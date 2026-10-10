"""RVC 相机服务启动入口。

用法（在项目根目录、激活项目虚拟环境后）：

    python -m rvc_service
    python -m rvc_service --host 127.0.0.1 --port 8001 --ip 169.254.10.202
    python -m rvc_service --no-auto-connect        # 仅启动服务，不自动连相机

环境变量（命令行参数优先）：
    RVC_CAMERA_SERVICE_HOST   默认 127.0.0.1
    RVC_CAMERA_SERVICE_PORT   默认 8001
    RVC_CAMERA_IP             默认 169.254.10.202（留空则连接第一台设备）
    RVC_CAMERA_SN             按序列号连接（优先级高于 IP）
    RVC_CAMERA_ID             相机通道 0/1（双目机型），默认 0
    RVC_CAMERA_AUTO_CONNECT   1/0，默认 1
    RVC_CAMERA_OUTPUT_DIR     采集文件目录，默认项目根目录 media/rvc_captures
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path


def _project_root() -> Path:
    # rvc_service/__main__.py 的上两级即项目根目录
    return Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RVC 3D 相机独立服务")
    parser.add_argument('--parent-stdin', action='store_true',
                        help='随启动它的网页进程退出（内部使用）')
    parser.add_argument(
        "--host",
        default=os.environ.get("RVC_CAMERA_SERVICE_HOST", "127.0.0.1"),
        help="监听地址，默认 127.0.0.1（仅本机访问）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RVC_CAMERA_SERVICE_PORT", "8001")),
        help="监听端口，默认 8001",
    )
    parser.add_argument(
        "--ip",
        default=os.environ.get("RVC_CAMERA_IP", "169.254.10.202"),
        help="相机 IP；留空且未指定 SN 时连接枚举到的第一台设备",
    )
    parser.add_argument(
        "--sn",
        default=os.environ.get("RVC_CAMERA_SN", ""),
        help="相机序列号，指定后优先于 --ip",
    )
    parser.add_argument(
        "--camera-id",
        default=os.environ.get("RVC_CAMERA_ID", "0"),
        help="相机通道（0/1，双目机型），默认 0",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("RVC_CAMERA_OUTPUT_DIR", ""),
        help="采集文件保存目录，默认 项目根/media/rvc_captures",
    )
    parser.add_argument(
        "--no-auto-connect",
        action="store_true",
        default=not _env_bool("RVC_CAMERA_AUTO_CONNECT", True),
        help="只启动 HTTP 服务，不自动连接相机",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("rvc_service")

    args = parse_args(argv)
    stopping = threading.Event()
    if args.parent_stdin:
        threading.Thread(target=_watch_parent, args=(stopping,),
                         daemon=True, name='web-parent-watch').start()
    from .server import make_server
    output_dir = Path(args.output_dir) if args.output_dir else (
        _project_root() / "media" / "rvc_captures"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    camera_ip = args.ip.strip() or None
    camera_sn = args.sn.strip() or None

    server = make_server(
        args.host,
        args.port,
        output_dir,
        auto_connect=not args.no_auto_connect,
        camera_ip=camera_ip,
        camera_sn=camera_sn,
        camera_id=args.camera_id,
    )

    # 退出时释放相机与 SDK，避免相机被死会话占用
    controller = server.RequestHandlerClass.controller

    def _shutdown(signum=None, frame=None):  # noqa: ANN001
        logger.info("收到退出信号，正在释放 RVC 相机资源 ...")
        stopping.set()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    logger.info("RVC 相机服务已启动: http://%s:%s", args.host, args.port)
    logger.info("采集文件目录: %s", output_dir)
    logger.info("请确认已关闭 RVCManager（否则会抢占相机连接）")
    try:
        # shutdown() from a signal handler on the serving thread deadlocks.
        server.timeout = 0.5
        while not stopping.is_set():
            server.handle_request()
    finally:
        try:
            controller.system_shutdown()
        finally:
            server.server_close()
    return 0


def _watch_parent(stopping):
    """Pipe EOF survives abrupt parent termination, including Windows window close."""
    try:
        if sys.platform == 'win32':
            # A blocking CRT stdin read holds the stream lock. Native DLL
            # initialization (including NumPy) can need that lock and deadlock.
            # Probe the pipe instead, so SDK imports and calls remain runnable.
            import ctypes
            import msvcrt
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            peek = kernel32.PeekNamedPipe
            peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                             wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD),
                             wintypes.LPVOID]
            peek.restype = wintypes.BOOL
            fd = sys.stdin.fileno()
            handle = msvcrt.get_osfhandle(fd)
            while not stopping.is_set():
                available = wintypes.DWORD()
                if not peek(handle, None, 0, None, ctypes.byref(available), None):
                    error = ctypes.get_last_error()
                    if error in (109, 232):  # broken pipe / pipe closing
                        break
                    raise ctypes.WinError(error)
                if available.value:
                    os.read(fd, min(available.value, 4096))
                stopping.wait(0.25)
        else:
            while sys.stdin.buffer.read(1):
                pass
    finally:
        # Bound shutdown even when a native SDK call is stuck during connect/capture.
        fallback = threading.Timer(10, os._exit, args=(0,))
        fallback.daemon = True
        fallback.start()
        stopping.set()


if __name__ == "__main__":
    raise SystemExit(main())
