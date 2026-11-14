"""Serialize S7 byte updates and heartbeat scheduling across local workers."""
import hashlib
import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


_lock = threading.RLock()


def _lock_windows(handle, timeout=15):
    """LK_LOCK retries only once a second and can starve behind the sampler."""
    import msvcrt
    deadline = time.monotonic() + timeout
    while True:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError('本机 PLC 通信锁等待超时；请检查是否同时运行多个程序副本或调试任务') from exc
            time.sleep(0.02)


@contextmanager
def plc_io(transport, *, purpose='io'):
    # Memory transports are independent PLCs; real connections share a lock by endpoint.
    with _lock:
        if not hasattr(transport, 'address'):
            yield None
            return
        endpoint = (transport.address, transport.tcp_port, transport.rack, transport.slot)
        key = hashlib.sha256(repr(endpoint).encode()).hexdigest()[:24]
        path = Path(getattr(settings, 'DATA_DIR', settings.BASE_DIR)) / 'logs' / f'plc_{purpose}_{key}.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+b') as initial:
            if initial.tell() == 0:
                initial.write(b' ')
        with path.open('r+b', buffering=0) as handle:
            if os.name == 'nt':
                import msvcrt
                _lock_windows(handle)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def plc_read_interval(transport):
    """Share a completion-based read gap across connections and processes."""
    from .plc_db100 import PLC_SCAN_INTERVAL
    with plc_io(transport, purpose='read') as handle:
        handle.seek(1)
        saved = handle.read().strip()
        previous = float(saved) if saved else None
        if previous is not None:
            elapsed = time.monotonic() - previous
            if 0 <= elapsed < PLC_SCAN_INTERVAL:
                time.sleep(PLC_SCAN_INTERVAL - elapsed)
        try:
            yield
        finally:
            # Failed reads also consume a slot; retries cannot form a busy loop.
            handle.seek(1)
            handle.write(str(time.monotonic()).encode('ascii'))
            handle.truncate()
            handle.flush()
