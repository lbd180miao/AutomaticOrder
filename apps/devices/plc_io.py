"""Serialize S7 byte updates and heartbeat scheduling across local workers."""
import hashlib
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


_lock = threading.RLock()


@contextmanager
def plc_io(transport):
    # Memory transports are independent PLCs; real connections share a lock by endpoint.
    with _lock:
        if not hasattr(transport, 'address'):
            yield None
            return
        endpoint = (transport.address, transport.tcp_port, transport.rack, transport.slot)
        key = hashlib.sha256(repr(endpoint).encode()).hexdigest()[:24]
        path = Path(getattr(settings, 'DATA_DIR', settings.BASE_DIR)) / 'logs' / f'plc_io_{key}.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+b') as initial:
            if initial.tell() == 0:
                initial.write(b' ')
        with path.open('r+b') as handle:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
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
