"""
3D Depth Camera Rack Positioning Module

This package implements the 3D depth camera rack positioning system for precise
robot box packing. It uses point cloud data from depth cameras, hand-eye calibration,
and rigid feature extraction to calculate X/Y/Z compensation values.

Core Components:
- providers: Data providers (hand-eye calibration, robot pose, depth camera)
- processors: Point cloud processing and coordinate transformations
- algorithms: Positioning algorithms (support plane, edge, pillar detection)
- calculators: Compensation value calculation
- services: Main service orchestration

Architecture:
The system uses the Provider pattern to support both Mock and Real modes,
enabling development and testing without physical hardware.
"""

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
    ProviderFactory,
)
from .processors import PointCloudProcessor
from .algorithms import PositioningAlgorithm
from .calculators import CompensationCalculator
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
    "ProviderFactory",
    "PointCloudProcessor",
    "PositioningAlgorithm",
    "CompensationCalculator",
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
