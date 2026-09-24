"""PyRVC 相机控制器（在独立相机服务进程内使用，Django 进程禁止导入本模块）。

封装 RVC X1/X2 相机的发现、连接、模式/曝光设置与采集，所有硬件操作由一把
进程内锁串行化（PyRVC 非线程安全，相机同一时刻只允许一个采集动作）。

实测 API（基于官方 SDK 示例 QuickCaptureX1/X2、CaptureOptionsX1/X2）：
    RVC.SystemInit() -> bool
    ret, devices = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
      # devices 是列表，len(devices) 即设备数量
    ret, info = device.GetDeviceInfo()
      # info.sn / info.name / info.support_x1 / info.support_x2 / info.support_extra
    device.IsFirmwareMatch() -> bool       # 固件版本检查，不匹配时拒绝连接
    cam = RVC.X1.Create(device, RVC.CameraID_Left)
    cam = RVC.X2.Create(device)            # X2 不传 CameraID
    cam.Open() -> bool
    cam.IsOpen() -> bool
    cam.Capture() -> bool                  # 推荐：直接使用相机内部参数（Method 3）
    cam.Capture(options) -> bool           # 可选：传入 X1/X2_CaptureOptions
    ret, options = cam.LoadCaptureOptionParameters()  # 读取相机当前参数
    cam.GetPointMap() -> PointMap
      pm_np = np.array(pm, copy=False).reshape(-1, 3)  # 展平为 N×3
    cam.GetImage(camera_id) -> Image       # X2 需传 camera_id
    cam.Close() / cam.Destroy() (静态方法 RVC.X1.Destroy / RVC.X2.Destroy)
    RVC.GetLastErrorMessage() -> str       # 获取最近一次错误信息
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import PyRVC as RVC
except ImportError as exc:  # pragma: no cover - 仅在未装 PyRVC 的开发机出现
    raise ImportError(
        "未安装 PyRVC，请在项目虚拟环境执行: pip install PyRVC requests"
    ) from exc


# ── 采集模式：业务别名 -> PyRVC 原生枚举 ──────────────────────────────────
# 现场常用名（HighPrecision / AntiMultiReflex ...）与 RVCManager 中文名都做了别名。
MODE_ALIASES: Dict[str, str] = {
    "FAST": "Fast",
    "快速": "Fast",
    "NORMAL": "Normal",
    "标准": "Normal",
    "HIGHPRECISION": "Normal",   # Robust 已废弃，映射 Normal
    "高精度": "Normal",
    "ROBUST": "Normal",         # Robust 已废弃
    "ULTRA": "Ultra",
    "超精细": "Ultra",
    "ANTIMULTIREFLEX": "AntiInterReflection",
    "ANTIINTERREFLECTION": "AntiInterReflection",
    "抗多次反射": "AntiInterReflection",
    "抗反光": "AntiInterReflection",
    "SWINGLINESCAN": "SwingLineScan",
    "摆动线扫": "SwingLineScan",
    "FIXEDLINESCAN": "FixedLineScan",
    "固定线扫": "FixedLineScan",
    "LINEARRAYSHIFT": "LineArrayShift",
}

# 原生模式名 -> 枚举属性
_MODE_ENUM_ATTR = {
    "Fast": "CaptureMode_Fast",
    "Normal": "CaptureMode_Normal",
    "Robust": "CaptureMode_Normal",  # Robust 已废弃 -> Normal
    "Ultra": "CaptureMode_Ultra",
    "AntiInterReflection": "CaptureMode_AntiInterReflection",
    "SwingLineScan": "CaptureMode_SwingLineScan",
    "FixedLineScan": "CaptureMode_FixedLineScan",
    "LineArrayShift": "CaptureMode_LineArrayShift",
}

# 线扫模式需要工件/相机运动，普通 Capture 不适用（X2 固定线扫走 StartFixedLineScan）
LINE_SCAN_MODES = {"SwingLineScan", "FixedLineScan", "LineArrayShift"}

_CAMERA_IDS = {
    0: "CameraID_Left",   # SDK示例用 CameraID_Left
    1: "CameraID_Right",
    "0": "CameraID_Left",
    "1": "CameraID_Right",
    "LEFT": "CameraID_Left",
    "RIGHT": "CameraID_Right",
    "EXTRA": "CameraID_Extra",
    "BOTH": "CameraID_Both",
}


class RvcControllerError(RuntimeError):
    """相机硬件/SDK 错误（连接失败、采集失败等），属于可重试/可回退类错误。"""


class RvcConfigError(ValueError):
    """相机参数配置错误（如不支持的模式名），调用方不得回退到模拟数据。"""


@dataclass
class CaptureState:
    """当前生效/待生效的采集参数（每次 Capture 时写入 options）。"""

    mode: str = "Normal"
    exposure_2d: int = 10             # RVC-M2600-V2 有效范围: 3-100
    exposure_3d: int = 50             # RVC-M2600-V2 有效范围: 3-100
    gain_2d: float = 1.0
    gain_3d: float = 1.0
    projector_brightness: int = 240  # 0-255
    save_2d: bool = True
    pointcloud_scale: float = 1.0    # 点云单位换算到毫米的系数（RVC 原生即毫米时为 1）
    
    @classmethod
    def from_json_config(cls, json_path: Path) -> "CaptureState":
        """从 RVC JSON 配置文件加载参数（RVCManager 导出格式）。"""
        import json
        
        if not json_path.exists():
            return cls()
        
        with open(json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # RVC JSON 配置中的字段映射
        mode_map = {
            1: "Fast",
            2: "Normal", 
            4: "Normal",  # capture_mode=4 对应 Normal
            3: "Ultra",
        }
        
        return cls(
            mode=mode_map.get(config.get("capture_mode", 2), "Normal"),
            exposure_2d=int(config.get("exposure_time_2d", 10)),
            exposure_3d=int(config.get("exposure_time_3d", 50)),
            gain_2d=float(config.get("gain_2d", 1.0)),
            gain_3d=float(config.get("gain_3d", 1.0)),
            projector_brightness=int(config.get("projector_brightness", 240)),
            save_2d=bool(config.get("enable_2d_in_capture", True)),
        )


@dataclass
class _Device:
    device: Any
    info: Any
    ip: str
    family: str                      # 'X1' / 'X2'
    camera: Any = None               # 已 Create 的 X1/X2 对象
    opened: bool = False


class RvcCameraController:
    """单相机控制器：同一进程只维护一个相机实例。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._lock = threading.RLock()
        self._inited = False
        self._dev: Optional[_Device] = None
        
        # 尝试从配置文件加载参数，否则使用默认值
        if config_path and Path(config_path).exists():
            self.state = CaptureState.from_json_config(Path(config_path))
        else:
            # 尝试从标准位置加载（rvc_service/rvc.json）
            default_config = Path(__file__).parent / "rvc.json"
            if default_config.exists():
                self.state = CaptureState.from_json_config(default_config)
            else:
                self.state = CaptureState()
        
        self.capture_count = 0
        self.last_error: str = ""

    # ── 系统生命周期 ────────────────────────────────────────────────────
    def system_init(self) -> None:
        with self._lock:
            if self._inited and RVC.SystemIsInited():
                return
            ok = bool(RVC.SystemInit())
            if not ok:
                raise RvcControllerError(
                    f"PyRVC SystemInit 失败: {RVC.GetLastErrorMessage()}"
                )
            self._inited = True

    def system_shutdown(self) -> None:
        with self._lock:
            self._close_locked()
            if self._inited:
                try:
                    RVC.SystemShutdown()
                finally:
                    self._inited = False

    # ── 设备发现 ────────────────────────────────────────────────────────
    @staticmethod
    def _decode_ip_bytes(value: Any) -> str:
        """把 SDK 返回的 bytes/str 解析为 IPv4 字符串。"""
        if isinstance(value, bytes):
            for encoding in ("utf-8", "gbk", "ascii"):
                try:
                    value = value.decode(encoding).strip("\x00").strip()
                    break
                except UnicodeDecodeError:
                    continue
        if isinstance(value, str) and value.count(".") == 3:
            parts = value.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                return value
        return ""

    @classmethod
    def _device_ip(cls, device: Any, camera_id: Any = None) -> str:
        """读取相机网口 IP。

        PyRVC 1.15 的 GetNetworkConfig 是实例方法，需指定网口
        （NetworkDevice_LeftCamera / RightCamera / ExtraCamera），
        返回 (网络类型, IP, 子网掩码, 网关(bytes), 端口(int))。
        """
        targets = []
        if camera_id is not None:
            targets.append(camera_id)
        targets += [
            RVC.NetworkDevice_LeftCamera,
            RVC.NetworkDevice_RightCamera,
            RVC.NetworkDevice_ExtraCamera,
        ]
        for target in targets:
            try:
                result = device.GetNetworkConfig(target)
            except Exception:
                continue
            if not isinstance(result, tuple):
                continue
            for item in result[1:4]:
                ip = cls._decode_ip_bytes(item)
                if ip:
                    return ip
        return ""

    @staticmethod
    def _info_dict(device: Any, ip: str) -> Dict[str, Any]:
        # SDK 示例：ret, info = device.GetDeviceInfo()
        result = device.GetDeviceInfo()
        info = result[1] if isinstance(result, tuple) else result
        return {
            "sn": getattr(info, "sn", ""),
            "name": getattr(info, "name", ""),
            "type": str(getattr(info, "type", "")),
            "ip": ip,
            "port": str(getattr(info, "port", "")),
            "support_x1": bool(getattr(info, "support_x1", False)),
            "support_x2": bool(getattr(info, "support_x2", False)),
            "support_color": bool(getattr(info, "support_color", False)),
            "support_extra": bool(getattr(info, "support_extra", False)),
            "workingdist_near_mm": getattr(info, "workingdist_near_mm", None),
            "workingdist_far_mm": getattr(info, "workingdist_far_mm", None),
        }

    def list_devices(self) -> List[Dict[str, Any]]:
        """枚举所有 GigE/USB 设备（只读，不打开相机）。"""
        self.system_init()
        with self._lock:
            # SDK 示例：ret, devices = RVC.SystemListDevices(opt)
            # devices 是 list，len(devices) 即实际设备数
            scan_result = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
            devices = scan_result[1] if isinstance(scan_result, tuple) else scan_result
            result: List[Dict[str, Any]] = []
            for dev in devices:
                ip = self._device_ip(dev)
                result.append(self._info_dict(dev, ip))
            return result


    def _find_device_locked(
        self, sn: Optional[str] = None, ip: Optional[str] = None
    ) -> Any:
        # SDK 示例：ret, devices = RVC.SystemListDevices(opt)，len(devices) 即设备数
        scan_result = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
        devices = scan_result[1] if isinstance(scan_result, tuple) else scan_result
        if len(devices) == 0:
            raise RvcControllerError(
                "未发现任何 RVC 设备：请检查相机电源、网线/网卡网段"
                "（相机 169.254.10.202，网卡需同网段），并关闭 RVCManager"
            )
        resolved: List[tuple] = []
        for dev in devices:
            # SDK 示例：ret, info = device.GetDeviceInfo()
            info_result = dev.GetDeviceInfo()
            info = info_result[1] if isinstance(info_result, tuple) else info_result
            dev_ip = self._device_ip(dev)
            resolved.append((dev, info, dev_ip))

        def _match(candidate: tuple) -> bool:
            _, info_obj, dev_ip = candidate
            if sn and getattr(info_obj, "sn", "") == sn:
                return True
            if ip and dev_ip == ip:
                return True
            return False

        if sn or ip:
            for candidate in resolved:
                if _match(candidate):
                    return candidate
            target = sn or ip
            available = [
                f"{getattr(i, 'sn', '')}@{dip}" for _, i, dip in resolved
            ]
            raise RvcControllerError(
                f"未找到目标 RVC 设备 {target}，当前在线设备: {available}"
            )
        return resolved[0]

    # ── 连接 / 断开 ─────────────────────────────────────────────────────
    def connect(
        self,
        sn: Optional[str] = None,
        ip: Optional[str] = None,
        camera_id: Any = 0,
    ) -> Dict[str, Any]:
        self.system_init()
        with self._lock:
            # 已连接同一台则幂等返回
            if self._dev and self._dev.opened:
                if (not sn or self._dev.info.sn == sn) and (
                    not ip or self._dev.ip == ip
                ):
                    return self.status()
                self._close_locked()

            device, info, dev_ip = self._find_device_locked(sn=sn, ip=ip)

            # SDK 示例：固件不匹配时应提示升级（IsFirmwareMatch）
            try:
                if not device.IsFirmwareMatch():
                    logger.warning(
                        "RVC 相机固件版本不匹配（SN=%s），建议用 RVCManager 升级固件",
                        getattr(info, "sn", ""),
                    )
            except Exception:
                pass  # 旧版 SDK 可能无此方法

            # SDK 示例 QuickCaptureX2：X2 用 RVC.X2.Create(device)，不传 CameraID
            # SDK 示例 QuickCaptureX1：X1 用 RVC.X1.Create(device, RVC.CameraID_Left)
            support_x2 = bool(getattr(info, "support_x2", False))
            family = "X2" if support_x2 else "X1"
            cam_id_enum = self._resolve_camera_id(camera_id)
            if family == "X2":
                camera = RVC.X2.Create(device)   # X2 不传 CameraID
            else:
                camera = RVC.X1.Create(device, cam_id_enum)

            opened = bool(camera.Open())
            if not opened:
                msg = RVC.GetLastErrorMessage() or "Open 返回 False"
                try:
                    if family == "X2":
                        RVC.X2.Destroy(camera)
                    else:
                        RVC.X1.Destroy(camera)
                except Exception:
                    pass
                raise RvcControllerError(
                    f"打开 RVC {family} 相机失败（SN={getattr(info, 'sn', '')} "
                    f"IP={dev_ip}）：{msg}。若提示占用，请关闭 RVCManager 后重试"
                )

            self._dev = _Device(
                device=device, info=info, ip=dev_ip, family=family,
                camera=camera, opened=True,
            )
            self.last_error = ""
            return self.status()


    @staticmethod
    def _resolve_camera_id(camera_id: Any):
        if isinstance(camera_id, str) and camera_id.isdigit():
            camera_id = int(camera_id)
        attr = _CAMERA_IDS.get(camera_id)
        if attr is None and isinstance(camera_id, int):
            attr = _CAMERA_IDS.get(0)
        if attr is None:
            raise RvcConfigError(f"不支持的 CameraID: {camera_id}")
        return getattr(RVC, attr)

    def _close_locked(self) -> None:
        dev = self._dev
        if dev is None:
            return
        if dev.camera is not None:
            try:
                if dev.opened:
                    dev.camera.Close()
            except Exception:
                pass
            try:
                # SDK 示例：用静态方法 RVC.X1.Destroy / RVC.X2.Destroy
                if dev.family == "X2":
                    RVC.X2.Destroy(dev.camera)
                else:
                    RVC.X1.Destroy(dev.camera)
            except Exception:
                pass
        dev.opened = False
        dev.camera = None
        self._dev = None


    def disconnect(self) -> Dict[str, Any]:
        with self._lock:
            self._close_locked()
            return self.status()

    def recover(
        self, sn: Optional[str] = None, ip: Optional[str] = None, camera_id: Any = 0
    ) -> Dict[str, Any]:
        """断线恢复：释放句柄 → 重新 SystemInit → 重新枚举连接。"""
        with self._lock:
            self._close_locked()
            try:
                if RVC.SystemIsInited():
                    RVC.SystemShutdown()
            except Exception:
                pass
            self._inited = False
            return self.connect(sn=sn, ip=ip, camera_id=camera_id)

    # ── 参数设置 ────────────────────────────────────────────────────────
    @staticmethod
    def resolve_mode(mode: str) -> str:
        """把业务侧模式名解析为 RVC 原生模式名。"""
        if not mode:
            raise RvcConfigError("采集模式不能为空")
        native = MODE_ALIASES.get(str(mode).strip().upper())
        if native is None:
            native = str(mode).strip()
        if native not in _MODE_ENUM_ATTR:
            raise RvcConfigError(
                f"不支持的 RVC 采集模式: {mode}，可选: {sorted(set(MODE_ALIASES.values()))}"
            )
        return native

    def _mode_enum(self, native_mode: str):
        return getattr(RVC, _MODE_ENUM_ATTR[native_mode])

    def set_mode(self, mode: str) -> Dict[str, Any]:
        native = self.resolve_mode(mode)
        with self._lock:
            self.state.mode = native
            return {"mode": native}

    def set_exposure(
        self,
        exposure_2d: Optional[float] = None,
        exposure_3d: Optional[float] = None,
        gain_2d: Optional[float] = None,
        gain_3d: Optional[float] = None,
        projector_brightness: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if exposure_2d is not None:
                self.state.exposure_2d = float(exposure_2d)
            if exposure_3d is not None:
                self.state.exposure_3d = float(exposure_3d)
            if gain_2d is not None:
                self.state.gain_2d = float(gain_2d)
            if gain_3d is not None:
                self.state.gain_3d = float(gain_3d)
            if projector_brightness is not None:
                self.state.projector_brightness = int(projector_brightness)
            return {
                "exposure_2d": self.state.exposure_2d,
                "exposure_3d": self.state.exposure_3d,
                "gain_2d": self.state.gain_2d,
                "gain_3d": self.state.gain_3d,
                "projector_brightness": self.state.projector_brightness,
            }

    # ── 采集 ────────────────────────────────────────────────────────────
    def _build_options(self, family: str, overrides: Dict[str, Any]):
        options = RVC.X2_CaptureOptions() if family == "X2" else RVC.X1_CaptureOptions()
        native_mode = self.resolve_mode(overrides.get("mode") or self.state.mode)
        options.capture_mode = self._mode_enum(native_mode)

        # SDK X2/X1_CaptureOptions.exposure_time_2d/3d 只接受 int，不接受 float
        options.exposure_time_2d = int(
            overrides.get("exposure_2d", self.state.exposure_2d)
        )
        options.exposure_time_3d = int(
            overrides.get("exposure_3d", self.state.exposure_3d)
        )
        if hasattr(options, "gain_2d"):
            options.gain_2d = float(overrides.get("gain_2d", self.state.gain_2d))
            options.gain_3d = float(overrides.get("gain_3d", self.state.gain_3d))
        if hasattr(options, "projector_brightness"):
            options.projector_brightness = int(
                overrides.get(
                    "projector_brightness", self.state.projector_brightness
                )
            )
        # 2D/3D 一起采；点云变换到相机坐标系；不算法线（省时间，PLY 用 PointsOnly）
        options.enable_2d_in_capture = bool(
            overrides.get("save_2d", self.state.save_2d)
        )
        if hasattr(options, "transform_to_camera"):
            options.transform_to_camera = True
        if hasattr(options, "calc_normal"):
            options.calc_normal = False
        return options, native_mode

    def capture(
        self,
        output_dir: Path,
        *,
        mode: Optional[str] = None,
        exposure_2d: Optional[float] = None,
        exposure_3d: Optional[float] = None,
        projector_brightness: Optional[int] = None,
        save_2d: bool = True,
        save_ply: bool = True,
        pointcloud_scale: Optional[float] = None,
    ) -> Dict[str, Any]:
        overrides = {
            "mode": mode,
            "exposure_2d": exposure_2d,
            "exposure_3d": exposure_3d,
            "projector_brightness": projector_brightness,
            "save_2d": save_2d,
        }
        with self._lock:
            if self._dev is None or not self._dev.opened:
                raise RvcControllerError("相机未连接，请先连接相机（/connect）")
            # SDK 示例：cam.IsOpen() 是实例方法
            if not self._dev.camera.IsOpen():
                raise RvcControllerError("相机连接已断开，请一键恢复连接")

            native_mode = self.resolve_mode(mode or self.state.mode)
            if native_mode in LINE_SCAN_MODES:
                raise RvcControllerError(
                    f"{native_mode} 为线扫模式，需要工件/相机配合运动采集，"
                    "普通拍照接口不支持，请改用线扫流程"
                )
            self.state.mode = native_mode

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            token = f"{stamp}_{self.capture_count + 1:06d}"

            # ── 采集：优先使用相机内部参数（SDK 推荐 Method 3：直接 Capture()）──
            # 如果需要覆盖参数（模式/曝光）则使用 LoadCaptureOptionParameters + 修改后 Capture(options)
            any_override = any([
                mode and mode != self.state.mode,
                exposure_2d is not None,
                exposure_3d is not None,
                projector_brightness is not None,
            ])
            if any_override:
                # Method 2：从相机读取当前参数，按需修改后采集
                try:
                    load_ret = self._dev.camera.LoadCaptureOptionParameters()
                    ok_load = load_ret[0] if isinstance(load_ret, tuple) else bool(load_ret)
                    options = load_ret[1] if isinstance(load_ret, tuple) and len(load_ret) > 1 else None
                except Exception:
                    ok_load, options = False, None

                if ok_load and options is not None:
                    # ⚠️ 必须始终覆盖 capture_mode：LoadCaptureOptionParameters() 读回的
                    # capture_mode 可能是相机内部不同枚举的整数值（如 2），直接传给
                    # Capture(options) 会报 "capture_mode[2] not support!"。
                    # 即使调用方没有指定 mode，也要用当前 state.mode 对应的枚举覆盖。
                    try:
                        mode_enum_attr = _MODE_ENUM_ATTR.get(native_mode)
                        if mode_enum_attr and hasattr(RVC, mode_enum_attr):
                            options.capture_mode = getattr(RVC, mode_enum_attr)
                        elif hasattr(options, "capture_mode"):
                            # fallback：用 Normal 枚举兜底，避免残留不支持的整数值
                            fallback_attr = _MODE_ENUM_ATTR.get("Normal")
                            if fallback_attr and hasattr(RVC, fallback_attr):
                                options.capture_mode = getattr(RVC, fallback_attr)
                    except Exception:
                        pass
                    if exposure_2d is not None and hasattr(options, "exposure_time_2d"):
                        options.exposure_time_2d = int(exposure_2d)
                    if exposure_3d is not None and hasattr(options, "exposure_time_3d"):
                        options.exposure_time_3d = int(exposure_3d)
                    if projector_brightness is not None and hasattr(options, "projector_brightness"):
                        options.projector_brightness = int(projector_brightness)
                    if hasattr(options, "enable_2d_in_capture"):
                        options.enable_2d_in_capture = save_2d
                    if hasattr(options, "calc_normal"):
                        options.calc_normal = False
                    ok = bool(self._dev.camera.Capture(options))
                else:
                    # 读取参数失败，退回无参采集
                    ok = bool(self._dev.camera.Capture())
            else:
                # Method 3（SDK 推荐）：直接使用相机内部参数采集
                ok = bool(self._dev.camera.Capture())

            if not ok:
                self.last_error = RVC.GetLastErrorMessage() or "Capture 返回 False"
                raise RvcControllerError(f"采集失败: {self.last_error}")

            scale = (
                float(pointcloud_scale)
                if pointcloud_scale is not None
                else self.state.pointcloud_scale
            )

            result: Dict[str, Any] = {
                "frame_index": self.capture_count + 1,
                "mode": native_mode,
                "family": self._dev.family,
                "sn": getattr(self._dev.info, "sn", ""),
                "name": getattr(self._dev.info, "name", ""),
                "ip": self._dev.ip,
            }

            # ── 点云：SDK 示例 pm_np = np.array(pm, copy=False).reshape(-1, 3) ──
            point_map = self._dev.camera.GetPointMap()
            if point_map is None or not point_map.IsValid():
                raise RvcControllerError("采集成功但点云无效，请检查曝光/模式或相机状态")
            # SDK 示例使用 copy=False；reshape(-1,3) 展平为 N×3，再按尺寸还原组织化
            pm_flat = np.array(point_map, copy=False).reshape(-1, 3).astype(np.float64)
            size = point_map.GetSize()
            width = int(getattr(size, "width", 0) or getattr(size, "cols", 0))
            height = int(getattr(size, "height", 0) or getattr(size, "rows", 0))
            if width > 0 and height > 0 and pm_flat.shape[0] == width * height:
                cloud = pm_flat.reshape(height, width, 3)
            else:
                # 兜底：保留展平格式
                cloud = pm_flat
            if scale != 1.0:
                cloud = cloud * scale
            result["width"] = width
            result["height"] = height
            if cloud.ndim == 3:
                result["point_count"] = int(np.isfinite(cloud).all(axis=2).sum())
            else:
                result["point_count"] = int(np.isfinite(cloud).all(axis=1).sum())

            npy_path = output_dir / f"pointcloud_{token}.npy"
            np.save(npy_path, cloud)
            result["pointcloud_npy"] = str(npy_path)

            if save_ply:
                ply_path = output_dir / f"pointcloud_{token}.ply"
                try:
                    # SDK 示例：pm.Save(path, RVC.PointMapUnitEnum.Millimeter, True)
                    saved = bool(
                        point_map.Save(str(ply_path), RVC.PointMapUnitEnum.Millimeter, True)
                    )
                except Exception:
                    try:
                        # 兼容旧版 SDK 不同枚举路径
                        saved = bool(
                            point_map.Save(
                                str(ply_path), RVC.PointMapTypeEnum.PointsOnly,
                                RVC.Millimeter, True,
                            )
                        )
                    except Exception:
                        saved = False
                if saved:
                    result["pointcloud_ply"] = str(ply_path)

            # ── 2D 图像：X2 需传 camera_id（SDK 示例：img = x2.GetImage(camera_id)）──
            if save_2d:
                try:
                    if self._dev.family == "X2":
                        # 优先 Extra，否则 Left（与 SDK QuickCaptureX2 示例一致）
                        info = self._dev.info
                        cam_id_for_img = (
                            RVC.CameraID_Extra
                            if getattr(info, "support_extra", False)
                            else RVC.CameraID_Left
                        )
                        image = self._dev.camera.GetImage(cam_id_for_img)
                    else:
                        image = self._dev.camera.GetImage()
                except Exception:
                    image = None

                if image is not None and image.IsValid():
                    img_size = image.GetSize()
                    img_w = int(getattr(img_size, "width", 0) or getattr(img_size, "cols", 0))
                    img_h = int(getattr(img_size, "height", 0) or getattr(img_size, "rows", 0))
                    img_path = output_dir / f"image2d_{token}.png"
                    if bool(image.SaveImage(str(img_path))):
                        result["image_2d"] = str(img_path)
                        result["image_width"] = img_w
                        result["image_height"] = img_h
                    image_array = np.array(image, copy=False)
                    result["image_shape"] = list(image_array.shape)
                else:
                    result["image_2d"] = ""

            self.capture_count += 1
            self.last_error = ""
            return result


    # ── 状态 ────────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        with self._lock:
            connected = False
            if self._dev is not None and self._dev.opened and self._dev.camera is not None:
                try:
                    if self._dev.family == "X1":
                        connected = bool(RVC.X1.IsOpen(self._dev.camera))
                    else:
                        connected = bool(RVC.X2.IsOpen(self._dev.camera))
                except Exception:
                    connected = False
            data: Dict[str, Any] = {
                "connected": connected,
                "streaming": connected,   # RVC 为单次触发采集，连接即视为可采
                "sdk_version": str(RVC.GetVersion()),
                "mode": self.state.mode,
                "exposure_2d": self.state.exposure_2d,
                "exposure_3d": self.state.exposure_3d,
                "projector_brightness": self.state.projector_brightness,
                "capture_count": self.capture_count,
                "last_error": self.last_error,
            }
            if self._dev is not None:
                data["device"] = self._info_dict(self._dev.device, self._dev.ip)
                data["family"] = self._dev.family
            return data
