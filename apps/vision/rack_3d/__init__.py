"""Camera providers and shared point-cloud registration API."""

__version__ = "1.0.0"

from .providers import (
    HandEyeProvider,
    RobotPoseProvider,
    DepthCameraProvider,
    MockHandEyeProvider,
    MockRobotPoseProvider,
    MockDepthCameraProvider,
    RealHandEyeProvider,
    RealRobotPoseProvider,
    RealDepthCameraProvider,
    OfflineHandEyeProvider,
    OfflineRobotPoseProvider,
    OfflineDepthCameraProvider,
    ProviderFactory,
)
from .processors import PointCloudProcessor
from .services import RackPositioningService
from .exceptions import (
    RackPositioningErrorCode,
    RackPositioningException,
    PointCloudError,
    CoordinateTransformError,
    ROIError,
    PositioningAlgorithmError,
    CompensationError,
    ConfigurationError,
)

__all__ = [
    "HandEyeProvider",
    "RobotPoseProvider",
    "DepthCameraProvider",
    "MockHandEyeProvider",
    "MockRobotPoseProvider",
    "MockDepthCameraProvider",
    "RealHandEyeProvider",
    "RealRobotPoseProvider",
    "RealDepthCameraProvider",
    "OfflineHandEyeProvider",
    "OfflineRobotPoseProvider",
    "OfflineDepthCameraProvider",
    "ProviderFactory",
    "PointCloudProcessor",
    "RackPositioningService",
    "RackPositioningErrorCode",
    "RackPositioningException",
    "PointCloudError",
    "CoordinateTransformError",
    "ROIError",
    "PositioningAlgorithmError",
    "CompensationError",
    "ConfigurationError",
]
