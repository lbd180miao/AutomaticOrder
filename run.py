"""Source and frozen executable entry point."""
import argparse
import os
import sys


def positive_threads(value):
    value = int(value)
    if not 1 <= value <= 64:
        raise argparse.ArgumentTypeError('threads must be between 1 and 64')
    return value


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--hik-capture']:
        from apps.devices.adapters.hik_capture_worker import main as hik_main
        return hik_main(argv[1:])
    # Frozen executables cannot interpret Python's -m option.
    if argv[:1] == ['--rvc-service']:
        from rvc_service.__main__ import main as camera_main
        return camera_main(argv[1:])
    parser = argparse.ArgumentParser(description='AutomaticOrder server')
    parser.add_argument('--threads', type=positive_threads,
                        default=os.environ.get('WAITRESS_THREADS', '8'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data-dir', help='Persistent directory containing db.sqlite3 and media')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    from pathlib import Path
    from instance_lock import acquire
    directory = Path(args.data_dir or os.environ.get('AUTOMATIC_ORDER_DATA_DIR') or
                     (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent)).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    instance_handle = acquire(directory)
    if args.data_dir:
        os.environ['AUTOMATIC_ORDER_DATA_DIR'] = os.path.abspath(args.data_dir)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
    import whitenoise.middleware  # Ensure PyInstaller includes this module.
    import django
    django.setup()
    from waitress import serve
    from django.core.wsgi import get_wsgi_application
    from django.conf import settings
    print(f'AutomaticOrder: threads={args.threads}, media={settings.MEDIA_ROOT}', flush=True)
    application = get_wsgi_application()
    from apps.workflow.listener import start_listener, stop_listener
    if settings.MES_GATEWAY_ENABLED:
        from apps.mes.remote_client import start_worker
        start_worker()
    if not args.no_browser:
        import threading
        import webbrowser
        threading.Timer(2, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    start_listener()
    try:
        serve(application, host=args.host, port=args.port, threads=args.threads)
    finally:
        stop_listener()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
