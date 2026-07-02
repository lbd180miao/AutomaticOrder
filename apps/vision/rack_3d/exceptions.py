"""
异常与错误码定义 (Exceptions & Error Codes)

统一的错误码体系和异常类层次结构，供 rack_3d 各模块使用。
错误码分段：
- 1xxx 点云采集
- 2xxx 坐标转换
- 3xxx ROI
- 4xxx 定位算法
- 5xxx 补偿计算
- 6xxx PLC 通讯

Requirements: 22.1-22.8
"""

from typing import Optional, Dict, Any


class RackPositioningErrorCode:
    """料架定位统一错误码常量。"""

    # 点云采集错误 (1xxx)
    CAMERA_NOT_CONNECTED = 'E1001'
    CAMERA_TIMEOUT = 'E1002'
    POINTCLOUD_INVALID = 'E1003'
    POINTCLOUD_EMPTY = 'E1004'

    # 坐标转换错误 (2xxx)
    HAND_EYE_MISSING = 'E2001'
    HAND_EYE_INVALID = 'E2002'
    ROBOT_POSE_MISSING = 'E2003'
    TRANSFORM_FAILED = 'E2004'

    # ROI 错误 (3xxx)
    ROI_NOT_FOUND = 'E3001'
    ROI_INVALID_BOUNDS = 'E3002'
    ROI_INSUFFICIENT_POINTS = 'E3003'

    # 定位算法错误 (4xxx)
    RANSAC_FAILED = 'E4001'
    PLANE_FIT_LOW_QUALITY = 'E4002'
    EDGE_DETECTION_FAILED = 'E4003'
    PILLAR_DETECTION_FAILED = 'E4004'
    LOW_CONFIDENCE = 'E4005'

    # 补偿计算错误 (5xxx)
    OFFSET_OUT_OF_RANGE = 'E5001'
    STANDARD_VALUE_MISSING = 'E5002'

    # PLC 通讯错误 (6xxx)
    PLC_NOT_CONNECTED = 'E6001'
    PLC_WRITE_FAILED = 'E6002'

    # 配置/通用错误 (9xxx)
    INVALID_MODE = 'E9001'
    RECIPE_NOT_FOUND = 'E9002'


class RackPositioningException(Exception):
    """料架定位异常基类，携带错误码、消息和详情。"""

    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{error_code}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.error_code,
            'message': self.message,
            'details': self.details,
        }


class PointCloudError(RackPositioningException):
    """点云采集/解析相关错误。"""


class CoordinateTransformError(RackPositioningException):
    """坐标转换错误。"""


class ROIError(RackPositioningException):
    """ROI 配置或裁剪错误。"""


class PositioningAlgorithmError(RackPositioningException):
    """定位算法错误（平面拟合、边缘/立柱检测）。"""


class CompensationError(RackPositioningException):
    """补偿计算错误。"""


class ConfigurationError(RackPositioningException):
    """配置错误（模式无效、配方缺失等）。"""
