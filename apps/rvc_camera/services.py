"""RVC 相机业务服务层（Django 侧门面）。

对外接口刻意对齐旧 ``apps.dm_camera.services.DMCameraService`` 的关键方法
（is_connected / is_streaming / connect / start_stream /
capture_frame_data / get_status），使 vision 料架定位、坐标工作台等调用方
可以零改动切换到 RVC 相机。

与 DM 的区别：真实 SDK 调用在独立进程 ``rvc_service`` 中完成，本类只通过
HTTP 取结果并把落盘的 .npy 点云读回 numpy。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from django.conf import settings

from .client import RvcCameraClient, RvcCameraConfigurationError, RvcCameraError

logger = logging.getLogger(__name__)


def _rvc_cfg() -> Dict[str, Any]:
    return getattr(settings, "AUTOMATIC_ORDER", {}).get("RVC_CAMERA", {})


class RvcCameraService:
    """RVC 相机服务单例（无状态硬件句柄，仅缓存 HTTP 客户端与连接状态）。"""

    _instance: Optional["RvcCameraService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, client: Optional[RvcCameraClient] = None) -> None:
        if getattr(self, "_initialized", False):
            # 允许测试注入自定义 client
            if client is not None:
                self._client = client
            return
        self._client = client or RvcCameraClient()
        self._status_cache: Dict[str, Any] = {}
        self._status_cache_at = 0.0
        self._initialized = True

    # ── 状态 ────────────────────────────────────────────────────────────
    def _cached_status(self, ttl_seconds: float = 2.0) -> Dict[str, Any]:
        now = time.monotonic()
        if self._status_cache and now - self._status_cache_at < ttl_seconds:
            return self._status_cache
        try:
            status = self._client.status()
            self._status_cache = status
            self._status_cache_at = now
            return status
        except RvcCameraError:
            self._status_cache = {"connected": False, "streaming": False}
            self._status_cache_at = now
            return self._status_cache

    @property
    def is_connected(self) -> bool:
        return bool(self._cached_status().get("connected"))

    @property
    def is_streaming(self) -> bool:
        # RVC 为单次触发采集，连接即可采
        return self.is_connected

    def get_status(self) -> Dict[str, Any]:
        try:
            status = self._client.status()
            self._status_cache = status
            self._status_cache_at = time.monotonic()
            return status
        except RvcCameraError as exc:
            return {
                "connected": False,
                "streaming": False,
                "service_online": False,
                "error": str(exc),
            }

    # ── 设备发现 / 连接 ─────────────────────────────────────────────────
    def find_devices(self) -> List[Dict[str, Any]]:
        return self._client.find_devices()

    def connect(
        self,
        device_sn: Optional[str] = None,
        config_id: Optional[int] = None,
        *,
        ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """连接相机（config_id 仅为对齐旧接口，RVC 不使用数据库配置）。"""
        result = self._client.connect(sn=device_sn, ip=ip)
        self._status_cache_at = 0
        # 连接后应用 settings 中的默认模式/曝光
        cfg = _rvc_cfg()
        try:
            if cfg.get("DEFAULT_MODE"):
                self._client.set_mode(cfg["DEFAULT_MODE"])
            self._client.set_exposure(
                exposure_2d=cfg.get("EXPOSURE_2D"),
                exposure_3d=cfg.get("EXPOSURE_3D"),
                projector_brightness=cfg.get("PROJECTOR_BRIGHTNESS"),
            )
        except RvcCameraError as exc:
            logger.warning("连接后应用默认采集参数失败: %s", exc)
        return result

    def ensure_connected(self) -> None:
        """业务采集前的自动连接（对齐旧 DM 行为：无需先在页面手动连接）。"""
        if self.is_connected:
            return
        cfg = _rvc_cfg()
        self._client.connect(
            sn=cfg.get("CAMERA_SN") or None,
            ip=cfg.get("CAMERA_IP") or None,
            camera_id=cfg.get("CAMERA_ID", 0),
        )
        self._status_cache_at = 0
        if cfg.get("DEFAULT_MODE"):
            self._client.set_mode(cfg["DEFAULT_MODE"])
        self._client.set_exposure(
            exposure_2d=cfg.get("EXPOSURE_2D"),
            exposure_3d=cfg.get("EXPOSURE_3D"),
            projector_brightness=cfg.get("PROJECTOR_BRIGHTNESS"),
        )

    def start_stream(self) -> Dict[str, str]:
        """RVC 为单次触发采集，无需开启数据流；保留方法以兼容旧调用。"""
        if not self.is_connected:
            self.ensure_connected()
        return {"status": "connected", "message": "RVC 相机就绪（单次触发模式）"}

    def stop_stream(self) -> Dict[str, str]:
        return {"status": "connected", "message": "RVC 相机无需停止数据流"}

    def disconnect(self) -> Dict[str, Any]:
        result = self._client.disconnect()
        self._status_cache_at = 0
        return result

    def recover(self, *, ip: Optional[str] = None, sn: Optional[str] = None) -> Dict[str, Any]:
        result = self._client.recover(ip=ip, sn=sn)
        self._status_cache_at = 0
        return result

    def set_mode(self, mode: str) -> Dict[str, Any]:
        return self._client.set_mode(mode)

    def set_exposure(self, **kwargs: Any) -> Dict[str, Any]:
        return self._client.set_exposure(**kwargs)

    # ── 采集 ────────────────────────────────────────────────────────────
    @staticmethod
    def _dated_output_dir() -> Path:
        cfg = _rvc_cfg()
        base = Path(cfg.get("OUTPUT_DIR") or (settings.MEDIA_ROOT / "rvc_captures"))
        today = datetime.now().strftime("%Y/%m/%d")
        return base / today

    def _to_media_relative(self, abs_path: str) -> str:
        """相机服务落盘的绝对路径 → MEDIA_ROOT 相对存储名。"""
        if not abs_path:
            return ""
        p = Path(abs_path)
        try:
            return p.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
        except (ValueError, OSError):
            return str(p)

    def capture_frame_data(
        self,
        frame_type: str = "POINTCLOUD",
        save_record: bool = True,
        *,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """采集一帧并返回算法可直接使用的数据（对齐旧 DM 接口契约）。

        Returns:
            dict: data(np.ndarray H×W×3 点云，单位毫米)、width、height、
            image_width、image_height、frame_index、confidence、
            raw_data_path（.npy 存储相对路径）、result_image_path、preview_url 等
        """
        frame_type = (frame_type or "POINTCLOUD").upper()
        if frame_type not in {"POINTCLOUD", "RGB", "2D"}:
            raise RvcCameraError(
                f"RVC 相机仅支持 POINTCLOUD / RGB 帧类型，收到: {frame_type}"
            )

        output_dir = self._dated_output_dir()
        need_2d = frame_type in {"RGB", "2D"}
        meta = self._client.capture(
            output_dir=str(output_dir),
            mode=mode,
            save_2d=True,  # 点云帧也顺带存一张 2D 图用于预览/追溯
            save_ply=frame_type == "POINTCLOUD",
        )

        width = int(meta.get("width") or 0)
        height = int(meta.get("height") or 0)
        point_count = int(meta.get("point_count") or 0)
        confidence = (
            round(point_count / float(width * height), 4)
            if width and height
            else 0.0
        )

        result: Dict[str, Any] = {
            "frame_type": frame_type,
            "width": width,
            "height": height,
            "image_width": int(meta.get("image_width") or 0),
            "image_height": int(meta.get("image_height") or 0),
            "frame_index": int(meta.get("frame_index") or 0),
            "confidence": confidence,
            "mode": meta.get("mode"),
            "source": "rvc_camera",
            "raw_data_path": "",
            "result_image_path": "",
            "preview_url": "",
            "ply_path": "",
        }

        if frame_type == "POINTCLOUD":
            npy_abs = meta.get("pointcloud_npy", "")
            if not npy_abs or not Path(npy_abs).is_file():
                raise RvcCameraError(f"相机服务未返回有效的点云文件: {npy_abs}")
            data = np.load(npy_abs)
            if data.ndim != 3 or data.shape[2] != 3:
                raise RvcCameraError(f"点云数据维度异常: {data.shape}")
            result["data"] = data
            result["raw_data_path"] = self._to_media_relative(npy_abs)
            result["ply_path"] = self._to_media_relative(meta.get("pointcloud_ply", ""))
        else:
            # RGB / 2D 帧：读取 PNG 为 numpy(H×W×3)
            from PIL import Image

            img_abs = meta.get("image_2d", "")
            if not img_abs or not Path(img_abs).is_file():
                raise RvcCameraError("相机服务未返回有效的 2D 图像文件")
            result["data"] = np.asarray(Image.open(img_abs).convert("RGB"))
            result["width"] = int(meta.get("image_width") or result["data"].shape[1])
            result["height"] = int(meta.get("image_height") or result["data"].shape[0])

        img_rel = self._to_media_relative(meta.get("image_2d", ""))
        if img_rel:
            result["result_image_path"] = img_rel
            result["preview_url"] = f"{settings.MEDIA_URL}{img_rel}"

        logger.info(
            "RVC 采集成功 frame=%s mode=%s size=%sx%s points=%s",
            frame_type, meta.get("mode"), width, height, point_count,
        )

        # ── 额外保存 2D 相机原图到 rvc_service/pic/YYYYMMDD_HHMMSS/ ──────
        # 深度伪彩图 / 点云 npy 由上层 Rack3DLocator.capture() 统一写入同一目录
        if frame_type == "POINTCLOUD":
            self._save_capture_snapshot(
                image_2d_src=meta.get("image_2d", ""),
                npy_src=meta.get("pointcloud_npy", ""),
            )

        return result

    @staticmethod
    def _pic_base_dir() -> Path:
        """返回 rvc_service/pic 目录（绝对路径）。"""
        from django.conf import settings as _s
        return Path(getattr(_s, "BASE_DIR", Path(__file__).resolve().parent.parent.parent)) / "rvc_service" / "pic"

    @staticmethod
    def pic_session_dir() -> Path:
        """新建一个以 YYYYMMDD_HHMMSS 命名的采集快照目录并返回。"""
        from apps.rvc_camera.services import RvcCameraService
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = RvcCameraService._pic_base_dir() / stamp
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _save_capture_snapshot(
        self,
        image_2d_src: str,
        npy_src: str = "",
    ) -> Path:
        """复制 2D 相机原图到 rvc_service/pic/YYYYMMDD_HHMMSS/ 目录。

        返回新建的快照目录路径，供上层写入深度伪彩图等额外文件。
        """
        import shutil

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = self._pic_base_dir() / stamp
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("无法创建采集快照目录 %s: %s", save_dir, exc)
            return save_dir

        # 复制 2D 相机原图
        if image_2d_src and Path(image_2d_src).is_file():
            try:
                shutil.copy2(image_2d_src, save_dir / "image2d.png")
            except OSError as exc:
                logger.warning("复制 2D 图像失败: %s", exc)

        logger.info("采集快照目录已创建: %s", save_dir)
        return save_dir




    # 旧接口名别名（部分代码/脚本可能调用 capture）
    def capture(self, frame_type: str = "POINTCLOUD", save_record: bool = True) -> Dict[str, Any]:
        return self.capture_frame_data(frame_type=frame_type, save_record=save_record)
