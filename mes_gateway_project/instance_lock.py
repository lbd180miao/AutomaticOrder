"""Keep one process per persistent data directory on Windows."""
import os


def acquire(directory):
    handle = open(directory / '.instance.lock', 'a+b')
    if os.name == 'nt':
        import msvcrt
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            raise RuntimeError('此数据目录的程序已启动，请使用现有窗口或先退出旧程序') from None
    return handle
