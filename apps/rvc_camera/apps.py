"""RVC 相机 Django App 配置。

Django 启动时自动在后台拉起独立相机服务进程（python -m rvc_service），
Django 进程退出时自动关闭相机进程，无需手动开第二个终端窗口。

架构说明：
  PyRVC SDK 非线程安全，必须在独立进程中运行。
  本 App 通过 subprocess.Popen 启动 rvc_service，
  Django 只通过本机 HTTP（127.0.0.1:8001）与它通信，互不干扰。
"""
import atexit
import logging
import os
import subprocess
import sys
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
import threading

from django.apps import AppConfig

logger = logging.getLogger("apps.rvc_camera")

_rvc_stop = threading.Event()
_rvc_monitor = None
_rvc_lock = threading.Lock()
_rvc_proc: subprocess.Popen | None = None   # 全局持有子进程句柄


def _stop_rvc_service() -> None:
    """Django 退出时关闭相机子进程（由 atexit 注册）。"""
    global _rvc_proc
    _rvc_stop.set()
    with _rvc_lock:
        proc = _rvc_proc
    if proc is None or proc.poll() is not None:
        return
    logger.info("RVC 相机服务正在关闭（PID=%s）...", proc.pid)
    try:
        # EOF also reaches the child if this process crashes or its window closes.
        proc.stdin.close()
        proc.wait(timeout=12)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
    _rvc_proc = None
    logger.info("RVC 相机服务已退出。")


class RvcCameraConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rvc_camera"
    verbose_name = "RVC 3D相机"

    def ready(self) -> None:
        """Django 完成启动后自动拉起 rvc_service 子进程。"""
        # ── 跳过不需要启动相机的场景 ──────────────────────────────────
        # manage.py migrate / makemigrations / shell 等管理命令不需要相机
        argv0 = sys.argv[0] if sys.argv else ""
        skip_cmds = {
            "migrate", "makemigrations", "shell", "shell_plus",
            "collectstatic", "test", "check", "inspectdb",
            "createsuperuser", "changepassword", "dbshell",
            "check_rack_references",
        }
        if any(cmd in sys.argv for cmd in skip_cmds):
            return

        # Django runserver 会 fork 两次（autoreload），只让主进程启动相机
        # RUN_MAIN=true 表示这是 autoreloader 的子进程（真正跑业务的那个），
        # 没有 RUN_MAIN 说明是外层 watcher 进程，跳过。
        # 判断：如果是 runserver 命令，必须等 RUN_MAIN=true 才启动
        if "runserver" in sys.argv and "--noreload" not in sys.argv and not os.environ.get("RUN_MAIN"):
            return

        self._launch_rvc_service()

    # ------------------------------------------------------------------
    def _launch_rvc_service(self) -> None:
        """启动 rvc_service 子进程并注册退出清理。"""
        from django.conf import settings

        global _rvc_proc

        # 已经在运行，不重复启动
        if _rvc_proc is not None and _rvc_proc.poll() is None:
            logger.debug("RVC 相机服务已在运行（PID=%s），跳过重复启动。", _rvc_proc.pid)
            return

        cfg = getattr(settings, "AUTOMATIC_ORDER", {}).get("RVC_CAMERA", {})
        auto_start = cfg.get("AUTO_START", True)
        if not auto_start:
            logger.info("RVC_CAMERA.AUTO_START=False，跳过自动启动相机服务。")
            return

        global _rvc_monitor
        if _rvc_monitor is not None and _rvc_monitor.is_alive():
            return
        _rvc_stop.clear()
        atexit.register(_stop_rvc_service)
        _rvc_monitor = threading.Thread(
            target=_supervise_rvc_service, args=(dict(cfg),),
            daemon=True, name="rvc-service-monitor",
        )
        _rvc_monitor.start()


def _service_alive(port):
    # 本机健康检查不经过系统 HTTP 代理。
    try:
        with build_opener(ProxyHandler({})).open(
            f"http://127.0.0.1:{port}/health", timeout=2,
        ) as response:
            body = json.load(response)
        return body.get("success") is True and body.get("data", {}).get("service") == "rvc-camera-service"
    except Exception:
        return False


def _ensure_rvc_service(cfg):
    """复用已有服务；只管理本进程创建的子进程。"""
    from django.conf import settings
    global _rvc_proc
    with _rvc_lock:
        if _rvc_stop.is_set():
            return
        if _rvc_proc is not None:
            code = _rvc_proc.poll()
            if code is None:
                return
            logger.error("RVC 相机进程已退出（exit=%s），正在重新启动", code)
            _rvc_proc = None
        port = int(cfg.get("SERVICE_PORT", 8001))
        if _service_alive(port):
            return
        root = Path(settings.BASE_DIR)
        log_dir = Path(getattr(settings, "DATA_DIR", root)) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = ([sys.executable, '--rvc-service'] if getattr(sys, 'frozen', False)
               else [sys.executable, '-u', '-m', 'rvc_service']) + [
            '--host', '127.0.0.1', '--port', str(port),
            '--ip', cfg.get('CAMERA_IP', '169.254.10.202'),
            '--camera-id', str(cfg.get('CAMERA_ID', 0)),
            '--parent-stdin',
        ]
        if cfg.get('CAMERA_SN'):
            cmd += ['--sn', cfg['CAMERA_SN'].strip()]
        if cfg.get('OUTPUT_DIR'):
            cmd += ['--output-dir', str(cfg['OUTPUT_DIR'])]
        env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        # 直接落盘，避免 PIPE 无人读取导致相机进程阻塞。
        with (log_dir / 'rvc-service.log').open('ab', buffering=0) as output:
            from datetime import datetime
            output.write(f"\n[{datetime.now().isoformat()}] Starting RVC service on port {port}\n".encode())
            _rvc_proc = subprocess.Popen(
                cmd, cwd=str(root), env=env, stdout=output,
                stderr=subprocess.STDOUT, stdin=subprocess.PIPE, **kwargs,
            )
        logger.warning("RVC 相机服务已启动 PID=%s，日志：%s", _rvc_proc.pid, log_dir / 'rvc-service.log')


def _supervise_rvc_service(cfg):
    """网页后台每 5 秒检查一次，启动失败或进程退出后重试。"""
    while not _rvc_stop.is_set():
        try:
            _ensure_rvc_service(cfg)
        except Exception:
            logger.exception("RVC 相机服务启动失败，5 秒后重试")
        if _rvc_stop.wait(5):
            break
