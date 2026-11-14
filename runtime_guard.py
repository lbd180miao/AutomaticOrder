"""Keep frozen startup failures visible, including native DLL process exits.

The guardian never imports Django or camera SDKs and never retries production
work. A native crash cannot be caught with Python's try/except in the worker.
"""
import faulthandler
import os
from pathlib import Path
import subprocess
import sys
import threading
import traceback
from datetime import datetime


def data_directory(argv):
    for index, value in enumerate(argv):
        if value.startswith('--data-dir='):
            return Path(value.split('=', 1)[1]).resolve()
        if value == '--data-dir' and index + 1 < len(argv):
            return Path(argv[index + 1]).resolve()
    return Path(os.environ.get('AUTOMATIC_ORDER_DATA_DIR') or
                (Path(sys.executable).parent if getattr(sys, 'frozen', False)
                 else Path(__file__).parent)).resolve()


def run_logged(main, argv):
    # Frozen Python may ignore PYTHONIOENCODING. Match the guardian's UTF-8
    # decoder explicitly before Django or the SDK emits any output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace', line_buffering=True)
    log_dir = data_directory(argv) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    # Retain the descriptor for the entire process lifetime (including atexit).
    global _fault_log
    filename = 'rvc-native-crash.log' if argv[:1] == ['--rvc-service'] else 'native-crash.log'
    _fault_log = (log_dir / filename).open('a', encoding='utf-8')
    _fault_log.write(f'\n[{datetime.now().isoformat()}] pid={os.getpid()} start\n')
    _fault_log.flush()
    faulthandler.enable(file=_fault_log, all_threads=True)
    try:
        return main(argv)
    except Exception:
        traceback.print_exc()
        with (log_dir / 'startup-error.log').open('a', encoding='utf-8') as log:
            log.write(f'\n[{datetime.now().isoformat()}]\n')
            traceback.print_exc(file=log)
        return 1


def watch_guardian():
    # Use the already-tested nonblocking Windows pipe watcher. Do not block
    # Python stdin's CRT lock while native numerical libraries are importing.
    from rvc_service.__main__ import _watch_parent
    stopped = threading.Event()

    def watch():
        _watch_parent(stopped)
        # The launcher has gone away: close all worker pipes as well. There is
        # no safe interactive continuation of hardware work without its owner.
        os._exit(0)

    threading.Thread(target=watch, daemon=True, name='launcher-watch').start()


def supervise(argv):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace', line_buffering=True)
    log_dir = data_directory(argv) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'server.log'
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        def report(message):
            log.write(message + '\n')
            try:
                print(message, flush=True)
            except (OSError, UnicodeError):
                pass

        report(f'[{datetime.now().isoformat()}] Starting application; log: {log_path}')
        process = subprocess.Popen(
            [sys.executable, '--web-server', *argv], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', env=env,
        )
        try:
            for line in process.stdout:
                report(line.rstrip('\n'))
            code = process.wait()
        except KeyboardInterrupt:
            process.stdin.close()
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait()
        finally:
            process.stdin.close()
            process.stdout.close()
        report(f'[{datetime.now().isoformat()}] Application exited: {code} (0x{code & 0xffffffff:08X})')
        if code:
            report('程序异常退出，错误已保存到 logs。请保留日志用于排查。')
            # Batch checks must terminate; a user double-clicking the EXE gets
            # a persistent error window, even for an access violation.
            if '--no-browser' not in argv and sys.stdin and sys.stdin.isatty():
                try:
                    input('按回车关闭此窗口…')
                except (EOFError, KeyboardInterrupt):
                    pass
        return code
