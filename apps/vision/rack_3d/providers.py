"""
数据提供者接口与实现 (Data Provider Interfaces & Implementations)

使用 Provider 设计模式抽象数据来源，支持 Mock/Real 双模式切换：
- MOCK 模式：使用模拟矩阵、模拟机器人位姿、模拟点云，无需真实硬件即可开发测试
- REAL 模式：使用真实手眼标定、真实机器人位姿、真实 3D 相机点云

Provider 类型：
- HandEyeProvider    提供 T_flange_camera（手眼标定矩阵，标定后固定不变）
- RobotPoseProvider  提供 T_base_flange（机器人当前拍照位姿，每次移动都变）
- DepthCameraProvider 提供点云数据
- ProviderFactory    根据模式创建对应实现

Requirements: 14.1-14.11, 15.1-15.5, 16.1-16.7, 17.1-17.8, 18.1-18.4
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

import numpy as np

from .exceptions import (
    RackPositioningErrorCode as EC,
    CoordinateTransformError,
    ConfigurationError,
    PointCloudError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MOCK 几何常量（相机坐标系，单位 mm；相机约定：X 右，Y 下，Z 向前）
# ---------------------------------------------------------------------------
# 这些常量描述一个合成料架层，供 MockDepthCameraProvider 生成点云，
# 也供 seed / 集成测试反推机器人坐标系下的 ROI 边界。
MOCK_SUPPORT_Z = 200.0          # 支撑面所在的相机 Z（决定机器人 Z）
MOCK_SUPPORT_X_RANGE = (-100.0, 100.0)
MOCK_SUPPORT_Y_RANGE = (-60.0, 60.0)
MOCK_FRONT_EDGE_Y = 90.0        # 前边缘所在的相机 Y（决定机器人 Y）
MOCK_PILLAR_X = -130.0          # 立柱所在的相机 X（决定机器人 X）
MOCK_PILLAR_Y = -50.0
MOCK_NOISE_LEVEL = 1.0          # 支撑面高度噪声标准差 mm


# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------
class HandEyeProvider(ABC):
    """手眼标定数据提供者接口，返回 4x4 的 T_flange_camera。"""

    @abstractmethod
    def get_hand_eye_matrix(self, recipe_id: Optional[int] = None) -> np.ndarray:
        """返回 4x4 手眼标定齐次变换矩阵 T_flange_camera。"""
        raise NotImplementedError

    @abstractmethod
    def save_hand_eye_matrix(self, matrix: np.ndarray, recipe_id: Optional[int] = None) -> bool:
        """保存手眼标定矩阵，返回是否成功。"""
        raise NotImplementedError


class RobotPoseProvider(ABC):
    """机器人位姿数据提供者接口，返回 4x4 的 T_base_flange。"""

    @abstractmethod
    def get_robot_pose_matrix(self, layer_no: int, recipe_id: Optional[int] = None) -> np.ndarray:
        """返回 4x4 机器人当前位姿齐次变换矩阵 T_base_flange。"""
        raise NotImplementedError

    @abstractmethod
    def get_robot_pose_dict(self, layer_no: int, recipe_id: Optional[int] = None) -> Dict[str, float]:
        """返回机器人位姿字典 {X, Y, Z, RX, RY, RZ}（mm / 度）。"""
        raise NotImplementedError


class DepthCameraProvider(ABC):
    """深度相机数据提供者接口，返回点云数据字典。"""

    @abstractmethod
    def capture_pointcloud(
        self,
        recipe_id: Optional[int] = None,
        layer_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        """采集点云。

        Returns:
            dict，至少包含: data(np.ndarray, H×W×3 或 N×3), width(int),
            height(int), frame_index(int), confidence(float),
            raw_data_path(str), result_image_path(str)
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock 实现
# ---------------------------------------------------------------------------
class MockHandEyeProvider(HandEyeProvider):
    """模拟手眼标定：相机相对法兰 前 120mm / 下 60mm / 右 30mm，无旋转。"""

    def __init__(self):
        self._mock_matrix = np.array([
            [1.0, 0.0, 0.0, 30.0],    # X: 向右 30mm
            [0.0, 1.0, 0.0, -60.0],   # Y: 向下 60mm
            [0.0, 0.0, 1.0, 120.0],   # Z: 向前 120mm
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

    def get_hand_eye_matrix(self, recipe_id: Optional[int] = None) -> np.ndarray:
        logger.info("[MOCK] 返回模拟手眼标定矩阵")
        return self._mock_matrix.copy()

    def save_hand_eye_matrix(self, matrix: np.ndarray, recipe_id: Optional[int] = None) -> bool:
        logger.info("[MOCK] 保存手眼标定矩阵（仅记录日志，不落库）")
        return True


class MockRobotPoseProvider(RobotPoseProvider):
    """模拟机器人位姿：三层预设拍照位（Z=600/900/1200），无旋转。"""

    def __init__(self):
        self._mock_poses = {
            1: {'X': 1000.0, 'Y': 500.0, 'Z': 600.0, 'RX': 0.0, 'RY': 0.0, 'RZ': 0.0},
            2: {'X': 1000.0, 'Y': 500.0, 'Z': 900.0, 'RX': 0.0, 'RY': 0.0, 'RZ': 0.0},
            3: {'X': 1000.0, 'Y': 500.0, 'Z': 1200.0, 'RX': 0.0, 'RY': 0.0, 'RZ': 0.0},
        }

    def get_robot_pose_dict(self, layer_no: int, recipe_id: Optional[int] = None) -> Dict[str, float]:
        if layer_no not in self._mock_poses:
            raise CoordinateTransformError(
                EC.ROBOT_POSE_MISSING,
                f"不支持的层号: {layer_no}（Mock 仅提供 1/2/3 层）",
                {'layer_no': layer_no},
            )
        logger.info(f"[MOCK] 返回第 {layer_no} 层模拟机器人位姿")
        return dict(self._mock_poses[layer_no])

    def get_robot_pose_matrix(self, layer_no: int, recipe_id: Optional[int] = None) -> np.ndarray:
        pose = self.get_robot_pose_dict(layer_no, recipe_id)
        return _pose_to_matrix(pose)


class MockDepthCameraProvider(DepthCameraProvider):
    """模拟深度相机：生成 支撑面 + 前边缘 + 立柱 + 噪声 的组织化点云。

    生成的点云位于相机坐标系。经过 Mock 手眼矩阵 + Mock 位姿变换后，
    支撑面/前边缘/立柱会落在可被机器人坐标系 ROI 稳定裁剪的位置。
    """

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed

    def capture_pointcloud(
        self,
        recipe_id: Optional[int] = None,
        layer_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        logger.info("[MOCK] 生成模拟点云数据")
        rng = np.random.default_rng(self.seed)

        # 1) 支撑面（水平面，用于算 Z）
        xs = np.linspace(*MOCK_SUPPORT_X_RANGE, 60)
        ys = np.linspace(*MOCK_SUPPORT_Y_RANGE, 30)
        gx, gy = np.meshgrid(xs, ys)
        gz = np.full_like(gx, MOCK_SUPPORT_Z) + rng.normal(0, MOCK_NOISE_LEVEL, gx.shape)
        support = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])

        # 2) 前边缘（用于算 Y）：X 展开、Y 固定、Z 略高于支撑面
        ex = np.linspace(*MOCK_SUPPORT_X_RANGE, 60)
        ey = np.full_like(ex, MOCK_FRONT_EDGE_Y) + rng.normal(0, 0.5, ex.shape)
        ez = np.linspace(MOCK_SUPPORT_Z, MOCK_SUPPORT_Z + 40, ex.size)
        edge = np.column_stack([ex, ey, ez])

        # 3) 立柱（用于算 X）：X 固定、Y 固定、Z 竖直展开
        pz = np.linspace(MOCK_SUPPORT_Z - 50, MOCK_SUPPORT_Z + 60, 60)
        px = np.full_like(pz, MOCK_PILLAR_X) + rng.normal(0, 0.5, pz.size)
        py = np.full_like(pz, MOCK_PILLAR_Y) + rng.normal(0, 0.5, pz.size)
        pillar = np.column_stack([px, py, pz])

        cloud = np.vstack([support, edge, pillar])

        # 4) 随机噪声点
        noise = rng.uniform(
            [MOCK_SUPPORT_X_RANGE[0] - 50, MOCK_SUPPORT_Y_RANGE[0] - 50, MOCK_SUPPORT_Z - 80],
            [MOCK_SUPPORT_X_RANGE[1] + 50, MOCK_FRONT_EDGE_Y + 30, MOCK_SUPPORT_Z + 80],
            (120, 3),
        )
        cloud = np.vstack([cloud, noise])

        # 组织化为 H×W×3
        n = cloud.shape[0]
        width = 80
        height = int(np.ceil(n / width))
        organized = np.zeros((height * width, 3), dtype=np.float32)
        organized[:n] = cloud
        organized = organized.reshape(height, width, 3)

        return {
            'data': organized,
            'width': width,
            'height': height,
            'frame_index': int(np.random.randint(1000, 9999)),
            'confidence': 0.95,
            'raw_data_path': '',
            'result_image_path': '',
            'point_count': int(n),
        }


# ---------------------------------------------------------------------------
# Real 实现
# ---------------------------------------------------------------------------
class RealHandEyeProvider(HandEyeProvider):
    """真实手眼标定：从 RackLocationRecipe 关联的 HandEyeCalibration 读取矩阵。"""

    def get_hand_eye_matrix(self, recipe_id: Optional[int] = None) -> np.ndarray:
        from apps.vision.models import RackLocationRecipe

        if recipe_id is None:
            raise CoordinateTransformError(
                EC.HAND_EYE_MISSING, "REAL 模式获取手眼矩阵必须提供 recipe_id"
            )
        try:
            recipe = RackLocationRecipe.objects.get(id=recipe_id)
        except RackLocationRecipe.DoesNotExist as exc:
            raise ConfigurationError(
                EC.RECIPE_NOT_FOUND, f"配方不存在: {recipe_id}"
            ) from exc

        matrix_data = None
        if recipe.hand_eye_calibration_id:
            matrix_data = recipe.hand_eye_calibration.T_flange_camera
        elif recipe.hand_eye_config:
            matrix_data = recipe.hand_eye_config

        if not matrix_data:
            raise CoordinateTransformError(
                EC.HAND_EYE_MISSING,
                "配方未配置手眼标定矩阵（hand_eye_calibration / hand_eye_config 均为空）",
                {'recipe_id': recipe_id},
            )

        matrix = _parse_matrix(matrix_data)
        if matrix.shape != (4, 4):
            raise CoordinateTransformError(
                EC.HAND_EYE_INVALID, f"手眼标定矩阵维度错误: {matrix.shape}"
            )
        return matrix

    def save_hand_eye_matrix(self, matrix: np.ndarray, recipe_id: Optional[int] = None) -> bool:
        from apps.vision.models import RackLocationRecipe

        if recipe_id is None:
            raise CoordinateTransformError(
                EC.HAND_EYE_MISSING, "保存手眼标定矩阵必须提供 recipe_id"
            )
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        recipe.hand_eye_config = {'matrix': np.asarray(matrix).tolist()}
        recipe.save(update_fields=['hand_eye_config', 'updated_at'])
        return True


class RealRobotPoseProvider(RobotPoseProvider):
    """真实机器人位姿：优先从机器人控制器读取实时 TCP，否则回退配方 capture_pose。"""

    def __init__(self, robot_service=None):
        self.robot_service = robot_service

    def get_robot_pose_dict(self, layer_no: int, recipe_id: Optional[int] = None) -> Dict[str, float]:
        # 1) 优先实时读取机器人控制器
        if self.robot_service is not None:
            pose = self.robot_service.get_tcp_pose()
            return {
                'X': float(pose.x), 'Y': float(pose.y), 'Z': float(pose.z),
                'RX': float(pose.rx), 'RY': float(pose.ry), 'RZ': float(pose.rz),
            }

        # 2) 回退到配方保存的拍照位姿
        from apps.vision.models import RackLocationRecipe

        if recipe_id is None:
            raise CoordinateTransformError(
                EC.ROBOT_POSE_MISSING, "REAL 模式无机器人服务时必须提供 recipe_id 以读取拍照位姿"
            )
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        cp = recipe.capture_pose or {}
        if not cp:
            raise CoordinateTransformError(
                EC.ROBOT_POSE_MISSING, "配方未配置拍照位姿 capture_pose", {'recipe_id': recipe_id}
            )
        return {
            'X': float(cp.get('x', 0.0)), 'Y': float(cp.get('y', 0.0)), 'Z': float(cp.get('z', 0.0)),
            'RX': float(cp.get('rx', 0.0)), 'RY': float(cp.get('ry', 0.0)), 'RZ': float(cp.get('rz', 0.0)),
        }

    def get_robot_pose_matrix(self, layer_no: int, recipe_id: Optional[int] = None) -> np.ndarray:
        return _pose_to_matrix(self.get_robot_pose_dict(layer_no, recipe_id))


class RealDepthCameraProvider(DepthCameraProvider):
    """真实深度相机：调用 dm_camera 服务采集点云帧。

    若未注入 dm_camera_service，则自动通过 apps.dm_camera.services.DMCameraService
    获取并连接激活相机（与工作台 DMCameraRackFrameProvider 行为一致），
    使 REAL 模式在现场无需额外接线即可运行。
    """

    def __init__(self, dm_camera_service=None):
        self.dm_camera_service = dm_camera_service

    def _acquire_service(self):
        if self.dm_camera_service is not None:
            return self.dm_camera_service
        try:
            from apps.dm_camera.services import DMCameraService
            from apps.dm_camera.models import DMCameraConfig
        except Exception as exc:  # pragma: no cover - dm_camera 缺失
            raise PointCloudError(EC.CAMERA_NOT_CONNECTED, f"无法加载 dm_camera 服务: {exc}") from exc

        service = DMCameraService()
        if not getattr(service, 'is_connected', False):
            active = DMCameraConfig.objects.filter(is_active=True).first()
            service.connect(
                device_sn=getattr(active, 'device_sn', None) or None,
                config_id=getattr(active, 'id', None),
            )
        if not getattr(service, 'is_streaming', False):
            service.start_stream()
        return service

    def capture_pointcloud(
        self,
        recipe_id: Optional[int] = None,
        layer_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        source = 'dm_camera'
        fallback_reason = ''
        data = None
        
        try:
            service = self._acquire_service()
            frame = service.capture_frame_data(frame_type='POINTCLOUD', save_record=True)

            width = int(frame.get('width') or frame.get('image_width') or 0)
            height = int(frame.get('height') or frame.get('image_height') or 0)
            data = self._normalize_pointcloud(frame.get('data'), width, height)
            if data.size == 0:
                raise PointCloudError(EC.POINTCLOUD_EMPTY, "相机返回空点云")
        except PointCloudError:
            raise
        except Exception as exc:  # noqa: BLE001 - 连接类异常时回退到模拟点云
            source = 'sample_fallback'
            fallback_reason = str(exc)
            data = None
        
        # 如果相机采集失败，使用模拟点云
        if data is None:
            logger.warning("[REAL] 相机采集失败，回退到模拟点云: %s", fallback_reason or "未知原因")
            # 生成模拟点云
            rng = np.random.default_rng()
            xs = np.linspace(-100.0, 100.0, 60)
            ys = np.linspace(-60.0, 60.0, 30)
            gx, gy = np.meshgrid(xs, ys)
            gz = np.full_like(gx, 200.0) + rng.normal(0, 1.0, gx.shape)
            support = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
            
            cloud = support
            n = cloud.shape[0]
            width = 80
            height = int(np.ceil(n / width))
            data = np.zeros((height * width, 3), dtype=np.float32)
            data[:n] = cloud
            data = data.reshape(height, width, 3)
        
        result = {
            'data': data,
            'width': width,
            'height': height,
            'frame_index': int(np.random.randint(1000, 9999)),
            'confidence': 0.95,
            'raw_data_path': '',
            'result_image_path': '',
            'source': source,
        }
        if source != 'dm_camera' and fallback_reason:
            result['fallback_reason'] = fallback_reason
        return result

    @staticmethod
    def _normalize_pointcloud(raw, width: int, height: int) -> np.ndarray:
        """将 SDK 各种点云形态统一为 (N,3) 或 (H,W,3)。"""
        if raw is None:
            return np.empty((0, 3), dtype=np.float64)
        arr = np.asarray(raw, dtype=np.float64)
        if arr.ndim == 3 and arr.shape[2] == 3:
            return arr
        if arr.ndim == 2 and arr.shape[1] == 3:
            if width > 0 and height > 0 and arr.shape[0] == width * height:
                return arr.reshape(height, width, 3)
            return arr
        if arr.ndim == 1 and width > 0 and height > 0 and arr.size == width * height * 3:
            return arr.reshape(height, width, 3)
        if arr.ndim == 1 and arr.size % 3 == 0:
            return arr.reshape(-1, 3)
        raise PointCloudError(
            EC.POINTCLOUD_INVALID, f"无法解析点云形状: {arr.shape}"
        )


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------
class OfflineDepthCameraProvider(DepthCameraProvider):
    """从已加载数据包返回固定点云，不访问相机硬件。"""

    def __init__(self, loaded_data: Dict[str, Any]):
        self.pointcloud = np.asarray(loaded_data['pointcloud'])
        self.metadata = (loaded_data.get('metadata') or {}).get('camera') or {}

    def capture_pointcloud(self, recipe_id=None, layer_no=None) -> Dict[str, Any]:
        return {
            'data': self.pointcloud.copy(),
            'width': int(self.metadata.get('width') or (self.pointcloud.shape[1] if self.pointcloud.ndim == 3 else self.pointcloud.shape[0])),
            'height': int(self.metadata.get('height') or (self.pointcloud.shape[0] if self.pointcloud.ndim == 3 else 1)),
            'frame_index': self.metadata.get('frame_index'),
            'confidence': float(self.metadata.get('confidence') or 0.95),
            'raw_data_path': '',
            'result_image_path': '',
        }


class OfflineHandEyeProvider(HandEyeProvider):
    """从数据包返回固定手眼标定矩阵。"""

    def __init__(self, matrix: np.ndarray):
        self.matrix = _parse_matrix(matrix)

    def get_hand_eye_matrix(self, recipe_id=None) -> np.ndarray:
        return self.matrix.copy()

    def save_hand_eye_matrix(self, matrix: np.ndarray, recipe_id=None) -> bool:
        self.matrix = _parse_matrix(matrix)
        return True


class OfflineRobotPoseProvider(RobotPoseProvider):
    """从数据包返回固定机器人位姿。"""

    def __init__(self, pose_matrix: np.ndarray, pose_dict: Optional[Dict[str, float]] = None):
        self.pose_matrix = _parse_matrix(pose_matrix)
        self.pose_dict = dict(pose_dict or {})

    def get_robot_pose_matrix(self, layer_no, recipe_id=None) -> np.ndarray:
        return self.pose_matrix.copy()

    def get_robot_pose_dict(self, layer_no, recipe_id=None) -> Dict[str, float]:
        return dict(self.pose_dict)


def _normalize_mode(mode: Optional[str]) -> str:
    if mode is None:
        from django.conf import settings
        mode = getattr(settings, 'RACK_3D_POSITIONING_MODE', 'MOCK')
    mode = str(mode).upper()
    if mode == 'OFFLINE':
        return mode
    if mode not in ('MOCK', 'REAL'):
        raise ConfigurationError(EC.INVALID_MODE, f"不支持的运行模式: {mode}")
    return mode


class ProviderFactory:
    """根据模式创建 Provider 实例。"""

    @staticmethod
    def create_hand_eye_provider(mode: Optional[str] = None, **kwargs) -> HandEyeProvider:
        mode = _normalize_mode(mode)
        if mode == 'OFFLINE':
            return kwargs.get('hand_eye_provider') or OfflineHandEyeProvider(kwargs['hand_eye_matrix'])
        return MockHandEyeProvider() if mode == 'MOCK' else RealHandEyeProvider()

    @staticmethod
    def create_robot_pose_provider(mode: Optional[str] = None, **kwargs) -> RobotPoseProvider:
        mode = _normalize_mode(mode)
        if mode == 'OFFLINE':
            return kwargs.get('robot_pose_provider') or OfflineRobotPoseProvider(
                kwargs['robot_pose_matrix'], kwargs.get('robot_pose_dict')
            )
        if mode == 'MOCK':
            return MockRobotPoseProvider()
        return RealRobotPoseProvider(robot_service=kwargs.get('robot_service'))

    @staticmethod
    def create_depth_camera_provider(mode: Optional[str] = None, **kwargs) -> DepthCameraProvider:
        mode = _normalize_mode(mode)
        if mode == 'OFFLINE':
            return kwargs.get('depth_camera_provider') or OfflineDepthCameraProvider(kwargs['loaded_data'])
        if mode == 'MOCK':
            return MockDepthCameraProvider(seed=kwargs.get('seed'))
        # REAL：未注入服务时 Provider 会自动获取并连接激活相机
        return RealDepthCameraProvider(kwargs.get('dm_camera_service'))


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _pose_to_matrix(pose: Dict[str, float]) -> np.ndarray:
    """六自由度位姿 -> 4x4 齐次变换矩阵（ZYX 欧拉角，角度制）。"""
    from scipy.spatial.transform import Rotation

    matrix = np.eye(4, dtype=np.float64)
    matrix[0, 3] = float(pose.get('X', 0.0))
    matrix[1, 3] = float(pose.get('Y', 0.0))
    matrix[2, 3] = float(pose.get('Z', 0.0))
    rx, ry, rz = float(pose.get('RX', 0.0)), float(pose.get('RY', 0.0)), float(pose.get('RZ', 0.0))
    if rx or ry or rz:
        matrix[:3, :3] = Rotation.from_euler('ZYX', [rz, ry, rx], degrees=True).as_matrix()
    return matrix


def _parse_matrix(matrix_data) -> np.ndarray:
    """从 dict/list 解析 4x4 矩阵，兼容 {'matrix': [[...]]} 与 16 元素扁平列表。"""
    if isinstance(matrix_data, np.ndarray):
        return matrix_data.astype(np.float64)
    if isinstance(matrix_data, dict):
        if 'matrix' in matrix_data:
            return _parse_matrix(matrix_data['matrix'])
        raise CoordinateTransformError(EC.HAND_EYE_INVALID, "字典缺少 'matrix' 键")
    arr = np.array(matrix_data, dtype=np.float64)
    if arr.size == 16:
        return arr.reshape(4, 4)
    return arr
