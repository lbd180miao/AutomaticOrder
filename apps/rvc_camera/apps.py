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
import signal
import subprocess
import sys
import time

from django.apps import AppConfig

logger = logging.getLogger("apps.rvc_camera")

_rvc_proc: subprocess.Popen | None = None   # 全局持有子进程句柄


def _stop_rvc_service() -> None:
    """Django 退出时关闭相机子进程（由 atexit 注册）。"""
    global _rvc_proc
    proc = _rvc_proc
    if proc is None or proc.poll() is not None:
        return
    logger.info("RVC 相机服务正在关闭（PID=%s）...", proc.pid)
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
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
        }
        if any(cmd in sys.argv for cmd in skip_cmds):
            return

        # Django runserver 会 fork 两次（autoreload），只让主进程启动相机
        # RUN_MAIN=true 表示这是 autoreloader 的子进程（真正跑业务的那个），
        # 没有 RUN_MAIN 说明是外层 watcher 进程，跳过。
        # 判断：如果是 runserver 命令，必须等 RUN_MAIN=true 才启动
        if "runserver" in sys.argv and not os.environ.get("RUN_MAIN"):
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

        # 构建启动命令（与 python -m rvc_service 等价，继承当前 venv）
        cmd = [
            sys.executable, "-m", "rvc_service",
            "--host", "127.0.0.1",
            "--port", str(cfg.get("SERVICE_PORT", 8001)),
            "--ip",   cfg.get("CAMERA_IP", "169.254.10.202"),
        ]
        sn = cfg.get("CAMERA_SN", "").strip()
        if sn:
            cmd += ["--sn", sn]

        camera_id = cfg.get("CAMERA_ID", 0)
        if camera_id:
            cmd += ["--camera-id", str(camera_id)]

        output_dir = cfg.get("OUTPUT_DIR")
        if output_dir:
            cmd += ["--output-dir", str(output_dir)]

        # Windows 下子进程需要 CREATE_NEW_PROCESS_GROUP 才能发 CTRL_BREAK_EVENT
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            _rvc_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                **kwargs,
            )
            logger.info(
                "✅ RVC 相机服务已自动启动（PID=%s），命令: %s",
                _rvc_proc.pid, " ".join(cmd),
            )
            # 等 1.5 秒，检查子进程有没有立刻崩溃
            time.sleep(1.5)
            if _rvc_proc.poll() is not None:
                out = _rvc_proc.stdout.read().decode("utf-8", errors="replace")
                logger.error(
                    "❌ RVC 相机服务启动后立即退出（exit=%s）：\n%s",
                    _rvc_proc.returncode, out,
                )
                _rvc_proc = None
                return

            # 注册 Django 退出时自动关闭
            atexit.register(_stop_rvc_service)

        except Exception as exc:
            logger.error("❌ 启动 RVC 相机服务失败: %s", exc)
            _rvc_proc = None
