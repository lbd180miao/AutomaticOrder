"""RVC 相机服务的 HTTP 接口（Python 标准库实现，零额外依赖，便于 PyInstaller 打包）。

接口一览（均为本机回环访问）：
    GET  /health              服务存活检查（不访问相机）
    GET  /status              相机连接与当前参数
    GET  /find_devices        枚举在线 RVC 设备
    POST /connect             连接相机      {"ip": "...", "sn": "...", "camera_id": 0}
    POST /disconnect          断开相机
    POST /recover             断线恢复（重新初始化 SDK + 连接）
    POST /set_mode            {"mode": "Robust"}
    POST /set_exposure        {"exposure_2d":.., "exposure_3d":.., "projector_brightness":..}
    POST /capture             采集一帧，保存 .npy 点云/.ply/2D 图

统一响应：{"success": true, "data": {...}} / {"success": false, "error": "..."}
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .camera_controller import (
    RvcCameraController,
    RvcConfigError,
    RvcControllerError,
)

logger = logging.getLogger("rvc_service")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


class RvcRequestHandler(BaseHTTPRequestHandler):
    controller: RvcCameraController = None  # 由 make_server 注入（类属性）
    default_output_dir: Path = None        # 由 make_server 注入

    # ── 基础收发 ────────────────────────────────────────────────────────
    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data: Optional[Dict[str, Any]] = None) -> None:
        self._send_json({"success": True, "data": data or {}})

    def _fail(self, error: str, status: int = 500) -> None:
        self._send_json({"success": False, "error": error}, status=status)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as exc:
            raise RvcConfigError(f"请求体不是合法 JSON: {exc}") from exc

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    # ── 路由 ────────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802 - stdlib 命名
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        try:
            if route == "/health":
                self._ok({"service": "rvc-camera-service", "status": "running"})
            elif route == "/status":
                self._ok(self.controller.status())
            elif route == "/find_devices":
                self._ok({"devices": self.controller.list_devices()})
            else:
                self._fail(f"未知接口: {route}", status=404)
        except (RvcControllerError, RvcConfigError) as exc:
            logger.warning("GET %s failed: %s", route, exc)
            self._fail(str(exc), status=400 if isinstance(exc, RvcConfigError) else 500)
        except Exception as exc:  # noqa: BLE001 - 服务不能因单次请求崩溃
            logger.exception("GET %s unexpected error", route)
            self._fail(f"服务内部错误: {exc}")

    def do_POST(self) -> None:  # noqa: N802 - stdlib 命名
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            body = self._read_json()
            # query 参数可作为 body 的补充（方便浏览器/form 调用）
            for key, value in query.items():
                body.setdefault(key, value)

            if route == "/connect":
                data = self.controller.connect(
                    sn=body.get("sn") or None,
                    ip=body.get("ip") or None,
                    camera_id=body.get("camera_id", 0),
                )
                self._ok(data)
            elif route == "/disconnect":
                self._ok(self.controller.disconnect())
            elif route == "/recover":
                data = self.controller.recover(
                    sn=body.get("sn") or None,
                    ip=body.get("ip") or None,
                    camera_id=body.get("camera_id", 0),
                )
                self._ok(data)
            elif route == "/set_mode":
                self._ok(self.controller.set_mode(body.get("mode", "")))
            elif route == "/set_exposure":
                self._ok(
                    self.controller.set_exposure(
                        exposure_2d=_as_float(body.get("exposure_2d")),
                        exposure_3d=_as_float(body.get("exposure_3d")),
                        gain_2d=_as_float(body.get("gain_2d")),
                        gain_3d=_as_float(body.get("gain_3d")),
                        projector_brightness=_as_int(body.get("projector_brightness")),
                    )
                )
            elif route == "/capture":
                output_dir = Path(body.get("output_dir") or self.default_output_dir)
                data = self.controller.capture(
                    output_dir,
                    mode=body.get("mode"),
                    exposure_2d=_as_float(body.get("exposure_2d")),
                    exposure_3d=_as_float(body.get("exposure_3d")),
                    projector_brightness=_as_int(body.get("projector_brightness")),
                    save_2d=bool(body.get("save_2d", True)),
                    save_ply=bool(body.get("save_ply", True)),
                    pointcloud_scale=_as_float(body.get("pointcloud_scale")),
                )
                self._ok(data)
            else:
                self._fail(f"未知接口: {route}", status=404)
        except (RvcControllerError, RvcConfigError) as exc:
            logger.warning("POST %s failed: %s", route, exc)
            self._fail(str(exc), status=400 if isinstance(exc, RvcConfigError) else 500)
        except Exception as exc:  # noqa: BLE001 - 服务不能因单次请求崩溃
            logger.exception("POST %s unexpected error", route)
            self._fail(f"服务内部错误: {exc}")


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(float(value))


def make_server(
    host: str,
    port: int,
    output_dir: Path,
    *,
    auto_connect: bool = True,
    camera_ip: Optional[str] = None,
    camera_sn: Optional[str] = None,
    camera_id: Any = 0,
) -> ThreadingHTTPServer:
    controller = RvcCameraController()
    RvcRequestHandler.controller = controller
    RvcRequestHandler.default_output_dir = Path(output_dir)

    server = ThreadingHTTPServer((host, port), RvcRequestHandler)

    if auto_connect:
        try:
            controller.system_init()
            status = controller.connect(
                sn=camera_sn, ip=camera_ip, camera_id=camera_id
            )
            logger.info("RVC 相机自动连接成功: %s", status.get("device", {}))
        except Exception as exc:  # noqa: BLE001 - 相机未上电不应阻止服务启动
            logger.warning(
                "启动时自动连接相机失败（服务仍启动，可稍后 /recover）: %s", exc
            )
    return server
