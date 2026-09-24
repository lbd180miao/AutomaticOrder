"""RVC 相机服务 HTTP 客户端（Django 进程内使用）。

Django 不直接 import PyRVC，所有相机操作都通过 HTTP 调用独立进程
``rvc_service``（默认 http://127.0.0.1:8001），与海康 2D 相机的
“独立进程独占 SDK”隔离思路一致。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class RvcCameraError(RuntimeError):
    """相机服务/硬件错误（服务未启动、连接失败、采集失败等）。"""


class RvcCameraConfigurationError(ValueError):
    """相机参数配置错误（如不支持的模式），调用方不得静默回退到模拟数据。"""


def _rvc_settings() -> Dict[str, Any]:
    return getattr(settings, "AUTOMATIC_ORDER", {}).get("RVC_CAMERA", {})


class RvcCameraClient:
    """对独立 RVC 相机服务的薄封装。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        cfg = _rvc_settings()
        self.base_url = (base_url or cfg.get("SERVICE_URL") or "http://127.0.0.1:8001").rstrip("/")
        self.timeout = timeout or cfg.get("TIMEOUT", 30)
        self._session = requests.Session()

    # ── 内部工具 ────────────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(
                method,
                url,
                json=payload if method.upper() == "POST" else None,
                params=payload if method.upper() == "GET" else None,
                timeout=timeout or self.timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RvcCameraError(
                "无法连接 RVC 相机服务（%s）。\n"
                "请新开一个终端，在项目根目录运行：python -m rvc_service\n"
                "并确认：1) 相机已上电、网卡同网段；2) 已关闭 RVCManager。\n"
                "原始错误: %s" % (self.base_url, exc)
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise RvcCameraError(f"RVC 相机服务响应超时（{path}，{self.timeout}s）") from exc
        except requests.exceptions.RequestException as exc:
            raise RvcCameraError(f"RVC 相机服务请求失败（{path}）: {exc}") from exc

        try:
            body = resp.json()
        except ValueError as exc:
            raise RvcCameraError(
                f"RVC 相机服务返回了非 JSON 响应（HTTP {resp.status_code}）: {resp.text[:200]}"
            ) from exc

        if not body.get("success", False):
            error = body.get("error", "未知错误")
            # 参数类错误（不支持的模式等）归为配置错误，业务层不得回退模拟数据
            if resp.status_code == 400:
                raise RvcCameraConfigurationError(error)
            raise RvcCameraError(error)
        return body.get("data") or {}

    def _get(self, path: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        return self._request("GET", path, timeout=timeout)

    def _post(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self._request("POST", path, payload or {}, timeout=timeout)

    # ── 服务/相机状态 ──────────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        return self._get("/health", timeout=3)

    def is_service_alive(self) -> bool:
        try:
            self.health()
            return True
        except RvcCameraError:
            return False

    def status(self) -> Dict[str, Any]:
        return self._get("/status", timeout=5)

    def find_devices(self) -> List[Dict[str, Any]]:
        return self._get("/find_devices", timeout=15).get("devices", [])

    # ── 连接管理 ────────────────────────────────────────────────────────
    def connect(
        self,
        *,
        ip: Optional[str] = None,
        sn: Optional[str] = None,
        camera_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        cfg = _rvc_settings()
        return self._post(
            "/connect",
            {
                "ip": ip or cfg.get("CAMERA_IP") or None,
                "sn": sn or cfg.get("CAMERA_SN") or None,
                "camera_id": camera_id if camera_id is not None else cfg.get("CAMERA_ID", 0),
            },
            timeout=20,
        )

    def disconnect(self) -> Dict[str, Any]:
        return self._post("/disconnect")

    def recover(
        self,
        *,
        ip: Optional[str] = None,
        sn: Optional[str] = None,
        camera_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        cfg = _rvc_settings()
        return self._post(
            "/recover",
            {
                "ip": ip or cfg.get("CAMERA_IP") or None,
                "sn": sn or cfg.get("CAMERA_SN") or None,
                "camera_id": camera_id if camera_id is not None else cfg.get("CAMERA_ID", 0),
            },
            timeout=30,
        )

    # ── 参数设置 ────────────────────────────────────────────────────────
    def set_mode(self, mode: str) -> Dict[str, Any]:
        return self._post("/set_mode", {"mode": mode})

    def set_exposure(
        self,
        *,
        exposure_2d: Optional[float] = None,
        exposure_3d: Optional[float] = None,
        projector_brightness: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._post(
            "/set_exposure",
            {
                "exposure_2d": exposure_2d,
                "exposure_3d": exposure_3d,
                "projector_brightness": projector_brightness,
            },
        )

    # ── 采集 ────────────────────────────────────────────────────────────
    def capture(
        self,
        *,
        output_dir: Optional[str] = None,
        mode: Optional[str] = None,
        exposure_2d: Optional[float] = None,
        exposure_3d: Optional[float] = None,
        projector_brightness: Optional[int] = None,
        save_2d: bool = True,
        save_ply: bool = True,
        pointcloud_scale: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        cfg = _rvc_settings()
        from pathlib import Path

        target_dir = Path(output_dir) if output_dir else cfg.get("OUTPUT_DIR")
        if target_dir is not None:
            target_dir = Path(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_dir = str(target_dir)
        # ⚠️ 注意：只有调用方明确传入曝光/模式参数时才传给服务端。
        # 若传 None，服务端会用 LoadCaptureOptionParameters() 读回的内部参数，
        # 但该方式下 capture_mode 整数值可能不被 SDK 支持（如 "capture_mode[2] not support!"）。
        # 曝光参数应在 ensure_connected() 时通过 set_exposure() 接口设置一次，
        # 采集时只需直接 Capture()（Method 3，SDK 推荐）。
        payload: Dict[str, Any] = {
            "output_dir": target_dir,
            "save_2d": save_2d,
            "save_ply": save_ply,
        }
        # 只在明确提供时才传这些参数，避免触发 Method 2 路径
        if mode is not None:
            payload["mode"] = mode
        elif cfg.get("DEFAULT_MODE"):
            payload["mode"] = cfg["DEFAULT_MODE"]
        if exposure_2d is not None:
            payload["exposure_2d"] = exposure_2d
        if exposure_3d is not None:
            payload["exposure_3d"] = exposure_3d
        if projector_brightness is not None:
            payload["projector_brightness"] = projector_brightness
        if pointcloud_scale is not None:
            payload["pointcloud_scale"] = pointcloud_scale
        elif cfg.get("POINTCLOUD_SCALE"):
            payload["pointcloud_scale"] = cfg["POINTCLOUD_SCALE"]
        return self._post(
            "/capture",
            payload,
            timeout=timeout or cfg.get("CAPTURE_TIMEOUT", 60),
        )
