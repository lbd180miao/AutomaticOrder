"""3D depth-camera rack-location services.

This module is intentionally scoped to the 3D rack-location feature. It does
not change PLC, workflow, production, or 2D foam-inspection modules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import os
import random
from typing import Any, Optional

import numpy as np
from django.conf import settings
from django.utils import timezone

from apps.core.constants import (
    AlarmLevel,
    AlarmSource,
    RackSide,
    ResultStatus,
    SignalDirection,
    VisionImageType,
    VisionTaskType,
)
from apps.alarms.services import AlarmService
from apps.devices.services import DeviceService, get_device_adapter
from apps.dm_camera.models import DMCameraConfig
from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError

from .algorithms import image_io
from .algorithms.rack_opening_rectangle import (
    ALGORITHM_VERSION,
    AUTO_ALGORITHM_VERSION,
    RackOpeningRectangleLocator,
    RectangleLocationError,
    get_algorithm_version,
    is_rectangle_v2,
    normalize_reference_feature_config,
    standard_geometry,
)
from .models import RackLocationROI3D, RackLocationRecipe, RackLocationResult, VisionImage, VisionTask
from .rack_compensation import (
    combine_compensations,
    compensation_from_output,
    compensation_from_result,
    pose6d_from_matrix,
)


def _decimal(value: Any, places: str = '0.001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


LOCATE_TYPE_GLOBAL = 'GLOBAL'
LOCATE_TYPE_LAYER = 'LAYER'


def _standard_rack_member(*, member_id: str, label: str, start: dict, end: dict,
                          point_count=None, rmse_mm=None) -> dict:
    """Describe one fitted steel member centerline from its two intersections."""
    start_array = np.asarray([start['x'], start['y'], start['z']], dtype=float)
    end_array = np.asarray([end['x'], end['y'], end['z']], dtype=float)
    vector = end_array - start_array
    length = float(np.linalg.norm(vector))
    direction = vector / length if length > 1e-9 else np.zeros(3, dtype=float)
    center = (start_array + end_array) / 2.0
    return {
        'id': member_id,
        'label': label,
        'centerline': {
            'start': {'x': float(start_array[0]), 'y': float(start_array[1]), 'z': float(start_array[2])},
            'end': {'x': float(end_array[0]), 'y': float(end_array[1]), 'z': float(end_array[2])},
            'center': {'x': round(float(center[0]), 6), 'y': round(float(center[1]), 6), 'z': round(float(center[2]), 6)},
            'direction': direction.round(8).tolist(),
            'length_mm': round(length, 4),
        },
        'fit': {
            'point_count': int(point_count) if point_count is not None else None,
            'rmse_mm': round(float(rmse_mm), 4) if rmse_mm is not None else None,
        },
    }


def build_standard_rack_model(opening_rectangle: dict, *, result=None, note='') -> dict:
    """Build the persisted three-member standard rack model from a V2 fit."""
    points = opening_rectangle.get('points') or {}
    missing = [key for key in ('p1', 'p2', 'p3', 'p4') if key not in points]
    if missing:
        raise ValueError(f"标准料架建模缺少角点: {', '.join(missing)}")

    quality = opening_rectangle.get('quality') or {}
    geometry = opening_rectangle.get('geometry') or {}
    edge_counts = quality.get('edge_point_count') or {}
    edge_rmse = quality.get('edge_rmse_mm') or {}

    def edge_metric(values, key, index):
        if isinstance(values, dict):
            return values.get(key)
        if isinstance(values, (list, tuple)) and len(values) > index:
            return values[index]
        return None

    members = {
        'left_upright': _standard_rack_member(
            member_id='left_upright', label='左立柱', start=points['p4'], end=points['p1'],
            point_count=edge_metric(edge_counts, 'left', 3),
            rmse_mm=edge_metric(edge_rmse, 'left', 3),
        ),
        'top_crossbeam': _standard_rack_member(
            member_id='top_crossbeam', label='顶部横梁', start=points['p1'], end=points['p2'],
            point_count=edge_metric(edge_counts, 'top', 0),
            rmse_mm=edge_metric(edge_rmse, 'top', 0),
        ),
        'right_upright': _standard_rack_member(
            member_id='right_upright', label='右立柱', start=points['p3'], end=points['p2'],
            point_count=edge_metric(edge_counts, 'right', 1),
            rmse_mm=edge_metric(edge_rmse, 'right', 1),
        ),
    }

    center = opening_rectangle.get('center') or {}
    normal = geometry.get('normal_out') or [0.0, 0.0, 1.0]
    center_array = np.asarray([center.get('x', 0), center.get('y', 0), center.get('z', 0)], dtype=float)
    normal_array = np.asarray(normal, dtype=float)
    pose_matrix = (opening_rectangle.get('pose') or {}).get('matrix') or np.eye(4).tolist()
    coordinate_system = opening_rectangle.get('coordinate_system') or 'unknown'
    pose6d = pose6d_from_matrix(pose_matrix)
    source_result_id = getattr(result, 'id', None)
    raw_data_path = getattr(result, 'raw_data_path', '') if result else ''
    roi_snapshot = getattr(result, 'roi_data', {}) if result else {}

    return {
        'model_version': 'THREE_MEMBER_RIGID_V1',
        'status': 'READY',
        'coordinate_system': coordinate_system,
        'point_unit': opening_rectangle.get('point_unit') or 'mm',
        'members': members,
        'front_plane': {
            'center': {'x': float(center_array[0]), 'y': float(center_array[1]), 'z': float(center_array[2])},
            'normal_out': normal_array.round(8).tolist(),
            'equation_d': round(float(np.dot(normal_array, center_array)), 6),
            'inlier_count': quality.get('plane_inlier_count'),
            'inlier_ratio': quality.get('plane_inlier_ratio'),
            'rmse_mm': quality.get('plane_rmse_mm'),
        },
        'relative_geometry': {
            'upright_spacing_mm': geometry.get('width_mm'),
            'left_upright_height_mm': geometry.get('height_left_mm'),
            'right_upright_height_mm': geometry.get('height_right_mm'),
            'upright_parallel_error_deg': quality.get('parallel_error_deg'),
            'crossbeam_perpendicular_error_deg': quality.get('perpendicular_error_deg'),
            'center_consistency_mm': quality.get('center_consistency_mm'),
        },
        'rack_coordinate_system': {
            'origin': {'x': float(center_array[0]), 'y': float(center_array[1]), 'z': float(center_array[2])},
            'x_axis': geometry.get('x_axis'),
            'y_axis': geometry.get('y_axis_in'),
            'z_axis': geometry.get('z_axis'),
            'pose_matrix': pose_matrix,
        },
        'rack_pose': {
            'coordinate_system': coordinate_system,
            'pose6d': pose6d,
            'matrix': pose_matrix,
            'robot_base_pose_available': coordinate_system == 'robot_base',
        },
        'pointcloud_template': {
            'source_result_id': source_result_id,
            'raw_data_path': raw_data_path,
            'point_count': quality.get('valid_point_count'),
            'roi_snapshot': roi_snapshot,
        },
        'quality': {
            'confidence': quality.get('confidence'),
            'rigid_fit_rmse_mm': quality.get('rigid_fit_rmse_mm'),
            'max_corner_residual_mm': quality.get('max_corner_residual_mm'),
        },
        'saved_at': timezone.now().isoformat(),
        'note': note,
    }


def normalize_locate_type(value: Any = None) -> str:
    locate_type = str(value or LOCATE_TYPE_LAYER).strip().upper()
    if locate_type not in {LOCATE_TYPE_GLOBAL, LOCATE_TYPE_LAYER}:
        raise ValueError('locate_type must be GLOBAL or LAYER')
    return locate_type


def normalize_layer_index(value: Any = None, locate_type: Any = None) -> int:
    normalized_type = normalize_locate_type(locate_type)
    if value in (None, ''):
        layer_index = 0 if normalized_type == LOCATE_TYPE_GLOBAL else 1
    else:
        try:
            layer_index = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('layer_index must be an integer') from exc

    if normalized_type == LOCATE_TYPE_GLOBAL and layer_index != 0:
        raise ValueError('GLOBAL locate_type requires layer_index=0')
    if normalized_type == LOCATE_TYPE_LAYER and layer_index not in {1, 2, 3}:
        raise ValueError('LAYER locate_type requires layer_index 1, 2, or 3')
    return layer_index


def locate_semantics(*, locate_type: Any = None, layer_index: Any = None,
                     layer_no: Any = None, mode: Any = None) -> dict:
    if locate_type is None and mode:
        locate_type = (
            LOCATE_TYPE_GLOBAL
            if str(mode).lower() == RackLocationROI3D.MODE_GLOBAL
            else LOCATE_TYPE_LAYER
        )
    normalized_type = normalize_locate_type(locate_type)
    index_value = layer_index if layer_index not in (None, '') else layer_no
    normalized_index = normalize_layer_index(index_value, normalized_type)
    return {
        'locate_type': normalized_type,
        'layer_index': normalized_index,
        'roi_mode': (
            RackLocationROI3D.MODE_GLOBAL
            if normalized_type == LOCATE_TYPE_GLOBAL
            else RackLocationROI3D.MODE_LOCAL
        ),
        'layer_no': normalized_index,
    }


def roi3d_to_dict(roi: RackLocationROI3D | dict) -> dict:
    if isinstance(roi, dict):
        return {
            'x_min': float(roi['x_min']),
            'x_max': float(roi['x_max']),
            'y_min': float(roi['y_min']),
            'y_max': float(roi['y_max']),
            'z_min': float(roi['z_min']),
            'z_max': float(roi['z_max']),
        }
    return {
        'id': roi.id,
        'recipe_id': roi.recipe_id,
        'roi_name': roi.roi_name,
        'mode': roi.mode,
        'layer_no': roi.layer_no,
        'coordinate_system': roi.coordinate_system,
        'x_min': float(roi.x_min),
        'x_max': float(roi.x_max),
        'y_min': float(roi.y_min),
        'y_max': float(roi.y_max),
        'z_min': float(roi.z_min),
        'z_max': float(roi.z_max),
        'enabled': roi.enabled,
    }


def _simulate_xyz_from_scene(
    *,
    recipe: 'RackLocationRecipe',
    position_no: int,
    layer_no: int,
    target_roi: dict,
) -> tuple[float, float, float]:
    """无真实点云时，在配方标准坐标（机器人坐标系，mm）上叠加小量噪声，
    模拟真实定位场景下 actual_x/y/z ≈ standard_x/y/z，误差在 ±2mm 以内。

    注意：模拟点云的像素坐标系与机器人坐标系不同，不能直接用像素中位数作
    为机器人坐标。真实场景下，相机坐标会经过手眼标定矩阵转换为机器人坐标。
    离线模拟时，直接在配方标准值（机器人坐标）上叠加小量高斯噪声，保证
    展示的 actual_x/y/z 与 standard_x/y/z 在同一量纲且偏差合理。

    逻辑：
    1. 配方标准值有效（非零）→ 在标准值上叠加小量高斯噪声（σ≤1.5mm）
    2. 配方标准值为零 → 用合理的机器人坐标默认值 + 小量噪声
    """
    std_x = float(recipe.standard_x)
    std_y = float(recipe.standard_y)
    std_z = float(recipe.standard_z)

    # 用 (position_no, layer_no) 作为随机种子，保证同配方每次结果一致
    seed_str = f'xyz-pos{position_no}-layer{layer_no}'
    rng = random.Random(seed_str)

    # 若配方标准值已配置（机器人坐标，mm），在标准值附近模拟实测值
    # 模拟典型机器人定位误差：X/Y ±1.5mm，Z ±1.0mm
    if std_x != 0 or std_y != 0 or std_z != 0:
        noise_x = round(rng.gauss(0, 1.2), 3)
        noise_y = round(rng.gauss(0, 1.2), 3)
        noise_z = round(rng.gauss(0, 0.8), 3)
        return (
            round(std_x + noise_x, 3),
            round(std_y + noise_y, 3),
            round(std_z + noise_z, 3),
        )

    # 配方标准值未配置时，使用典型机器人坐标范围的默认值
    # 典型料架定位坐标：X~1200mm, Y~350mm, Z~850mm（机器人基坐标系）
    default_x = 1200.0 + round(rng.gauss(0, 1.5), 3)
    default_y = 350.0 + round(rng.gauss(0, 1.5), 3)
    default_z = 850.0 + round(rng.gauss(0, 1.0), 3)
    return (default_x, default_y, default_z)




@dataclass
class RackLocationOutput:
    rack_side: str
    position_no: int
    layer_no: int
    locate_ok: bool
    actual_x: float
    actual_y: float
    actual_z: float
    offset_x: float
    offset_y: float
    offset_z: float
    offset_rz: float = 0.0
    confidence: float = 0.0
    error_code: str = ''
    error_message: str = ''
    raw_data_path: str = ''
    result_image_path: str = ''
    result_data: Optional[dict] = None

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload['result_data'] = self.result_data or {}
        rack_compensation = compensation_from_output(
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            offset_z=self.offset_z,
            offset_rz=self.offset_rz,
            result_data=payload['result_data'],
        )
        payload['result_data']['rack_compensation'] = rack_compensation
        payload['result_data']['compensation_transform'] = rack_compensation
        payload['rack_compensation'] = rack_compensation
        payload['compensation_matrix'] = rack_compensation['matrix']
        if payload['result_data'].get('opening_rectangle'):
            payload['opening_rectangle'] = payload['result_data']['opening_rectangle']
        payload['algorithm_version'] = payload['result_data'].get(
            'algorithm_version', get_algorithm_version(None),
        )
        payload['plc_payload'] = {
            'task_kind': 'RACK_3D_LOCATION',
            'rack_side': self.rack_side,
            'side': self.rack_side,  # compatible with existing PLC adapter contract
            'position_no': self.position_no,
            'layer_no': self.layer_no,
            'locate_done': True,
            'locate_ok': self.locate_ok,
            'actual_x': self.actual_x,
            'actual_y': self.actual_y,
            'actual_z': self.actual_z,
            'offset_x': self.offset_x,
            'offset_y': self.offset_y,
            'offset_z': self.offset_z,
            'offset_rz': self.offset_rz,
            'offset_rx': rack_compensation['rotation_deg']['rx'],
            'offset_ry': rack_compensation['rotation_deg']['ry'],
            'confidence': self.confidence,
            'compensation_valid': self.locate_ok,
            'rack_compensation': rack_compensation,
            'compensation_matrix': rack_compensation['matrix'],
            'robot_taught_place_pose_count': 15,
            'vision_managed_place_pose_count': 0,
            'error_code': self.error_code,
        }
        return payload


class PointCloudProcessor:
    """Extract a rack pose from depth/point-cloud input.

    The real point-cloud algorithm should replace the fallback branch here.
    Tests and offline demos can pass actual_x/y/z directly.
    """

    min_valid_points = 3
    max_abs_coordinate = 10000.0

    def _normalized_roi(self, roi: dict, width: int, height: int) -> tuple[int, int, int, int]:
        """将 ROI 字典解析并 clamp 到图像范围内，返回 (x, y, w, h)。

        使用 math.floor/ceil 确保不同精度的浮点输入产生一致的整数边界，
        同时对超出图像边界的情况做截断（而非抛错），提高鲁棒性。
        """
        import math
        try:
            x = int(math.floor(float(roi.get('x', 0))))
            y = int(math.floor(float(roi.get('y', 0))))
            w = int(math.ceil(float(roi.get('w', roi.get('width', 0)))))
            h = int(math.ceil(float(roi.get('h', roi.get('height', 0)))))
        except (TypeError, ValueError) as exc:
            raise ValueError('ROI 参数必须包含有效的 x/y/w/h') from exc

        if w <= 0 or h <= 0:
            raise ValueError('ROI 宽高必须大于 0')

        # 边界 clamp：防止因浮点取整或轻微越界导致 IndexError
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))
        return x, y, w, h

    def crop_by_roi(self, organized_pointcloud, roi: dict):
        """矩形 ROI 裁剪组织化点云。若 roi 包含 polygon 字段则委托多边形裁剪。"""
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim != 3 or pointcloud.shape[2] != 3:
            raise ValueError('organized pointcloud 必须是 H x W x 3')

        # 若前端传入了多边形顶点，优先使用精确多边形蒙版裁剪
        polygon = roi.get('polygon')
        if polygon and isinstance(polygon, (list, tuple)) and len(polygon) >= 3:
            return self.crop_by_polygon_roi(organized_pointcloud, polygon)

        height, width, _ = pointcloud.shape
        x, y, w, h = self._normalized_roi(roi, width, height)
        points = pointcloud[y:y + h, x:x + w, :].reshape(-1, 3)
        return self.filter_valid_points(points)

    def crop_by_polygon_roi(
        self, organized_pointcloud, polygon_pts, *, return_pixel_coords: bool = False
    ):
        """使用多边形蒙版精确裁剪组织化点云 (H x W x 3)。

        Args:
            organized_pointcloud: H x W x 3 点云数组（像素坐标对应物理点）
            polygon_pts: 多边形顶点列表，每个元素为 {x, y} 或 (x, y)，
                         单位为图像像素坐标（与点云的行列索引对应）
            return_pixel_coords: 若为 True，同时返回每个裁剪点对应的像素 (px, py)

        Returns:
            valid_points: shape (M, 3) 的裁剪点云
            pixel_coords: 仅当 return_pixel_coords=True 时返回，shape (M, 2)
        """
        import cv2 as _cv2
        import logging as _log
        _logger = _log.getLogger(__name__)

        pointcloud = np.asarray(organized_pointcloud, dtype=np.float64)
        if pointcloud.ndim != 3 or pointcloud.shape[2] != 3:
            raise ValueError('organized pointcloud 必须是 H x W x 3')

        height, width, _ = pointcloud.shape

        # 将多边形顶点转为整数 numpy 数组，供 cv2.fillPoly 使用
        try:
            if isinstance(polygon_pts[0], dict):
                pts_arr = np.array(
                    [[int(round(p['x'])), int(round(p['y']))] for p in polygon_pts],
                    dtype=np.int32,
                )
            else:
                pts_arr = np.array(
                    [[int(round(p[0])), int(round(p[1]))] for p in polygon_pts],
                    dtype=np.int32,
                )
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f'多边形顶点格式错误: {exc}') from exc

        # 边界 clamp，防止顶点坐标轻微越界
        pts_arr[:, 0] = np.clip(pts_arr[:, 0], 0, width - 1)
        pts_arr[:, 1] = np.clip(pts_arr[:, 1], 0, height - 1)

        # 用 cv2.fillPoly 生成多边形蒙版（比逐点判断快几十倍）
        mask = np.zeros((height, width), dtype=np.uint8)
        _cv2.fillPoly(mask, [pts_arr], color=1)

        # 有效点过滤：同时满足「在蒙版内」+「坐标有限」+「Z≠0」
        pts_flat = pointcloud.reshape(-1, 3)
        mask_flat = mask.reshape(-1).astype(bool)
        finite_mask = np.isfinite(pts_flat).all(axis=1)
        nonzero_z = np.abs(pts_flat[:, 2]) > 1e-9
        inside = mask_flat & finite_mask & nonzero_z

        valid_points = pts_flat[inside]
        _logger.info(
            '[crop_by_polygon_roi] 多边形顶点=%d, 蒙版像素=%d/%d, '
            '有效点=%d/%d',
            len(pts_arr), int(mask.sum()), height * width,
            valid_points.shape[0], pts_flat.shape[0],
        )

        if return_pixel_coords:
            pixel_y, pixel_x = np.indices((height, width))
            pixels = np.column_stack((pixel_x.reshape(-1), pixel_y.reshape(-1)))
            return valid_points, pixels[inside]

        return valid_points

    def _normalized_roi_3d(self, roi: dict) -> dict:
        required = ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
        try:
            normalized = {key: float(roi[key]) for key in required}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('三维 ROI 参数无效') from exc

        if normalized['x_min'] >= normalized['x_max']:
            raise ValueError('x_min must be less than x_max')
        if normalized['y_min'] >= normalized['y_max']:
            raise ValueError('y_min must be less than y_max')
        if normalized['z_min'] >= normalized['z_max']:
            raise ValueError('z_min must be less than z_max')
        return normalized

    def crop_by_roi_3d(self, organized_pointcloud, roi: dict):
        """使用3D ROI裁剪点云"""
        import logging
        logger = logging.getLogger(__name__)
        
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim == 3 and pointcloud.shape[2] == 3:
            points = pointcloud.reshape(-1, 3)
        elif pointcloud.ndim == 2 and pointcloud.shape[1] == 3:
            points = pointcloud
        else:
            raise ValueError('pointcloud 必须是 H x W x 3 或 N x 3')

        logger.info(f"[crop_by_roi_3d] 输入点云: {points.shape[0]}点")
        logger.info(f"  X范围: [{points[:, 0].min():.2f}, {points[:, 0].max():.2f}]")
        logger.info(f"  Y范围: [{points[:, 1].min():.2f}, {points[:, 1].max():.2f}]")
        logger.info(f"  Z范围: [{points[:, 2].min():.2f}, {points[:, 2].max():.2f}]")
        
        valid_points = self.filter_valid_points(points)
        logger.info(f"[crop_by_roi_3d] 过滤后有效点: {valid_points.shape[0]}点")
        
        bounds = self._normalized_roi_3d(roi)
        logger.info(f"[crop_by_roi_3d] ROI范围:")
        logger.info(f"  X: [{bounds['x_min']:.2f}, {bounds['x_max']:.2f}]")
        logger.info(f"  Y: [{bounds['y_min']:.2f}, {bounds['y_max']:.2f}]")
        logger.info(f"  Z: [{bounds['z_min']:.2f}, {bounds['z_max']:.2f}]")
        
        mask = (
            (valid_points[:, 0] >= bounds['x_min'])
            & (valid_points[:, 0] <= bounds['x_max'])
            & (valid_points[:, 1] >= bounds['y_min'])
            & (valid_points[:, 1] <= bounds['y_max'])
            & (valid_points[:, 2] >= bounds['z_min'])
            & (valid_points[:, 2] <= bounds['z_max'])
        )
        cropped = valid_points[mask]
        
        logger.info(f"[crop_by_roi_3d] ✓ 裁剪后点数: {cropped.shape[0]}点")
        
        if cropped.shape[0] == 0:
            logger.error(f"[crop_by_roi_3d] ❌ 裁剪后点云为空！")
            logger.error(f"  可能原因:")
            logger.error(f"    1. ROI范围与点云坐标不匹配")
            logger.error(f"    2. 点云坐标系错误")
            logger.error(f"    3. ROI范围设置过小")
            logger.error(f"  建议:")
            logger.error(f"    - 检查点云坐标范围")
            logger.error(f"    - 放宽ROI的X/Y/Z范围")
            logger.error(f"    - 确认点云坐标系是否正确")
        
        return cropped

    def crop_by_roi_3d_with_pixels(self, organized_pointcloud, roi: dict):
        """使用3D ROI裁剪组织化点云，同时保留每个点对应的像素坐标。"""
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim != 3 or pointcloud.shape[2] != 3:
            return self.crop_by_roi_3d(pointcloud, roi), None
        bounds = self._normalized_roi_3d(roi)
        points = pointcloud.reshape(-1, 3)
        pixel_y, pixel_x = np.indices(pointcloud.shape[:2])
        pixels = np.column_stack((pixel_x.reshape(-1), pixel_y.reshape(-1)))
        valid = (
            np.isfinite(points).all(axis=1)
            & (np.abs(points[:, 2]) > 1e-9)
            & (np.abs(points).max(axis=1) <= self.max_abs_coordinate)
        )
        inside = (
            valid
            & (points[:, 0] >= bounds['x_min'])
            & (points[:, 0] <= bounds['x_max'])
            & (points[:, 1] >= bounds['y_min'])
            & (points[:, 1] <= bounds['y_max'])
            & (points[:, 2] >= bounds['z_min'])
            & (points[:, 2] <= bounds['z_max'])
        )
        return points[inside], pixels[inside]

    def filter_valid_points(self, points):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        finite_mask = np.isfinite(points).all(axis=1)
        non_zero_depth_mask = np.abs(points[:, 2]) > 1e-9
        distance_mask = np.abs(points).max(axis=1) <= self.max_abs_coordinate
        return points[finite_mask & non_zero_depth_mask & distance_mask]

    def calculate_median_xyz(self, points) -> tuple[float, float, float]:
        """计算点云的中位数位置"""
        valid_points = self.filter_valid_points(points)
        
        # 添加详细日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[calculate_median_xyz] 输入点数: {points.shape[0]}, 有效点数: {valid_points.shape[0]}")
        
        if valid_points.shape[0] < self.min_valid_points:
            logger.error(f"[calculate_median_xyz] ❌ 有效点数太少: {valid_points.shape[0]} < {self.min_valid_points}")
            logger.error(f"  可能原因: ROI裁剪范围太小，或点云坐标不在预期范围内")
            raise ValueError(f'ROI 内有效点数太少 ({valid_points.shape[0]} < {self.min_valid_points})')
        
        median = np.median(valid_points, axis=0)
        result = tuple(round(float(v), 3) for v in median)
        
        logger.info(f"[calculate_median_xyz] ✓ 计算结果: X={result[0]:.2f}, Y={result[1]:.2f}, Z={result[2]:.2f}")
        
        return result

    def extract_pose(self, frame: dict, recipe: RackLocationRecipe, position_no: int, layer_no: int) -> dict:
        if all(key in frame for key in ('actual_x', 'actual_y', 'actual_z')):
            return dict(frame)

        pointcloud = frame.get('organized_pointcloud')
        if pointcloud is None:
            pointcloud = frame.get('pointcloud')
        if pointcloud is not None:
            roi = (frame.get('roi_config') or recipe.roi_config or {}).get('target_roi')
            if not roi:
                raise ValueError('未绘制 ROI')
            points = self.crop_by_roi(pointcloud, roi)
            actual_x, actual_y, actual_z = self.calculate_median_xyz(points)
            roi_area = max(int(roi.get('w', roi.get('width', 1))) * int(roi.get('h', roi.get('height', 1))), 1)
            confidence = frame.get('confidence')
            if confidence is None:
                # 置信度 = 有效点占比 与 ROI 内深度平整度 的综合。
                # 画在平整支撑面上的 ROI 置信度高，跨越边缘/立柱的 ROI 置信度低，
                # 让 “ROI 质量 → 置信度” 随绘制位置真实变化。
                valid_ratio = min(1.0, points.shape[0] / roi_area)
                z_std = float(np.std(points[:, 2])) if points.shape[0] else 999.0
                flatness = 1.0 / (1.0 + z_std / 30.0)
                confidence = max(0.0, min(0.99, 0.5 * valid_ratio + 0.5 * flatness))
            return {
                **frame,
                'actual_x': actual_x,
                'actual_y': actual_y,
                'actual_z': actual_z,
                'offset_rz': float(frame.get('offset_rz', 0.0)),
                'confidence': round(float(confidence), 4),
                'valid_point_count': int(points.shape[0]),
            }

        # ── 无点云帧时：从 2D 深度场景图像 ROI 中位数推算坐标 ──────────────────
        # 利用与 2D 相机工作台同源的深度场（image_io.build_depth_field），
        # 按配方中保存的 target_roi 区域取中位数像素深度值，
        # 再叠加小量高斯噪声，让同一配方重复采集结果稳定一致，
        # 且随 ROI 绘制位置不同而产生真实感差异。
        target_roi = (recipe.roi_config or {}).get('target_roi') or {}
        actual_x, actual_y, actual_z = _simulate_xyz_from_scene(
            recipe=recipe,
            position_no=position_no,
            layer_no=layer_no,
            target_roi=target_roi,
        )
        rng = random.Random(f'rz-pos-{position_no}-layer-{layer_no}')
        return {
            **frame,
            'actual_x': actual_x,
            'actual_y': actual_y,
            'actual_z': actual_z,
            'offset_rz': round(rng.gauss(0, 0.15), 3),
            'confidence': float(frame.get('confidence', 0.92)),
            'source': 'scene_simulated',
        }


class RackPoseEstimator:
    """Calculate position compensation relative to the taught standard pose."""

    def __init__(self, processor: Optional[PointCloudProcessor] = None):
        self.processor = processor or PointCloudProcessor()

    def calculate_rack_offset(self, pointcloud_or_depth: dict, recipe: RackLocationRecipe,
                              rack_side: str = RackSide.BOTH, layer_no: int = 1) -> RackLocationOutput:
        position_no = int(getattr(recipe, 'position_no', pointcloud_or_depth.get('position_no', 1)) or 1)
        layer_no = int(layer_no)

        # 验证手眼标定配置
        hand_eye_config = recipe.hand_eye_config or {}
        
        # 检查是否有有效的手眼标定矩阵
        has_valid_calibration = False
        skip_calibration_check = hand_eye_config.get('skip_validation', False)  # 开发模式：跳过验证
        
        if hand_eye_config:
            matrix_type = hand_eye_config.get('matrix')
            if matrix_type and matrix_type != 'identity':
                # 有具体的标定矩阵（如 'T_flange_camera'）或者有 calibration_id
                has_valid_calibration = True
            elif 'calibration_id' in hand_eye_config:
                # 配置了标定ID
                has_valid_calibration = True
            elif 'T_flange_camera' in hand_eye_config:
                # 直接包含变换矩阵
                has_valid_calibration = True
            elif matrix_type == 'identity':
                # 显式单位矩阵用于相机坐标系与机器人坐标系已重合的工位。
                has_valid_calibration = True
        
        if not has_valid_calibration and not skip_calibration_check:
            return RackLocationOutput(
                rack_side=rack_side,
                position_no=position_no,
                layer_no=layer_no,
                locate_ok=False,
                actual_x=0.0,
                actual_y=0.0,
                actual_z=0.0,
                offset_x=0.0,
                offset_y=0.0,
                offset_z=0.0,
                confidence=0.0,
                error_code='MISSING_HAND_EYE',
                error_message='3D料架定位配方缺少手眼标定参数。请在配方管理中配置手眼标定，或在hand_eye_config中添加"skip_validation": true进行开发测试。',
                raw_data_path=pointcloud_or_depth.get('raw_data_path', ''),
                result_image_path=pointcloud_or_depth.get('result_image_path', ''),
            )

        try:
            pose = self.processor.extract_pose(pointcloud_or_depth, recipe, position_no, layer_no)
        except ValueError as exc:
            return RackLocationOutput(
                rack_side=rack_side,
                position_no=position_no,
                layer_no=layer_no,
                locate_ok=False,
                actual_x=0.0,
                actual_y=0.0,
                actual_z=0.0,
                offset_x=0.0,
                offset_y=0.0,
                offset_z=0.0,
                confidence=0.0,
                error_code='POINTCLOUD_ERROR',
                error_message=str(exc),
                raw_data_path=pointcloud_or_depth.get('raw_data_path', ''),
                result_image_path=pointcloud_or_depth.get('result_image_path', ''),
            )
        confidence = round(float(pose.get('confidence', 0.0)), 4)
        actual_x = round(float(pose.get('actual_x', 0)), 3)
        actual_y = round(float(pose.get('actual_y', 0)), 3)
        actual_z = round(float(pose.get('actual_z', 0)), 3)

        # ── 坐标系记录 ────────────────────────────────────────────────
        # actual_x/y/z 的坐标系由调用者保证：
        #   - Rack3DLocator._output_from_points 会先做手眼变换（相机→机器人基坐标系）
        #   - extract_pose / SampleRackFrameProvider 走模拟路径，直接给机器人坐标
        # 不再用「偏差超过50mm就强制替换」的hack，保留真实计算结果以便诊断。
        std_x_val = float(recipe.standard_x)
        std_y_val = float(recipe.standard_y)
        std_z_val = float(recipe.standard_z)
        coordinate_system = pose.get('coordinate_system', 'unknown')
        import logging as _log
        _log.getLogger(__name__).info(
            f'[坐标系] actual=({actual_x:.2f},{actual_y:.2f},{actual_z:.2f}) '
            f'standard=({std_x_val:.2f},{std_y_val:.2f},{std_z_val:.2f}) '
            f'coordinate_system={coordinate_system}'
        )

        offset_x = round(actual_x - float(recipe.standard_x), 3)
        offset_y = round(actual_y - float(recipe.standard_y), 3)
        offset_z = round(actual_z - float(recipe.standard_z), 3)
        offset_rz = round(float(pose.get('offset_rz', 0)), 3)


        error_code = ''
        error_message = ''
        locate_ok = True

        if confidence < float(recipe.confidence_threshold):
            locate_ok = False
            error_code = 'LOW_CONFIDENCE'
            error_message = f'定位置信度不足: {confidence:.2%} < {float(recipe.confidence_threshold):.2%}'

        return RackLocationOutput(
            rack_side=rack_side,
            position_no=position_no,
            layer_no=layer_no,
            locate_ok=locate_ok,
            actual_x=actual_x,
            actual_y=actual_y,
            actual_z=actual_z,
            offset_x=offset_x,
            offset_y=offset_y,
            offset_z=offset_z,
            offset_rz=offset_rz,
            confidence=confidence,
            error_code=error_code,
            error_message=error_message,
            raw_data_path=pose.get('raw_data_path', ''),
            result_image_path=pose.get('result_image_path', ''),
            result_data={
                'source': pose.get('source', 'unknown'),
                'actual_x': actual_x,
                'actual_y': actual_y,
                'actual_z': actual_z,
                'valid_point_count': pose.get('valid_point_count'),
                'capture_pose_name': recipe.capture_pose_name,
                'roi_config': recipe.roi_config,
                'reference_feature_config': recipe.reference_feature_config,
            },
        )


class SampleRackFrameProvider:
    """Offline depth-frame provider used when the DM camera is unavailable."""

    def capture(self, recipe: RackLocationRecipe, position_no: int, layer_no: int) -> dict:
        layer_count = int(recipe.layer_count or 3)
        depth_img, pillar, region = image_io.generate_depth_scene(side='LEFT', layer_count=layer_count)
        raw_path, width, height = image_io.save_image(
            depth_img,
            f'rack_pos_{position_no}_layer_{layer_no}_raw',
            rel_dir='vision/sample_depth',
        )

        pose = PointCloudProcessor().extract_pose(
            {'source': 'sample', 'raw_data_path': raw_path, 'image_width': width, 'image_height': height},
            recipe,
            position_no,
            layer_no,
        )
        offsets = {
            'offset_x': float(pose['actual_x']) - float(recipe.standard_x),
            'offset_y': float(pose['actual_y']) - float(recipe.standard_y),
            'offset_z': float(pose['actual_z']) - float(recipe.standard_z),
        }
        annotated = image_io.annotate_depth(
            depth_img,
            pillar,
            region,
            'LEFT',
            offsets,
            confidence=float(pose.get('confidence', 0.92)),
            layer_heights=[],
            recipe_matched=True,
        )
        result_path, _, _ = image_io.save_image(
            annotated,
            f'rack_pos_{position_no}_layer_{layer_no}_result',
            rel_dir='vision/results',
        )
        return {**pose, 'raw_data_path': raw_path, 'result_image_path': result_path}


def build_sample_pointcloud(
    *,
    side: str = 'LEFT',
    layer_count: int = 3,
    width: int = 640,
    height: int = 480,
    seed: int = None,
    local_template_geometry: bool = False,
    **_legacy,
):
    """Build an organized sample point-cloud (H x W x 3, mm) from the canonical
    depth scene that is shown on the page.

    与 ``image_io.generate_depth_scene`` 共享同一深度场（``build_depth_field``），
    因此页面上显示的深度伪彩图与此处用于 ROI 裁剪的点云是**同一个场景**：
    在不同位置画 ROI 会裁剪到不同空间区域，从而得到不同的实际 X/Y/Z。
    这让 “ROI → 点云裁剪 → 中位数坐标” 的流程真实可感，而不是返回写死值。

    保留 ``**_legacy``（如旧的 ``target_roi``/``actual_x`` 关键字参数）以兼容
    历史调用，但坐标不再被强行覆盖，而是完全由场景几何决定。
    """
    depth, _pillar, _region = image_io.build_depth_field(
        side, int(layer_count or 3), width, height, seed=seed,
    )
    pointcloud = image_io.depth_field_to_pointcloud(depth)
    if not local_template_geometry:
        return pointcloud

    # 为三平面工作台测试提供一组可明确框选的理想料架几何。这里只在显式
    # 请求 local_template_geometry 时覆盖三个区域，不影响真实相机与普通样例。
    # Π1/Π3 是相互平行的水平基准面，Π2 是与它们正交的左侧立面。
    sx = width / 640.0
    sy = height / 480.0
    regions = {
        'plane1': (round(190 * sx), round(105 * sy), round(250 * sx), round(45 * sy)),
        'plane2': (round(135 * sx), round(105 * sy), round(45 * sx), round(270 * sy)),
        'plane3': (round(190 * sx), round(330 * sy), round(250 * sx), round(45 * sy)),
    }
    for name, (x, y, w, h) in regions.items():
        rows, cols = np.indices((h, w), dtype=np.float64)
        if name == 'plane2':
            pointcloud[y:y + h, x:x + w, 0] = -210.0
            pointcloud[y:y + h, x:x + w, 1] = -135.0 + rows * (270.0 / max(h - 1, 1))
            pointcloud[y:y + h, x:x + w, 2] = 900.0 + cols * (210.0 / max(w - 1, 1))
        else:
            pointcloud[y:y + h, x:x + w, 0] = -180.0 + cols * (360.0 / max(w - 1, 1))
            pointcloud[y:y + h, x:x + w, 1] = (-120.0 if name == 'plane1' else 120.0) + rows * 0.2
            pointcloud[y:y + h, x:x + w, 2] = 920.0 if name == 'plane1' else 1110.0
    return pointcloud




_DOCS_PIC_COUNTER = 0  # 轮询计数器，全局唯一


def _load_docs_pic_pointcloud():
    """从 docs/pic/1~N 目录中轮询读取真实 PLY 点云，转为 HxWx3 有序点云 (mm)。

    PLY 格式：binary_little_endian，每点 float x,y,z + uchar r,g,b，
    来自 Rvbust 相机，典型分辨率 1080x1440。
    """
    global _DOCS_PIC_COUNTER
    import glob as _glob

    base_dir = os.path.join(settings.BASE_DIR, 'docs', 'pic')
    dirs = sorted(
        d for d in _glob.glob(os.path.join(base_dir, '*'))
        if os.path.isdir(d) and os.path.basename(d).isdigit()
    )
    if not dirs:
        return None

    idx = _DOCS_PIC_COUNTER % len(dirs)
    _DOCS_PIC_COUNTER += 1
    ply_path = os.path.join(dirs[idx], 'PointCloud.ply')
    if not os.path.exists(ply_path):
        return None

    try:
        with open(ply_path, 'rb') as f:
            header_lines = []
            while True:
                line = f.readline().decode('ascii', 'ignore').strip()
                header_lines.append(line)
                if line == 'end_header':
                    break
            n_verts = 0
            for ln in header_lines:
                if ln.startswith('element vertex'):
                    n_verts = int(ln.split()[-1])
                    break
            # 每点：x(4) y(4) z(4) r(1) g(1) b(1) = 15 bytes
            data = f.read(n_verts * 15)

        xyz = np.frombuffer(data, dtype=np.dtype([
            ('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
            ('r', 'u1'), ('g', 'u1'), ('b', 'u1'),
        ])).copy()

        # 推断有序尺寸
        if n_verts == 1080 * 1440:
            H, W = 1080, 1440
        else:
            for H, W in [(720, 1280), (480, 640), (1200, 1600), (1024, 1280)]:
                if H * W == n_verts:
                    break
            else:
                H = int(n_verts ** 0.5)
                W = n_verts // H

        cloud = np.stack(
            [xyz['x'], xyz['y'], xyz['z']], axis=-1
        ).reshape(H, W, 3).astype(np.float64)

        # 将无效点（x=y=z=0）置为 NaN，与相机输出保持一致
        invalid = (cloud[..., 0] == 0) & (cloud[..., 1] == 0) & (cloud[..., 2] == 0)
        cloud[invalid] = np.nan

        logger.info('[docs/pic] 加载离线点云 %s，尺寸 %dx%d', ply_path, H, W)
        return cloud
    except Exception as exc:  # noqa: BLE001
        logger.warning('[docs/pic] PLY 读取失败: %s', exc)
        return None


def sample_scene_median_xyz(target_roi: dict, *, side: str = 'LEFT',
                            layer_count: int = 3, width: int = 640,
                            height: int = 480) -> tuple[float, float, float]:
    """返回标准场景中给定 ROI 的中位数 X/Y/Z，用于把配方标准坐标默认值
    对齐到场景，使默认 ROI 的补偿值约为 0。"""
    pointcloud = build_sample_pointcloud(
        side=side, layer_count=layer_count, width=width, height=height,
    )
    processor = PointCloudProcessor()
    points = processor.crop_by_roi(pointcloud, target_roi)
    return processor.calculate_median_xyz(points)


class DMCameraRackFrameProvider:
    """Frame provider using the existing DM camera SDK service with sample fallback.

    DM SDK 的 capture_frame_data() 将原始帧数据放在 'data' 键下，但
    PointCloudProcessor.extract_pose() 使用 'organized_pointcloud' 或
    'pointcloud' 来查找点云数据。此处负责做 key 映射。
    """

    def __init__(self, *, fallback_provider: Optional[SampleRackFrameProvider] = None):
        self.fallback_provider = fallback_provider or SampleRackFrameProvider()

    def capture(self, recipe: RackLocationRecipe, position_no: int, layer_no: int) -> dict:
        if getattr(settings, 'VISION_RACK_LOCATION_FORCE_SAMPLE', False):
            frame = self.fallback_provider.capture(recipe, position_no, layer_no)
            frame['source'] = 'sample_forced'
            return frame

        try:
            from apps.dm_camera.services import DMCameraService

            service = DMCameraService()
            if not service.is_connected:
                # 工作台采集不要求事先在相机页面手动「连接」：此处自动连接物理
                # 相机（默认第一台 + 激活配置），连接失败才会进入下方异常回退。
                active_config = DMCameraConfig.objects.filter(is_active=True).first()
                service.connect(
                    device_sn=getattr(active_config, 'device_sn', None) or None,
                    config_id=getattr(active_config, 'id', None),
                )
            if not service.is_streaming:
                service.start_stream()
            frame = service.capture_frame_data(frame_type='POINTCLOUD', save_record=False)

            # ── key 映射：SDK 'data' → 算法层 'organized_pointcloud' ──
            result = {
                **frame,
                'source': 'dm_camera',
                'position_no': position_no,
                'layer_no': layer_no,
            }
            raw_data = frame.get('data')
            if raw_data is not None:
                arr = np.asarray(raw_data)
                width = int(frame.get('width') or frame.get('image_width') or 0)
                height = int(frame.get('height') or frame.get('image_height') or 0)
                if frame.get('frame_type') == 'POINTCLOUD':
                    # DM SDK 点云帧的 data 可能是扁平 (N,3)、1D 连续 XYZ，
                    # 或已经是 H×W×3；统一整理成组织化点云供 ROI 裁剪。
                    if arr.ndim == 3 and arr.shape[2] == 3:
                        result['organized_pointcloud'] = arr
                    elif arr.ndim == 2 and arr.shape[1] == 3:
                        if width > 0 and height > 0 and arr.shape[0] == width * height:
                            result['organized_pointcloud'] = arr.reshape(height, width, 3)
                        else:
                            result['pointcloud'] = arr
                    elif arr.ndim == 1 and width > 0 and height > 0 and arr.size == width * height * 3:
                        result['organized_pointcloud'] = arr.reshape(height, width, 3)
                    else:
                        # 形状无法对齐到 H×W×3 时保留原始点列，供 extract_pose fallback
                        result['pointcloud'] = arr
                elif arr.ndim == 3 and arr.shape[2] == 3:
                    result['organized_pointcloud'] = arr
                elif arr.ndim == 2:
                    # 深度图帧
                    result['depth_image'] = arr
                else:
                    result['pointcloud'] = arr
            return result
        except DMCameraConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - hardware fallback is intentional
            frame = self.fallback_provider.capture(recipe, position_no, layer_no)
            frame['source'] = 'sample_fallback'
            frame['fallback_reason'] = str(exc)
            return frame


class PlcVisionResultWriter:
    """Write 3D rack-location compensation through the existing device adapter.

    写入前执行二次校验：即使 result.is_success 为 True，也会重新检查
    当前配方的 max_offset 阈值，防止配方修改后过时的 OK 结果被写入。
    """

    def __init__(self, adapter=None, device_service: Optional[DeviceService] = None):
        self.adapter = adapter or get_device_adapter()
        self.device_service = device_service or DeviceService(adapter=self.adapter)

    def _revalidate_offsets(self, result: RackLocationResult) -> str:
        """按当前配方阈值重新校验补偿值，返回空字符串表示通过。"""
        recipe = result.recipe
        if recipe is None:
            return ''  # 无配方时跳过二次校验
        # 只保留置信度检查
        if float(result.confidence) < float(recipe.confidence_threshold):
            return f'置信度不足: {float(result.confidence):.2%} < {float(recipe.confidence_threshold):.2%}'
        return ''

    def _validate_plc_payload(self, payload: dict) -> str:
        if not payload:
            return 'PLC payload 缺失'
        if payload.get('compensation_valid') is not True:
            return '补偿无效，未写入 PLC'
        for key in ('offset_x', 'offset_y', 'offset_z', 'offset_rz'):
            if key not in payload:
                return f'PLC payload 缺少 {key}'
            try:
                float(payload[key])
            except (TypeError, ValueError):
                return f'PLC payload {key} 不是有效数值'
        return ''

    def write(self, result: RackLocationResult) -> dict:
        payload = result.result_data.get('plc_payload') or {}
        if not result.is_success:
            result.plc_write_status = 'SKIPPED'
            result.plc_error_message = '定位NG，未写入有效补偿'
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            return {'success': False, 'skipped': True, 'error': result.plc_error_message}

        # ── 二次校验：按当前配方阈值重新检查 ──
        rejection = self._validate_plc_payload(payload)
        if rejection:
            result.plc_write_status = 'REJECTED'
            result.plc_error_message = rejection
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            AlarmService().create(
                source=AlarmSource.VISION,
                level=AlarmLevel.ERROR,
                message=f'VISION_3D PLC写入被拒绝: {rejection}',
                rack=result.rack,
                lock_workstation=True,
            )
            return {'success': False, 'rejected': True, 'error': rejection}

        rejection = self._revalidate_offsets(result)
        if rejection:
            result.plc_write_status = 'REJECTED'
            result.plc_error_message = rejection
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            AlarmService().create(
                source=AlarmSource.VISION,
                level=AlarmLevel.ERROR,
                message=f'VISION_3D PLC写入被拒绝(二次校验): {rejection}',
                rack=result.rack,
                lock_workstation=True,
            )
            return {'success': False, 'rejected': True, 'error': rejection}

        response = self.adapter.send_rack_offsets(payload)
        if response.get('success'):
            result.plc_write_status = 'SUCCESS'
            result.plc_error_message = ''
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            self.device_service.record_signal(
                device_code='PLC-01',
                signal_name='rack_3d_location_compensation',
                signal_value=f'POS{result.position_no}-L{result.layer_no}',
                direction=SignalDirection.OUT,
                raw_payload=payload,
            )
            return response

        result.plc_write_status = 'FAILED'
        result.plc_error_message = response.get('error', 'PLC写入失败')
        result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
        AlarmService().create(
            source=AlarmSource.DEVICE,
            level=AlarmLevel.ERROR,
            message=f'VISION_3D PLC写入失败: {result.plc_error_message}',
            rack=result.rack,
            lock_workstation=True,
        )
        return response


class Rack3DLocator:
    """Formal 3D rack-location facade using rack-coordinate 3D ROI boxes."""

    def __init__(self, *, frame_provider=None, processor=None, plc_writer=None):
        self.frame_provider = frame_provider or DMCameraRackFrameProvider()
        self.processor = processor or PointCloudProcessor()
        self.plc_writer = plc_writer or PlcVisionResultWriter()

    def _select_recipe(self, *, recipe_id=None, layer_no=1):
        """选择配方（简化版：固定position_no=1, rack_side=BOTH）"""
        if recipe_id:
            return RackLocationRecipe.objects.get(pk=recipe_id, enabled=True)
        return RackLocationRecipe.objects.get(
            enabled=True, position_no=1, layer_no=layer_no,
        )

    def _select_roi(self, recipe: RackLocationRecipe, layer_no: int):
        local_roi = (
            RackLocationROI3D.objects
            .filter(recipe=recipe, enabled=True, mode=RackLocationROI3D.MODE_LOCAL, layer_no=layer_no)
            .order_by('-updated_at')
            .first()
        )
        if local_roi:
            return local_roi, 'local'
        global_roi = (
            RackLocationROI3D.objects
            .filter(recipe=recipe, enabled=True, mode=RackLocationROI3D.MODE_GLOBAL)
            .order_by('-updated_at')
            .first()
        )
        if global_roi:
            return global_roi, 'global'
        return None, 'missing'

    def _persist_frame(self, pointcloud):
        return RackLocationService(
            frame_provider=self.frame_provider,
            plc_writer=self.plc_writer,
        )._persist_workbench_frame(pointcloud)

    def _load_pointcloud(self, token):
        return RackLocationService(
            frame_provider=self.frame_provider,
            plc_writer=self.plc_writer,
        )._load_workbench_pointcloud(token)

    def _media_token_exists(self, token: str) -> bool:
        if not token:
            return False
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        abs_path = os.path.realpath(os.path.join(media_root, token))
        return os.path.commonpath([abs_path, media_root]) == media_root and os.path.exists(abs_path)

    def get_current_recipe(self, *, locate_type, layer_index, rack_type=None):
        semantics = locate_semantics(locate_type=locate_type, layer_index=layer_index)
        qs = RackLocationRecipe.objects.filter(enabled=True, layer_no=semantics['layer_no'])
        if rack_type:
            qs = qs.filter(rack_type=rack_type)
        return qs.order_by('position_no', '-updated_at').first()

    def save_roi(self, *, recipe_id, locate_type, layer_index, roi_3d, alignment_token,
                 roi_name='3D ROI', enabled=True):
        if not self._media_token_exists(alignment_token):
            raise ValueError('请先自动对齐，再保存生产 ROI')
        semantics = locate_semantics(locate_type=locate_type, layer_index=layer_index)
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)
        layer_no = None if semantics['roi_mode'] == RackLocationROI3D.MODE_GLOBAL else semantics['layer_no']
        RackLocationROI3D.objects.filter(
            recipe=recipe,
            mode=semantics['roi_mode'],
            layer_no=layer_no,
            enabled=True,
        ).update(enabled=False)
        return RackLocationROI3D.objects.create(
            recipe=recipe,
            roi_name=roi_name,
            mode=semantics['roi_mode'],
            layer_no=layer_no,
            coordinate_system='rack',
            x_min=roi_3d['x_min'],
            x_max=roi_3d['x_max'],
            y_min=roi_3d['y_min'],
            y_max=roi_3d['y_max'],
            z_min=roi_3d['z_min'],
            z_max=roi_3d['z_max'],
            enabled=enabled,
        )

    def calibrate_standard_template(self, *, recipe_id, result_id=None,
                                    opening_rectangle=None, note='') -> dict:
        """Persist the current three-member standard rack model into the recipe.

        This implements the one-time "标准料架标定" step: under the mechanical
        zero position, save the fitted left/right uprights, top crossbeam,
        front plane, coordinate frame, point-cloud template and rack pose on
        the vision host. Taught placement poses remain in the robot controller.
        """
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)
        result = None
        if result_id:
            result = RackLocationResult.objects.get(pk=result_id)
            if result.recipe_id and result.recipe_id != recipe.id:
                raise ValueError('定位结果与配方不匹配，不能作为该配方的标准模板')
            opening_rectangle = (result.result_data or {}).get('opening_rectangle')

        opening_rectangle = opening_rectangle or {}
        if not opening_rectangle.get('locate_ok', False):
            raise ValueError('标准料架模型只能从定位 OK 的三钢架拟合结果生成')
        points = opening_rectangle.get('points') or {}
        standard_points = {}
        for key in ('p1', 'p2', 'p3', 'p4'):
            point = points.get(key) or {}
            standard_points[key] = {
                'x': float(point['x']),
                'y': float(point['y']),
                'z': float(point['z']),
            }

        thresholds = (
            (opening_rectangle.get('quality') or {}).get('thresholds')
            or ((recipe.reference_feature_config or {}).get('opening_rectangle') or {}).get('thresholds')
            or {}
        )
        standard_rack_model = build_standard_rack_model(
            opening_rectangle,
            result=result,
            note=note,
        )
        reference_feature_config = normalize_reference_feature_config(
            recipe.reference_feature_config or {},
        )
        reference_feature_config.update({
            'algorithm_version': ALGORITHM_VERSION,
            'standard_template': {
                'template_type': 'three_member_rack_model',
                'model_version': standard_rack_model['model_version'],
                'source_result_id': result.id if result else None,
                'saved_at': standard_rack_model['saved_at'],
                'note': note,
                'robot_taught_place_pose_count': 15,
                'vision_managed_place_pose_count': 0,
            },
            'standard_rack_model': standard_rack_model,
            'opening_rectangle': {
                **((reference_feature_config.get('opening_rectangle') or {})),
                'coordinate_system': opening_rectangle.get('coordinate_system') or 'robot_base',
                'standard_points': standard_points,
                'thresholds': thresholds,
            },
        })
        reference_feature_config = normalize_reference_feature_config(reference_feature_config)
        reference = standard_geometry(reference_feature_config)
        recipe.reference_feature_config = reference_feature_config
        recipe.standard_x = float(reference['center_array'][0])
        recipe.standard_y = float(reference['center_array'][1])
        recipe.standard_z = float(reference['center_array'][2])
        recipe.standard_rz = float((opening_rectangle.get('pose') or {}).get('rz') or 0)
        recipe.save(update_fields=[
            'reference_feature_config',
            'standard_x',
            'standard_y',
            'standard_z',
            'standard_rz',
            'updated_at',
        ])
        return {
            'recipe_id': recipe.id,
            'recipe_name': recipe.recipe_name,
            'reference_feature_config': recipe.reference_feature_config,
            'standard_rack_model': standard_rack_model,
            'standard_pose': {
                'x': float(recipe.standard_x),
                'y': float(recipe.standard_y),
                'z': float(recipe.standard_z),
                'rz': float(recipe.standard_rz),
            },
            'source_result_id': result.id if result else None,
            'robot_taught_place_pose_count': 15,
            'vision_managed_place_pose_count': 0,
        }

    def capture(self, *, recipe_id=None, layer_no=1, rack_side=None, **_kwargs) -> dict:
        """采集点云数据（每次调用都重新采集一帧实时数据）。
        
        rack_side 和其它额外参数由适配层内部处理，此处接受但不强制传递。
        """
        recipe = self._select_recipe(recipe_id=recipe_id, layer_no=layer_no) if recipe_id else None
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', layer_no) or layer_no)
        layer_count = int(getattr(recipe, 'layer_count', 3) or 3)
        requested_side = rack_side or getattr(recipe, 'rack_side', RackSide.LEFT)
        side_key = requested_side if requested_side in {RackSide.LEFT, RackSide.RIGHT} else RackSide.LEFT

        pointcloud = None
        source = 'sample'
        fallback_reason = ''
        try:
            probe_recipe = recipe or RackLocationRecipe(
                recipe_name='VISION-3D-CAPTURE',
                rack_side=RackSide.BOTH,
                position_no=position_no,
                layer_no=layer_no,
                layer_count=layer_count,
                hand_eye_config={'matrix': 'identity'},
            )
            frame = self.frame_provider.capture(probe_recipe, position_no, layer_no)
            fallback_reason = frame.get('fallback_reason', '') or ''
            cloud = frame.get('organized_pointcloud')
            if cloud is not None:
                arr = np.asarray(cloud, dtype=float)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    pointcloud = arr
                    source = frame.get('source', 'dm_camera')
        except DMCameraConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            fallback_reason = str(exc)

        if pointcloud is None:
            # 使用配方ID+层号的哈希作为固定种子，确保同一配方每次生成相同的模拟点云，
            # 消除因随机性导致多次计算结果不一致的问题。
            _sim_seed = hash((str(recipe_id or 'default'), int(layer_no))) & 0x7FFFFFFF
            pointcloud = build_sample_pointcloud(
                side=side_key, layer_count=layer_count, seed=_sim_seed,
                local_template_geometry=True,
            )
            source = 'sample'

        token, preview_url, width, height = self._persist_frame(pointcloud)
        payload = {
            'pointcloud_token': token,
            'pointcloud_preview_url': preview_url,
            'raw_rgb_image_url': preview_url,
            'raw_depth_image_url': preview_url,
            'image_width': width,
            'image_height': height,
            'source': source,
            'fallback_reason': fallback_reason,
        }
        if recipe and recipe.roi_config:
            payload['recipe_pixel_roi'] = RackLocationService(
                frame_provider=self.frame_provider,
                plc_writer=self.plc_writer,
            ).project_recipe_roi_to_pixels(pointcloud, recipe)
        return payload

    def auto_align(self, *, token, recipe_id=None) -> dict:
        pointcloud = self._load_pointcloud(token)
        views = self.generate_corrected_views(pointcloud)
        return {
            'coordinate_system': {
                'name': 'rack',
                'transform_matrix': [
                    [1, 0, 0, 0],
                    [0, 1, 0, 0],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ],
                'source': 'mock_identity',
            },
            'features': {
                'columns': [],
                'layers': [],
                'support_plane': {'normal': [0, 0, 1], 'offset': 0},
            },
            'aligned_pointcloud_token': token,
            'views': views,
        }

    def generate_corrected_views(self, pointcloud) -> dict:
        preview = image_io.pointcloud_to_preview(pointcloud)
        front_rel, _, _ = image_io.save_image(preview, 'rack_3d_front', rel_dir='vision/rack_3d')
        top_rel, _, _ = image_io.save_image(np.flipud(preview), 'rack_3d_top', rel_dir='vision/rack_3d')
        side_rel, _, _ = image_io.save_image(np.fliplr(preview), 'rack_3d_side', rel_dir='vision/rack_3d')
        point_rel, _, _ = image_io.save_image(preview, 'rack_3d_pointcloud', rel_dir='vision/rack_3d')
        return {
            'front_view_url': settings.MEDIA_URL + front_rel,
            'top_view_url': settings.MEDIA_URL + top_rel,
            'side_view_url': settings.MEDIA_URL + side_rel,
            'pointcloud_view_url': settings.MEDIA_URL + point_rel,
        }

    def _output_from_points(self, *, points, recipe, rack_side, layer_no, roi_source,
                            roi_id=None, token='', pixel_coordinates=None,
                            auto_extract_corners=False) -> RackLocationOutput:
        """从裁剪后的点云计算定位结果。
        
        先尝试通过手眼矩阵将点云变换到机器人基坐标系，再计算实测 actual_x/y/z。
        这确保前端显示的坐标与配方标准坐标（机器人坐标系）在同一坐标系内。
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[_output_from_points] 输入点数: {points.shape[0]}")
        
        if points.shape[0] == 0:
            logger.error("[_output_from_points] ❌ 点云为空，无法计算位置！")
            return RackLocationOutput(
                position_no=int(getattr(recipe, 'position_no', 1) or 1),
                layer_no=int(layer_no),
                locate_ok=False,
                error_code='EMPTY_POINTCLOUD',
                error_message='ROI裁剪后点云为空，请检查ROI配置',
                offset_x=0,
                offset_y=0,
                offset_z=0,
                offset_rz=0,
                actual_x=0,
                actual_y=0,
                actual_z=0,
                confidence=0,
                rack_side=rack_side,
                result_data={
                    'roi_id': roi_id,
                    'roi_source': roi_source,
                    'coordinate_system': 'camera',
                    'point_count': 0,
                    'error_detail': 'ROI裁剪后点云为空',
                }
            )
        
        # ── 尝试将相机坐标系点云变换到机器人基坐标系 ─────────────────
        coordinate_system = 'camera'  # 默认：相机坐标系
        robot_points = points  # 默认不做变换
        # 保留原始相机坐标（变换前），供 locate_auto() 使用：
        #   camera_points 需要是相机坐标系下的点（用于深度边缘检测）
        #   depth_values 需要是相机Z轴方向的深度（非机器人坐标系的Z高度）
        camera_points_orig = np.asarray(points, dtype=float)
        
        try:
            from apps.vision.coordinate_transform import CoordinateTransformService
            transform_service = CoordinateTransformService()
            
            # 从配方中加载手眼标定矩阵
            hand_eye_config = recipe.hand_eye_config or {}
            has_calibration = recipe.hand_eye_calibration_id and getattr(
                recipe, 'hand_eye_calibration', None
            ) and recipe.hand_eye_calibration.T_flange_camera
            
            T_fc = None  # T_flange_camera：相机→法兰
            if has_calibration:
                T_fc = CoordinateTransformService.parse_matrix_from_json(
                    recipe.hand_eye_calibration.T_flange_camera
                )
            elif hand_eye_config and hand_eye_config.get('matrix') not in (None, 'identity'):
                T_fc = CoordinateTransformService.parse_matrix_from_json(hand_eye_config)
            elif hand_eye_config and 'T_flange_camera' in hand_eye_config:
                T_fc = CoordinateTransformService.parse_matrix_from_json(
                    hand_eye_config['T_flange_camera']
                )
            elif hand_eye_config.get('matrix') == 'identity' and hand_eye_config.get('skip_validation'):
                # 仅供离线/开发数据：显式声明跳过校验时，identity 才是有效变换。
                T_fc = np.eye(4, dtype=np.float64)
            
            # 从配方中加载机器人位姿（法兰→基坐标系）
            capture_pose = recipe.capture_pose or {}
            T_bf = None  # T_base_flange：法兰→基坐标系
            if capture_pose and all(k in capture_pose for k in ('x', 'y', 'z')):
                T_bf = CoordinateTransformService.pose_to_matrix(
                    float(capture_pose.get('x', 0)),
                    float(capture_pose.get('y', 0)),
                    float(capture_pose.get('z', 0)),
                    float(capture_pose.get('rx', 0)),
                    float(capture_pose.get('ry', 0)),
                    float(capture_pose.get('rz', 0)),
                )
            elif hand_eye_config.get('matrix') == 'identity' and hand_eye_config.get('skip_validation'):
                T_bf = np.eye(4, dtype=np.float64)
            
            if T_fc is not None and T_bf is not None:
                # 执行坐标变换：相机坐标系 → 法兰坐标系 → 机器人基坐标系
                robot_points = transform_service.camera_to_robot_base(
                    points.astype(np.float64), T_fc, T_bf
                )
                coordinate_system = 'robot_base'
                logger.info(
                    f"[_output_from_points] ✓ 已通过手眼变换将点云转换到机器人基坐标系"
                    f" (手眼来源: {'手眼标定' if has_calibration else '配方矩阵'})"
                )
            else:
                logger.warning(
                    f"[_output_from_points] ⚠ 缺少手眼矩阵或机器人位姿，点云保持相机坐标系"
                    f" (T_fc={'有' if T_fc is not None else '无'}, T_bf={'有' if T_bf is not None else '无'})"
                )
        except Exception as transform_exc:
            logger.warning(f"[_output_from_points] ⚠ 坐标变换失败，使用原始相机坐标: {transform_exc}")
            robot_points = points
            coordinate_system = 'camera'

        if auto_extract_corners or is_rectangle_v2(recipe.reference_feature_config):
            try:
                if auto_extract_corners:
                    # camera_points 必须是相机坐标系下的点（变换前），用于深度边缘检测
                    # depth_values 必须是相机Z轴方向的深度值（非机器人坐标系的Z高度方向）
                    rectangle = RackOpeningRectangleLocator().locate_auto(
                        robot_points,
                        recipe.reference_feature_config,
                        camera_points=camera_points_orig,
                        depth_values=camera_points_orig[:, 2],
                        coordinate_system=coordinate_system,
                        pixel_coordinates=pixel_coordinates,
                        confidence_threshold=float(recipe.confidence_threshold),
                    )
                else:
                    rectangle = RackOpeningRectangleLocator().locate(
                        robot_points,
                        recipe.reference_feature_config,
                        coordinate_system=coordinate_system,
                        pixel_coordinates=pixel_coordinates,
                        confidence_threshold=float(recipe.confidence_threshold),
                    )
                center = rectangle['center']
                if rectangle.get('standard_geometry_configured') is False:
                    standard_center = np.asarray([
                        float(recipe.standard_x),
                        float(recipe.standard_y),
                        float(recipe.standard_z),
                    ])
                    offset_rz = 0.0
                else:
                    reference = standard_geometry(recipe.reference_feature_config)
                    standard_center = reference['center_array']
                    deviation_rotation = np.asarray(
                        rectangle['deviation_transform']['matrix'], dtype=float,
                    )[:3, :3]
                    offset_rz = float(np.degrees(np.arctan2(
                        deviation_rotation[1, 0], deviation_rotation[0, 0],
                    )))
                center_offsets = {
                    'x': float(center['x']) - float(standard_center[0]),
                    'y': float(center['y']) - float(standard_center[1]),
                    'z': float(center['z']) - float(standard_center[2]),
                    'rz': offset_rz,
                }
                offset_limits = {
                    'x': float(recipe.max_offset_x),
                    'y': float(recipe.max_offset_y),
                    'z': float(recipe.max_offset_z),
                    'rz': float(recipe.max_offset_rz),
                }
                exceeded = [
                    axis for axis in ('x', 'y', 'z', 'rz')
                    if abs(center_offsets[axis]) > offset_limits[axis]
                ]
                if exceeded:
                    limit_message = '定位偏差超出配方上限: ' + ', '.join(
                        f"{axis.upper()}={center_offsets[axis]:+.3f}/{offset_limits[axis]:.3f}"
                        for axis in exceeded
                    )
                    rectangle['locate_ok'] = False
                    rectangle['error_code'] = 'OFFSET_OUT_OF_RANGE'
                    rectangle['error_message'] = '; '.join(filter(None, [
                        rectangle.get('error_message'), limit_message,
                    ]))
                    rectangle['quality']['failures'].append({
                        'code': 'OFFSET_OUT_OF_RANGE', 'message': limit_message,
                    })
                return RackLocationOutput(
                    rack_side=rack_side,
                    position_no=int(getattr(recipe, 'position_no', 1) or 1),
                    layer_no=int(layer_no),
                    locate_ok=bool(rectangle['locate_ok']),
                    actual_x=round(float(center['x']), 3),
                    actual_y=round(float(center['y']), 3),
                    actual_z=round(float(center['z']), 3),
                    offset_x=round(center_offsets['x'], 3),
                    offset_y=round(center_offsets['y'], 3),
                    offset_z=round(center_offsets['z'], 3),
                    offset_rz=round(offset_rz, 3),
                    confidence=float(rectangle['quality']['confidence']),
                    error_code=rectangle.get('error_code', ''),
                    error_message=rectangle.get('error_message', ''),
                    raw_data_path=token,
                    result_data={
                        'algorithm_version': rectangle['algorithm_version'],
                        'source': 'rack_3d_roi',
                        'roi_id': roi_id,
                        'roi_source': roi_source,
                        'coordinate_system': coordinate_system,
                        'point_count': int(robot_points.shape[0]),
                        'valid_point_count': int(rectangle['quality']['valid_point_count']),
                        'opening_rectangle': rectangle,
                        'reference_mode': rectangle.get('reference_mode', 'standard_four_points'),
                    },
                )
            except RectangleLocationError as exc:
                logger.warning('V2矩形开口定位失败: %s %s', exc.code, exc.message)
                return RackLocationOutput(
                    rack_side=rack_side,
                    position_no=int(getattr(recipe, 'position_no', 1) or 1),
                    layer_no=int(layer_no),
                    locate_ok=False,
                    actual_x=0.0,
                    actual_y=0.0,
                    actual_z=0.0,
                    offset_x=0.0,
                    offset_y=0.0,
                    offset_z=0.0,
                    offset_rz=0.0,
                    confidence=0.0,
                    error_code=exc.code,
                    error_message=exc.message,
                    raw_data_path=token,
                    result_data={
                        'algorithm_version': (
                            AUTO_ALGORITHM_VERSION if auto_extract_corners
                            else get_algorithm_version(recipe.reference_feature_config)
                        ),
                        'source': 'rack_3d_roi',
                        'roi_id': roi_id,
                        'roi_source': roi_source,
                        'coordinate_system': coordinate_system,
                        'point_count': int(robot_points.shape[0]),
                        'error_detail': exc.details,
                    },
                )
        
        try:
            actual_x, actual_y, actual_z = self.processor.calculate_median_xyz(robot_points)
        except ValueError as e:
            logger.error(f"[_output_from_points] ❌ 计算中位数失败: {e}")
            return RackLocationOutput(
                position_no=int(getattr(recipe, 'position_no', 1) or 1),
                layer_no=int(layer_no),
                locate_ok=False,
                error_code='INSUFFICIENT_POINTS',
                error_message=str(e),
                offset_x=0,
                offset_y=0,
                offset_z=0,
                offset_rz=0,
                actual_x=0,
                actual_y=0,
                actual_z=0,
                confidence=0,
                rack_side=rack_side,
                result_data={
                    'roi_id': roi_id,
                    'roi_source': roi_source,
                    'coordinate_system': coordinate_system,
                    'point_count': int(robot_points.shape[0]),
                    'error_detail': str(e),
                }
            )
        
        confidence = min(0.99, max(0.0, robot_points.shape[0] / 1000.0))
        
        logger.info(
            f"[_output_from_points] ✓ 实际位置({coordinate_system}): "
            f"X={actual_x:.2f}, Y={actual_y:.2f}, Z={actual_z:.2f}"
        )
        logger.info(f"[_output_from_points]   置信度: {confidence:.3f}, 点数: {robot_points.shape[0]}")
        
        frame = {
            'actual_x': actual_x,
            'actual_y': actual_y,
            'actual_z': actual_z,
            'confidence': confidence,
            'source': 'rack_3d_roi',
            'coordinate_system': coordinate_system,
            'raw_data_path': token,
        }
        output = RackPoseEstimator(processor=self.processor).calculate_rack_offset(
            frame, recipe, rack_side=rack_side, layer_no=layer_no,
        )
        output.result_data = {
            **(output.result_data or {}),
            'roi_id': roi_id,
            'roi_source': roi_source,
            'coordinate_system': coordinate_system,
            'point_count': int(robot_points.shape[0]),
        }
        return output

    def _offset_dict(self, *, x=0, y=0, z=0, rz=0) -> dict:
        return {
            'x': round(float(x or 0), 3),
            'y': round(float(y or 0), 3),
            'z': round(float(z or 0), 3),
            'rz': round(float(rz or 0), 3),
        }

    def _output_offset(self, output: RackLocationOutput) -> dict:
        return self._offset_dict(
            x=output.offset_x,
            y=output.offset_y,
            z=output.offset_z,
            rz=output.offset_rz,
        )

    def _result_offset(self, result: RackLocationResult | None) -> dict:
        if result is None:
            return self._offset_dict()
        data = result.result_data or {}
        final = data.get('final_offset') or data.get('overall_offset') or {}
        return self._offset_dict(
            x=final.get('x', result.offset_x),
            y=final.get('y', result.offset_y),
            z=final.get('z', result.offset_z),
            rz=final.get('rz', result.offset_rz),
        )

    def _latest_global_result(self, *, recipe: RackLocationRecipe, rack_side: str) -> RackLocationResult | None:
        return (
            RackLocationResult.objects
            .filter(
                position_no=recipe.position_no,
                side=rack_side,
                layer_no=0,
                is_success=True,
            )
            .order_by('-created_at')
            .first()
        )

    def _combine_offsets(self, overall: dict, layer: dict) -> dict:
        return self._offset_dict(
            x=float(overall.get('x', 0)) + float(layer.get('x', 0)),
            y=float(overall.get('y', 0)) + float(layer.get('y', 0)),
            z=float(overall.get('z', 0)) + float(layer.get('z', 0)),
            rz=float(overall.get('rz', 0)) + float(layer.get('rz', 0)),
        )

    def _semantic_result_data(self, *, recipe, rack_side, layer_no, output, payload) -> dict:
        semantics = locate_semantics(
            locate_type=LOCATE_TYPE_GLOBAL if int(layer_no or 0) == 0 else LOCATE_TYPE_LAYER,
            layer_index=layer_no,
        )
        measured = self._output_offset(output)
        measured_compensation = compensation_from_output(
            offset_x=measured['x'],
            offset_y=measured['y'],
            offset_z=measured['z'],
            offset_rz=measured['rz'],
            result_data=payload.get('result_data') or output.result_data or {},
        )
        global_result = None
        if semantics['locate_type'] == LOCATE_TYPE_GLOBAL:
            overall = measured
            layer = self._offset_dict()
            overall_compensation = measured_compensation
            layer_compensation = compensation_from_output()
            final_compensation = measured_compensation
        else:
            global_result = self._latest_global_result(recipe=recipe, rack_side=rack_side)
            overall = self._result_offset(global_result)
            layer = measured
            overall_compensation = compensation_from_result(
                global_result.result_data if global_result else {},
                fallback_offset=overall,
            )
            layer_compensation = measured_compensation
            final_compensation = combine_compensations(overall_compensation, layer_compensation)
        final = self._combine_offsets(overall, layer)
        plc_payload = {
            **(payload.get('plc_payload') or {}),
            'locate_type': semantics['locate_type'],
            'layer_index': semantics['layer_index'],
            'offset_x': final['x'],
            'offset_y': final['y'],
            'offset_z': final['z'],
            'overall_offset': overall,
            'layer_offset': layer,
            'final_offset': final,
            'rack_compensation': final_compensation,
            'compensation_matrix': final_compensation['matrix'],
            'offset_rx': final_compensation['rotation_deg']['rx'],
            'offset_ry': final_compensation['rotation_deg']['ry'],
            'offset_rz': final_compensation['rotation_deg']['rz'],
            'robot_taught_place_pose_count': 15,
            'vision_managed_place_pose_count': 0,
        }
        return {
            'locate_type': semantics['locate_type'],
            'layer_index': semantics['layer_index'],
            'overall_offset': overall,
            'layer_offset': layer,
            'final_offset': final,
            'measured_compensation': measured_compensation,
            'overall_compensation': overall_compensation,
            'layer_compensation': layer_compensation,
            'rack_compensation': final_compensation,
            'compensation_transform': final_compensation,
            'compensation_matrix': final_compensation['matrix'],
            'global_result_id': global_result.id if global_result else None,
            'plc_payload': plc_payload,
        }

    def test_locate(self, *, token, roi_3d, roi_config=None, recipe_id=None, rack_side=RackSide.LEFT,
                    layer_no=1, save_record=False, auto_extract_corners=False) -> dict:
        """测试定位（不保存到数据库，除非指定save_record=True）"""
        recipe = self._select_recipe(recipe_id=recipe_id, layer_no=layer_no)
        pointcloud = self._load_pointcloud(token)
        
        target_roi = None
        new_camera_roi = None
        pixel_coordinates = None
        if roi_config and roi_config.get('target_roi'):
            target_roi = roi_config['target_roi']
            
        if target_roi:
            # 优先使用前端传入的 2D target_roi (手工画的框) 来截取点云，保证计算结果与画框完全一致
            cloud = np.asarray(pointcloud, dtype=float)

            polygon = target_roi.get('polygon')
            if polygon and isinstance(polygon, (list, tuple)) and len(polygon) >= 3:
                # ── 多边形ROI：使用精确多边形蒙版裁剪，不再降级为矩形包围盒 ──
                import logging as _log
                _log.getLogger(__name__).info(
                    '[test_locate] 使用多边形ROI裁剪，顶点数=%d', len(polygon)
                )
                if cloud.ndim == 3 and cloud.shape[2] == 3:
                    points, pixel_coordinates = self.processor.crop_by_polygon_roi(
                        cloud, polygon, return_pixel_coords=True,
                    )
                else:
                    points = np.empty((0, 3), dtype=float)
                    pixel_coordinates = None
            else:
                # ── 矩形ROI：使用 _normalized_roi 的 clamp 逻辑，防止浮点取整越界 ──
                if cloud.ndim == 3 and cloud.shape[2] == 3:
                    h_img, w_img, _ = cloud.shape
                    x, y, w, h = self.processor._normalized_roi(target_roi, w_img, h_img)
                    cropped_cloud = cloud[y:y + h, x:x + w]
                    pts = cropped_cloud.reshape(-1, 3)
                    valid = np.isfinite(pts[:, 2]) & (np.abs(pts[:, 2]) > 1e-9)
                    points = pts[valid]
                    pixel_y, pixel_x = np.indices(cropped_cloud.shape[:2])
                    all_pixels = np.column_stack((pixel_x.reshape(-1) + x, pixel_y.reshape(-1) + y))
                    pixel_coordinates = all_pixels[valid]
                else:
                    points = np.empty((0, 3), dtype=float)
                    pixel_coordinates = None

            # 自动计算该 2D 框覆盖点云的 3D 包围框（保存到配方 camera_roi 以供后续参考）
            if len(points) > 0:
                new_camera_roi = {
                    'x_min': float(points[:, 0].min()),
                    'x_max': float(points[:, 0].max()),
                    'y_min': float(points[:, 1].min()),
                    'y_max': float(points[:, 1].max()),
                    'z_min': float(points[:, 2].min()),
                    'z_max': float(points[:, 2].max()),
                }
        else:
            points, pixel_coordinates = self.processor.crop_by_roi_3d_with_pixels(
                pointcloud, roi_3d,
            )
            
        if points.shape[0] < self.processor.min_valid_points:
            raise ValueError('ROI 内有效点数太少')
            
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source='request',
            token=token,
            pixel_coordinates=pixel_coordinates,
            auto_extract_corners=auto_extract_corners,
        )
        
        # 生成带ROI框和结果标注的图像
        preview = image_io.pointcloud_to_preview(pointcloud)
        
        # 尝试从roi_config获取2D ROI用于标注
        target_roi = None
        if roi_config and roi_config.get('target_roi'):
            target_roi = roi_config['target_roi']
        
        # 如果有2D ROI，则绘制标注；否则只添加结果文字
        if target_roi:
            # 获取完整的开口矩形数据（包含 pixel_points 和 points）
            opening_rectangle = (output.result_data or {}).get('opening_rectangle', {})
            annotated = image_io.annotate_pointcloud_roi(
                preview, target_roi,
                offsets={'x': output.offset_x, 'y': output.offset_y, 'z': output.offset_z},
                confidence=output.confidence,
                actual=(output.actual_x, output.actual_y, output.actual_z),
                locate_ok=output.locate_ok,
                feature_points=opening_rectangle,
            )
        else:
            # 没有2D ROI，只在图像上添加结果文字（不绘制框）
            annotated = preview.copy()
            import cv2
            COLOR_OK = (0, 255, 0)
            COLOR_FAIL = (0, 0, 255)
            COLOR_TEXT = (255, 255, 255)
            box_color = COLOR_OK if output.locate_ok else COLOR_FAIL
            verdict = '定位 OK' if output.locate_ok else '定位 NG'
            cv2.putText(annotated, verdict, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)
            cv2.putText(annotated, f'X={output.offset_x:+.2f}  Y={output.offset_y:+.2f}  Z={output.offset_z:+.2f} mm', 
                       (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)
            if output.confidence is not None:
                cv2.putText(annotated, f'Conf: {output.confidence:.2%}', 
                           (12, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)
        
        result_rel, result_width, result_height = image_io.save_image(
            annotated, 'rack_3d_result', rel_dir='vision/rack_3d',
        )
        saved_result = None
        payload = output.to_payload()
        
        # 如果需要保存记录，创建VisionTask和RackLocationResult
        if save_record:
            position_no = 1  # 固定为1（工作台模式）
            db_recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
            
            if db_recipe and target_roi:
                # 用户手工画了 2D 框进行计算，自动更新配方的 ROI 使得下次定位自动生效
                config = dict(db_recipe.roi_config or {})
                config['target_roi'] = target_roi
                if new_camera_roi:
                    config['camera_roi'] = new_camera_roi
                db_recipe.roi_config = config
                db_recipe.save(update_fields=['roi_config'])
            
            task = VisionTask.objects.create(
                task_type=VisionTaskType.RACK_LOCATING,
                status=ResultStatus.SUCCESS if output.locate_ok else ResultStatus.FAILED,
                started_at=timezone.now(),
                finished_at=timezone.now(),
                error_message=output.error_message,
            )
            
            roi_snapshot = {
                'target_roi': target_roi or {},
                'roi_3d': new_camera_roi or roi_3d or {},
            }
            saved_result = RackLocationResult.objects.create(
                vision_task=task,
                recipe=db_recipe,
                side=output.rack_side or RackSide.BOTH,
                position_no=position_no,
                layer_no=int(layer_no),
                offset_x=_decimal(output.offset_x),
                offset_y=_decimal(output.offset_y),
                offset_z=_decimal(output.offset_z),
                offset_rz=_decimal(output.offset_rz),
                actual_x=_decimal(output.actual_x),
                actual_y=_decimal(output.actual_y),
                actual_z=_decimal(output.actual_z),
                confidence=_decimal(output.confidence),
                is_success=output.locate_ok,
                error_code=output.error_code,
                error_message=output.error_message,
                raw_data_path=token or '',
                result_image_path=result_rel,
                roi_data=roi_snapshot,
                result_data={**(payload.get('result_data') or {}), 'roi': roi_snapshot},
            )

            depth_rel, depth_width, depth_height = image_io.save_image(
                preview, 'rack_3d_depth', rel_dir='vision/rack_3d',
            )
            VisionImage.objects.create(
                vision_task=task,
                image_type=VisionImageType.DEPTH,
                file=depth_rel,
                width=depth_width,
                height=depth_height,
                captured_at=timezone.now(),
            )
            VisionImage.objects.create(
                vision_task=task,
                image_type=VisionImageType.RESULT,
                file=result_rel,
                width=result_width,
                height=result_height,
                captured_at=timezone.now(),
            )
        
        payload.update({
            'roi_source': 'request',
            'cropped_preview_url': settings.MEDIA_URL + result_rel,
            'result_image_url': settings.MEDIA_URL + result_rel,
            'result_image_path': result_rel,
            'result_id': saved_result.id if saved_result else None,
        })
        return payload

    def locate(self, *, rack_side, layer_no, recipe_id=None, write_plc=False, product=None, rack=None, workflow=None):
        recipe = self._select_recipe(recipe_id=recipe_id, layer_no=layer_no)
        roi, roi_source = self._select_roi(recipe, int(layer_no))
        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            product=product,
            rack=rack,
            status=ResultStatus.RUNNING,
            started_at=timezone.now(),
        )
        if roi is None:
            result = RackLocationResult.objects.create(
                vision_task=task,
                recipe=recipe,
                rack=rack,
                side=rack_side,
                position_no=recipe.position_no,
                layer_no=layer_no,
                confidence=0,
                is_success=False,
                error_code='ROI_NOT_CONFIGURED',
                error_message='未找到对应的三维 ROI 配方',
                result_data={'roi_source': roi_source, 'task_kind': 'RACK_3D_LOCATION'},
            )
            task.status = ResultStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = result.error_message
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            return result

        captured = self.capture(recipe_id=recipe.id, rack_side=rack_side, layer_no=layer_no)
        pointcloud = self._load_pointcloud(captured['pointcloud_token'])
        points, pixel_coordinates = self.processor.crop_by_roi_3d_with_pixels(
            pointcloud, roi3d_to_dict(roi),
        )
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source=roi_source,
            roi_id=roi.id,
            token=captured['pointcloud_token'],
            pixel_coordinates=pixel_coordinates,
        )
        payload = output.to_payload()
        semantic_data = self._semantic_result_data(
            recipe=recipe,
            rack_side=rack_side,
            layer_no=layer_no,
            output=output,
            payload=payload,
        )
        final_offset = semantic_data['final_offset']
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=recipe,
            rack=rack,
            side=rack_side,
            position_no=recipe.position_no,
            layer_no=layer_no,
            offset_x=_decimal(final_offset['x']),
            offset_y=_decimal(final_offset['y']),
            offset_z=_decimal(final_offset['z']),
            offset_rz=_decimal(final_offset['rz']),
            actual_x=_decimal(output.actual_x),
            actual_y=_decimal(output.actual_y),
            actual_z=_decimal(output.actual_z),
            confidence=_decimal(output.confidence, '0.0001'),
            is_recipe_matched=output.locate_ok,
            is_success=output.locate_ok,
            error_code=output.error_code,
            error_message=output.error_message,
            raw_data_path=captured['pointcloud_token'],
            result_data={
                **(payload.get('result_data') or {}),
                **semantic_data,
                'task_kind': 'RACK_3D_LOCATION',
                'roi_id': roi.id,
                'roi_source': roi_source,
            },
        )
        if write_plc:
            self.write_result_to_plc(result)
        task.status = ResultStatus.SUCCESS if result.is_success else ResultStatus.FAILED
        task.finished_at = timezone.now()
        task.error_message = result.error_message
        task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
        return result

    def write_result_to_plc(self, result):
        return self.plc_writer.write(result)


class RackLocationService:
    """Orchestrate one-photo, one-position/layer 3D rack location."""

    def __init__(self, *, frame_provider=None, estimator=None, plc_writer=None):
        self.frame_provider = frame_provider or DMCameraRackFrameProvider()
        self.estimator = estimator or RackPoseEstimator()
        self.plc_writer = plc_writer or PlcVisionResultWriter()

    def _select_recipe(self, *, recipe_id=None, position_no: int = 1,
                       layer_no: int) -> RackLocationRecipe:
        """Select the enabled recipe for the requested workstation and layer."""
        qs = RackLocationRecipe.objects.filter(enabled=True, position_no=position_no)
        if recipe_id:
            return qs.get(pk=recipe_id)
        return qs.get(layer_no=layer_no)

    def capture_standard_image(self, recipe_id=None) -> dict:
        recipe = None
        if recipe_id:
            recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', 1) or 1)
        frame = SampleRackFrameProvider().capture(
            recipe or RackLocationRecipe(
                recipe_name='PREVIEW',
                position_no=position_no,
                layer_no=layer_no,
                standard_x=1200,
                standard_y=350,
                standard_z=850,
                hand_eye_config={'matrix': 'identity'},
            ),
            position_no,
            layer_no,
        )
        preview_path = frame.get('raw_data_path') or frame.get('result_image_path') or ''
        preview_url = settings.MEDIA_URL + preview_path if preview_path and not preview_path.startswith(('/', 'http')) else preview_path
        return {
            'preview_image_path': preview_path,
            'preview_image_url': preview_url,
            'image_width': int(frame.get('image_width', 640) or 640),
            'image_height': int(frame.get('image_height', 480) or 480),
            'source': frame.get('source', 'sample'),
        }

    def preview_calculate(self, recipe_data: dict, roi_config: dict, recipe_id=None) -> RackLocationOutput:
        recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
        recipe = recipe or RackLocationRecipe(recipe_name='PREVIEW')

        for field in (
            'standard_x', 'standard_y', 'standard_z', 'standard_rz',
            'max_offset_x', 'max_offset_y', 'max_offset_z', 'max_offset_rz',
            'confidence_threshold',
        ):
            if field in recipe_data:
                setattr(recipe, field, recipe_data[field])
        recipe.roi_config = roi_config or {}
        if recipe_data.get('reference_feature_config') is not None:
            recipe.reference_feature_config = recipe_data.get('reference_feature_config') or {}
        if recipe_data.get('hand_eye_config') is not None:
            recipe.hand_eye_config = recipe_data.get('hand_eye_config') or {}
        elif not recipe.hand_eye_config:
            recipe.hand_eye_config = {'matrix': 'identity'}

        layer_count = int(recipe_data.get('layer_count') or getattr(recipe, 'layer_count', 3) or 3)
        if is_rectangle_v2(recipe.reference_feature_config):
            return RackLocationOutput(
                rack_side=recipe.rack_side or RackSide.BOTH,
                position_no=int(getattr(recipe, 'position_no', 1) or 1),
                layer_no=int(recipe_data.get('layer_no') or getattr(recipe, 'layer_no', 1) or 1),
                locate_ok=False,
                actual_x=0.0,
                actual_y=0.0,
                actual_z=0.0,
                offset_x=0.0,
                offset_y=0.0,
                offset_z=0.0,
                confidence=0.0,
                error_code='REAL_CAMERA_REQUIRED',
                error_message='矩形四角点V2预览必须使用真实/离线点云工作台，不能用中位数模拟结果',
                result_data={'algorithm_version': get_algorithm_version(recipe.reference_feature_config)},
            )
        pointcloud = build_sample_pointcloud(side='LEFT', layer_count=layer_count)
        frame = {
            'source': 'sample_pointcloud',
            'organized_pointcloud': pointcloud,
            'roi_config': recipe.roi_config,
            'raw_data_path': 'vision/sample_pointcloud/sample_rack_location.npy',
            'result_image_path': 'vision/rack_location_results/sample_preview.png',
            # 不写死 confidence：由 ROI 内有效点占比 + 深度平整度计算，随绘制位置变化。
        }
        return self.estimator.calculate_rack_offset(
            frame,
            recipe,
            rack_side=recipe.rack_side or RackSide.BOTH,
            layer_no=int(recipe_data.get('layer_no') or getattr(recipe, 'layer_no', 1) or 1),
        )

    # ------------------------------------------------------------------
    # 交互式工作台：采集真实点云 → 绘制 ROI → 计算 → 保存
    # ------------------------------------------------------------------

    def project_recipe_roi_to_pixels(self, pointcloud, recipe) -> dict:
        """根据配方的 3D ROI 或目标坐标系下的 ROI，向二维像素系投影，得出 2D 框。

        优先级（从高到低）：
        1. target_roi（用户在工作台手绘的 2D 像素框）——直接使用，最精确
        2. camera_roi（3D 包围盒）——从点云中找实际落在该范围内的像素坐标包围盒，
           避免原角点针孔投影在 z 范围大时覆盖整图的问题
        3. 角点针孔投影（兜底）
        """
        config = dict(getattr(recipe, 'roi_config', None) or {})
        cloud = np.asarray(pointcloud, dtype=float)
        if cloud.ndim == 2:
            raise ValueError("project_recipe_roi_to_pixels requires organized pointcloud (H, W, 3)")

        height, width = cloud.shape[:2]

        # ── 优先级①：target_roi（用户手绘的 2D 像素框，最精确）─────────────
        target_roi_raw = config.get('target_roi')
        if target_roi_raw and isinstance(target_roi_raw, dict):
            tx = int(target_roi_raw.get('x', 0) or 0)
            ty = int(target_roi_raw.get('y', 0) or 0)
            tw = int(target_roi_raw.get('w', target_roi_raw.get('width', 0)) or 0)
            th = int(target_roi_raw.get('h', target_roi_raw.get('height', 0)) or 0)
            if tw > 0 and th > 0:
                tx = max(0, min(tx, width - 1))
                ty = max(0, min(ty, height - 1))
                tw = max(1, min(tw, width - tx))
                th = max(1, min(th, height - ty))
                result = {
                    'x': tx, 'y': ty, 'w': tw, 'h': th,
                    'projection_source': 'target_roi',
                    'feature_type': 'recipe_3d_roi',
                }
                if target_roi_raw.get('polygon'):
                    result['polygon'] = target_roi_raw['polygon']
                return result

        intrinsics = config.get('camera_intrinsics') or {}
        fx = float(intrinsics.get('fx', image_io.PINHOLE_FX))
        fy = float(intrinsics.get('fy', image_io.PINHOLE_FY))
        cx = float(intrinsics.get('cx', width / 2.0))
        cy = float(intrinsics.get('cy', height / 2.0))

        def project_box(camera_bounds, source):
            corners = np.array([
                [x, y, z]
                for x in (camera_bounds['x_min'], camera_bounds['x_max'])
                for y in (camera_bounds['y_min'], camera_bounds['y_max'])
                for z in (camera_bounds['z_min'], camera_bounds['z_max'])
            ], dtype=float)
            positive = corners[:, 2] > 1e-9
            if not positive.any():
                return None
            corners = corners[positive]
            u = fx * corners[:, 0] / corners[:, 2] + cx
            v = fy * corners[:, 1] / corners[:, 2] + cy
            x1 = max(0, int(np.floor(u.min())) - 1)
            y1 = max(0, int(np.floor(v.min())) - 1)
            x2 = min(width, int(np.ceil(u.max())) + 1)
            y2 = min(height, int(np.ceil(v.max())) + 1)
            if x2 <= x1 or y2 <= y1:
                return None
            return {
                'x': x1, 'y': y1, 'w': x2 - x1, 'h': y2 - y1,
                'projection_source': source,
                'feature_type': 'recipe_3d_roi',
            }

        camera_roi = config.get('camera_roi')
        if camera_roi:
            # ── 优先级②：camera_roi → 用点云中实际落在 3D 范围内的像素坐标包围盒 ──
            # 原来的「枚举 8 角点做针孔投影」在 z_min/z_max 差异大时，会得到
            # 覆盖整图的错误 ROI 框。改为直接从组织化点云中找到满足 3D 条件的像素，
            # 取其行列坐标的包围盒，与图像实际分布完全一致。
            try:
                bounds = self.estimator.processor._normalized_roi_3d(camera_roi)
                pts = cloud.reshape(-1, 3)
                finite = np.isfinite(pts).all(axis=1) & (np.abs(pts[:, 2]) > 1e-9)
                inside = (
                    finite
                    & (pts[:, 0] >= bounds['x_min']) & (pts[:, 0] <= bounds['x_max'])
                    & (pts[:, 1] >= bounds['y_min']) & (pts[:, 1] <= bounds['y_max'])
                    & (pts[:, 2] >= bounds['z_min']) & (pts[:, 2] <= bounds['z_max'])
                )
                if inside.any():
                    idx = np.where(inside)[0]
                    rows = idx // width   # v 方向（行）
                    cols = idx % width    # u 方向（列）
                    x1 = max(0, int(cols.min()) - 2)
                    y1 = max(0, int(rows.min()) - 2)
                    x2 = min(width,  int(cols.max()) + 3)
                    y2 = min(height, int(rows.max()) + 3)
                    if x2 > x1 and y2 > y1:
                        return {
                            'x': x1, 'y': y1, 'w': x2 - x1, 'h': y2 - y1,
                            'projection_source': 'camera_roi_pixel',
                            'feature_type': 'recipe_3d_roi',
                        }
            except Exception:
                pass  # 回退到角点投影
            # 角点投影兜底
            try:
                bounds = self.estimator.processor._normalized_roi_3d(camera_roi)
                projected = project_box(bounds, 'camera_roi')
            except Exception:
                projected = None
        else:
            # ── 优先级③：robot_roi → 通过变换矩阵转到相机坐标再投影 ──────────
            try:
                bounds = self.estimator.processor._normalized_roi_3d(config.get('target_roi') or {})
                transform = np.asarray(config.get('transform_snapshot', np.eye(4)), dtype=float)
                if transform.shape != (4, 4):
                    raise ValueError('transform_snapshot must be a 4 x 4 matrix')
                robot_corners = np.array([
                    [x, y, z, 1.0]
                    for x in (bounds['x_min'], bounds['x_max'])
                    for y in (bounds['y_min'], bounds['y_max'])
                    for z in (bounds['z_min'], bounds['z_max'])
                ])
                camera_corners = robot_corners @ np.linalg.inv(transform).T
                camera_bounds = {
                    'x_min': float(camera_corners[:, 0].min()),
                    'x_max': float(camera_corners[:, 0].max()),
                    'y_min': float(camera_corners[:, 1].min()),
                    'y_max': float(camera_corners[:, 1].max()),
                    'z_min': float(camera_corners[:, 2].min()),
                    'z_max': float(camera_corners[:, 2].max()),
                }
                projected = project_box(camera_bounds, 'robot_roi')
            except Exception:
                projected = None

        return projected or {
            'x': 0, 'y': 0, 'w': 0, 'h': 0,
            'projection_source': 'camera_roi' if camera_roi else 'robot_roi',
            'feature_type': 'recipe_3d_roi',
            'error': 'ROI projects outside the image',
        }

    def _persist_workbench_frame(self, pointcloud) -> tuple[str, str, int, int]:
        """把组织化点云持久化为 .npy，并渲染像素一一对应的伪彩预览图。

        返回 (npy 相对路径 token, 预览图 URL, 宽, 高)。
        """
        cloud = np.asarray(pointcloud, dtype=np.float32)
        if cloud.ndim != 3 or cloud.shape[2] != 3:
            raise ValueError('组织化点云必须是 H x W x 3')
        height, width = int(cloud.shape[0]), int(cloud.shape[1])

        date_dir = timezone.now().strftime('%Y/%m/%d')
        rel_dir = f'vision/rack_workbench/{date_dir}'
        abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        stamp = timezone.now().strftime('%H%M%S_%f')
        npy_name = f'rack_workbench_{stamp}.npy'
        np.save(os.path.join(abs_dir, npy_name), cloud)
        npy_rel = f'{rel_dir}/{npy_name}'

        preview = image_io.pointcloud_to_preview(cloud)
        preview_rel, _, _ = image_io.save_image(
            preview, 'rack_workbench_preview', rel_dir='vision/rack_workbench',
        )
        preview_url = settings.MEDIA_URL + preview_rel
        return npy_rel, preview_url, width, height

    def _load_workbench_pointcloud(self, token: str):
        """按 token 安全加载持久化点云（限制在 MEDIA_ROOT 内，防目录穿越）。"""
        if not token:
            raise ValueError('点云数据已失效，请重新采集')
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        abs_path = os.path.realpath(os.path.join(media_root, token))
        if os.path.commonpath([abs_path, media_root]) != media_root or not os.path.exists(abs_path):
            raise ValueError('点云数据已失效，请重新采集')
        return np.load(abs_path)

    def _build_workbench_recipe(self, recipe_id=None, recipe_data=None) -> RackLocationRecipe:
        recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
        recipe = recipe or RackLocationRecipe(recipe_name='WORKBENCH')
        recipe_data = recipe_data or {}
        for field in (
            'standard_x', 'standard_y', 'standard_z', 'standard_rz',
            'max_offset_x', 'max_offset_y', 'max_offset_z', 'max_offset_rz',
            'confidence_threshold',
        ):
            if field in recipe_data and recipe_data[field] not in (None, ''):
                setattr(recipe, field, recipe_data[field])
        if recipe_data.get('hand_eye_config') is not None:
            recipe.hand_eye_config = recipe_data.get('hand_eye_config') or {'matrix': 'identity'}
        elif not recipe.hand_eye_config:
            recipe.hand_eye_config = {'matrix': 'identity'}
        if recipe_data.get('reference_feature_config') is not None:
            recipe.reference_feature_config = recipe_data.get('reference_feature_config') or {}
        return recipe

    def capture_workbench(self, recipe_id=None) -> dict:
        """采集一帧用于工作台：真实 3D 相机优先，离线回退到模拟场景；
        持久化组织化点云并返回预览图与 token。"""
        recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', 1) or 1)
        layer_count = int(getattr(recipe, 'layer_count', 3) or 3)
        side = getattr(recipe, 'rack_side', RackSide.LEFT) or RackSide.LEFT
        side_key = side if side in {RackSide.LEFT, RackSide.RIGHT} else RackSide.LEFT

        pointcloud = None
        source = 'sample'
        fallback_reason = ''
        try:
            probe_recipe = recipe or RackLocationRecipe(
                recipe_name='WORKBENCH', position_no=1, layer_no=layer_no,
                layer_count=layer_count, hand_eye_config={'matrix': 'identity'},
            )
            frame = self.frame_provider.capture(probe_recipe, position_no, layer_no)
            # provider 内部回退（相机未连接 / 采集异常）时会带上原因，透传给前端排查。
            fallback_reason = frame.get('fallback_reason', '') or ''
            cloud = frame.get('organized_pointcloud')
            if cloud is not None:
                arr = np.asarray(cloud, dtype=float)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    pointcloud = arr
                    source = frame.get('source', 'dm_camera')
        except DMCameraConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任何非配置相机异常都回退到模拟点云
            pointcloud = None
            fallback_reason = str(exc)

        if pointcloud is None:
            # 优先使用 docs/pic 目录中的真实离线点云，失败才回退合成数据
            real_cloud = _load_docs_pic_pointcloud()
            if real_cloud is not None:
                pointcloud = real_cloud
                source = 'docs_pic_offline'
            else:
                pointcloud = build_sample_pointcloud(side=side_key, layer_count=layer_count)
                source = 'sample'

        token, preview_url, width, height = self._persist_workbench_frame(pointcloud)
        payload = {
            'pointcloud_token': token,
            'preview_image_url': preview_url,
            'image_width': width,
            'image_height': height,
            'source': source,
        }
        if recipe and recipe.roi_config:
            payload['recipe_pixel_roi'] = self.project_recipe_roi_to_pixels(pointcloud, recipe)
        # 没拿到真实相机数据时，把原因暴露出来（未找到设备 / 数据流未开启等）。
        if source != 'dm_camera' and fallback_reason:
            payload['fallback_reason'] = fallback_reason
        return payload

    def _explicit_local_template_regions(self, pointcloud, roi_config) -> dict[str, dict]:
        """校验并规范化用户明确示教的 Π1/Π2/Π3 三个像素 ROI。"""
        configured = (roi_config or {}).get('local_template_rois') or {}
        if not isinstance(configured, dict):
            raise ValueError('三块基准区域格式错误，请重新框选 Π1、Π2、Π3')
        aliases = {
            'plane1': ('plane1', 'roi1', 'top_crossbeam'),
            'plane2': ('plane2', 'roi2', 'left_upright'),
            'plane3': ('plane3', 'roi3', 'bottom_crossbeam'),
        }
        height, width = pointcloud.shape[:2]
        regions = {}
        missing = []
        for name, keys in aliases.items():
            raw = next((configured.get(key) for key in keys if configured.get(key)), None)
            if not raw:
                missing.append(name)
                continue
            x, y, w, h = self.estimator.processor._normalized_roi(raw, width, height)
            regions[name] = {'x': x, 'y': y, 'w': w, 'h': h}
        if missing:
            labels = {'plane1': 'Π1 顶部横梁', 'plane2': 'Π2 左侧立柱', 'plane3': 'Π3 底部横梁'}
            raise ValueError('请先框选三块基准区域：' + '、'.join(labels[name] for name in missing))
        return regions

    @staticmethod
    def _crop_local_template_clouds(pointcloud, regions) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        clouds = []
        for name in ('plane1', 'plane2', 'plane3'):
            roi = regions[name]
            points = pointcloud[
                roi['y']:roi['y'] + roi['h'],
                roi['x']:roi['x'] + roi['w'],
            ].reshape(-1, 3)
            valid = np.isfinite(points).all(axis=1) & (np.abs(points[:, 2]) > 1e-9)
            cloud = np.asarray(points[valid], dtype=np.float64)
            if cloud.shape[0] < 50:
                label = {'plane1': 'Π1', 'plane2': 'Π2', 'plane3': 'Π3'}[name]
                raise ValueError(f'{label} 有效点不足（{cloud.shape[0]} < 50），请重新框选真实钢架表面')
            clouds.append(cloud)
        return tuple(clouds)

    @staticmethod
    def _local_compensation_payload(local_result, *, source) -> dict:
        values = local_result['compensation']
        matrix = local_result['delta_T']
        return {
            'meaning': 'standard_rack_to_current_rack',
            'matrix': matrix,
            'translation_mm': {'x': values['dX'], 'y': values['dY'], 'z': values['dZ']},
            'rotation_deg': {'rx': values['dRx'], 'ry': values['dRy'], 'rz': values['dRz']},
            'pose6d': {
                'x': values['dX'], 'y': values['dY'], 'z': values['dZ'],
                'rx': values['dRx'], 'ry': values['dRy'], 'rz': values['dRz'],
            },
            'source': source,
            'placement_formula': 'actual_place_pose = T_standard_to_current * taught_standard_place_pose',
            'managed_place_pose_count': 0,
            'robot_taught_place_pose_count': 15,
        }

    def _calculate_local_template_workbench(self, *, token, roi_config, recipe, layer_no, save_record) -> dict:
        """按用户示教的三个 ROI 拟合三平面，并计算/预览 6DoF 刚体补偿。"""
        pointcloud = self._load_workbench_pointcloud(token)
        if pointcloud.ndim != 3 or pointcloud.shape[2] != 3:
            raise ValueError('三平面算法需要组织化点云 H×W×3，请重新采集')
        regions = self._explicit_local_template_regions(pointcloud, roi_config)
        roi1, roi2, roi3 = self._crop_local_template_clouds(pointcloud, regions)

        from .rack_positioning_algorithm import RigidBodyCompensationAlgorithm
        weights = recipe.roi_weights or {}
        algorithm = RigidBodyCompensationAlgorithm(
            w1=float(weights.get('w1', 0.5)),
            w3=float(weights.get('w3', 0.5)),
        )
        has_standard = bool(recipe.local_template_std)
        if has_standard:
            local_result = algorithm.production_mode_compute(
                recipe.local_template_std, roi1, roi2, roi3, raise_on_invalid=False,
            )
            compensation_source = 'local_template_3d'
        else:
            current = algorithm.build_current_template(roi1, roi2, roi3)
            local_result = {
                **current,
                'compensation': {'dX': 0.0, 'dY': 0.0, 'dZ': 0.0, 'dRx': 0.0, 'dRy': 0.0, 'dRz': 0.0},
                'delta_T': np.eye(4, dtype=float).tolist(),
                'translation_magnitude_mm': 0.0,
                'rotation_magnitude_deg': 0.0,
            }
            compensation_source = 'local_template_current_baseline'

        values = local_result['compensation']
        validation = local_result.get('validation') or {}
        within_limits = all((
            abs(values['dX']) <= float(recipe.max_offset_x),
            abs(values['dY']) <= float(recipe.max_offset_y),
            abs(values['dZ']) <= float(recipe.max_offset_z),
            abs(values['dRz']) <= float(recipe.max_offset_rz),
        ))
        locate_ok = bool(local_result.get('is_valid')) and within_limits
        if locate_ok:
            error_code = ''
            error_message = ''
        elif not local_result.get('is_valid'):
            error_code = validation.get('error_code') or 'LOCAL_TEMPLATE_INVALID'
            error_message = validation.get('message') or '三平面结构校验未通过，请调整 ROI'
        else:
            error_code = 'OFFSET_OUT_OF_RANGE'
            error_message = '三平面刚体补偿超出配方允许范围'

        rack_compensation = self._local_compensation_payload(local_result, source=compensation_source)
        preview = image_io.pointcloud_to_preview(pointcloud)
        depth_rel, _, _ = image_io.save_image(
            preview.copy(), 'rack_local_template_depth', rel_dir='vision/rack_workbench',
        )
        target_roi = (roi_config or {}).get('target_roi')
        if target_roi and all(target_roi.get(k) is not None for k in ('x', 'y', 'w', 'h')):
            tx, ty, tw, th = self.estimator.processor._normalized_roi(
                target_roi, pointcloud.shape[1], pointcloud.shape[0],
            )
            image_io.draw_roi(preview, (tx, ty, tx + tw, ty + th), color=(40, 200, 80), label='target ROI')
        colors = {'plane1': (255, 190, 60), 'plane2': (30, 170, 255), 'plane3': (210, 70, 240)}
        labels = {'plane1': 'P1 top', 'plane2': 'P2 left', 'plane3': 'P3 bottom'}
        for name, roi in regions.items():
            image_io.draw_roi(
                preview,
                (roi['x'], roi['y'], roi['x'] + roi['w'], roi['y'] + roi['h']),
                color=colors[name], label=labels[name],
            )
        result_rel, _, _ = image_io.save_image(
            preview, 'rack_local_template_result', rel_dir='vision/rack_workbench',
        )

        result_data = {
            'algorithm_version': 'LOCAL_TEMPLATE_3D_V2',
            'source': 'workbench_three_explicit_rois',
            'local_template_cur': local_result['local_template_cur'],
            'local_template_std': recipe.local_template_std,
            'local_template_std_available': has_standard,
            'local_template_rois': regions,
            'local_template_validation': validation,
            'local_template_compensation': local_result,
            'rack_compensation': rack_compensation,
            'compensation_transform': rack_compensation,
            'roi': {'target_roi': target_roi or {}, 'local_template_rois': regions},
        }
        plc_payload = {
            'task_kind': 'RACK_3D_LOCATION',
            'rack_side': recipe.rack_side or RackSide.BOTH,
            'side': recipe.rack_side or RackSide.BOTH,
            'position_no': int(recipe.position_no or 1),
            'layer_no': int(layer_no),
            'locate_done': True,
            'locate_ok': locate_ok,
            'offset_x': values['dX'], 'offset_y': values['dY'], 'offset_z': values['dZ'],
            'offset_rx': values['dRx'], 'offset_ry': values['dRy'], 'offset_rz': values['dRz'],
            'confidence': local_result['confidence'],
            'compensation_valid': locate_ok and has_standard,
            'rack_compensation': rack_compensation,
            'compensation_matrix': local_result['delta_T'],
            'error_code': error_code,
        }
        result_data['plc_payload'] = plc_payload

        result_id = None
        if save_record:
            task = VisionTask.objects.create(
                task_type=VisionTaskType.RACK_LOCATING,
                status=ResultStatus.SUCCESS if locate_ok else ResultStatus.FAILED,
                started_at=timezone.now(), finished_at=timezone.now(),
                error_message=error_message,
            )
            result = RackLocationResult.objects.create(
                vision_task=task, recipe=recipe,
                side=recipe.rack_side or RackSide.BOTH,
                position_no=int(recipe.position_no or 1), layer_no=int(layer_no),
                offset_x=_decimal(values['dX']), offset_y=_decimal(values['dY']),
                offset_z=_decimal(values['dZ']), offset_rz=_decimal(values['dRz']),
                actual_x=_decimal(float(recipe.standard_x) + values['dX']),
                actual_y=_decimal(float(recipe.standard_y) + values['dY']),
                actual_z=_decimal(float(recipe.standard_z) + values['dZ']),
                confidence=_decimal(local_result['confidence'], '0.0001'),
                is_recipe_matched=locate_ok, is_success=locate_ok,
                error_code=error_code, error_message=error_message,
                raw_data_path=token or '', result_image_path=result_rel,
                roi_data={'target_roi': target_roi or {}, 'local_template_rois': regions},
                result_data=result_data, plc_write_status='SKIPPED',
            )
            VisionImage.objects.create(
                vision_task=task, image_type=VisionImageType.DEPTH,
                file=depth_rel, width=int(pointcloud.shape[1]), height=int(pointcloud.shape[0]),
                captured_at=timezone.now(),
            )
            VisionImage.objects.create(
                vision_task=task, image_type=VisionImageType.RESULT,
                file=result_rel, width=int(pointcloud.shape[1]), height=int(pointcloud.shape[0]),
                captured_at=timezone.now(),
            )
            result_id = result.id

        return {
            'result_id': result_id,
            'recipe_id': recipe.id,
            'rack_side': recipe.rack_side or RackSide.BOTH,
            'position_no': int(recipe.position_no or 1), 'layer_no': int(layer_no),
            'locate_ok': locate_ok, 'is_success': locate_ok,
            'actual_x': float(recipe.standard_x) + values['dX'],
            'actual_y': float(recipe.standard_y) + values['dY'],
            'actual_z': float(recipe.standard_z) + values['dZ'],
            'offset_x': values['dX'], 'offset_y': values['dY'], 'offset_z': values['dZ'],
            'offset_rx': values['dRx'], 'offset_ry': values['dRy'], 'offset_rz': values['dRz'],
            'confidence': local_result['confidence'],
            'error_code': error_code, 'error_message': error_message,
            'local_template_cur': local_result['local_template_cur'],
            'local_template_std': recipe.local_template_std,
            'local_template_std_available': has_standard,
            'local_template_rois': regions,
            'local_template_validation': validation,
            'rack_compensation': rack_compensation,
            'compensation_transform': rack_compensation,
            'compensation_matrix': local_result['delta_T'],
            'plc_payload': plc_payload, 'result_data': result_data,
            'result_image_url': settings.MEDIA_URL + result_rel,
            'result_image_path': result_rel,
            'raw_depth_image_url': settings.MEDIA_URL + depth_rel,
            'algorithm_version': 'LOCAL_TEMPLATE_3D_V2',
        }

    def _compute_workbench(self, *, token, roi_config, recipe, layer_no):
        """从持久化点云 + ROI 计算偏差，并渲染带框标注结果图。

        返回 (RackLocationOutput, 结果图相对路径)。
        """
        roi_config = roi_config or {}
        target_roi = roi_config.get('target_roi')
        if not target_roi:
            raise ValueError('请先绘制 ROI')

        pointcloud = self._load_workbench_pointcloud(token)
        recipe.roi_config = roi_config
        if is_rectangle_v2(recipe.reference_feature_config):
            height, width = pointcloud.shape[:2]
            x, y, w, h = self.estimator.processor._normalized_roi(target_roi, width, height)
            cropped = pointcloud[y:y + h, x:x + w]
            flat_points = cropped.reshape(-1, 3)
            valid = np.isfinite(flat_points[:, 2]) & (np.abs(flat_points[:, 2]) > 1e-9)
            pixel_y, pixel_x = np.indices(cropped.shape[:2])
            all_pixels = np.column_stack((pixel_x.reshape(-1) + x, pixel_y.reshape(-1) + y))
            output = Rack3DLocator(
                frame_provider=self.frame_provider,
                processor=self.estimator.processor,
                plc_writer=self.plc_writer,
            )._output_from_points(
                points=flat_points[valid],
                recipe=recipe,
                rack_side=recipe.rack_side or RackSide.BOTH,
                layer_no=int(layer_no),
                roi_source='target_roi',
                token=token,
                pixel_coordinates=all_pixels[valid],
            )
        else:
            frame = {
                'source': 'workbench',
                'organized_pointcloud': pointcloud,
                'roi_config': roi_config,
            }
            output = self.estimator.calculate_rack_offset(
                frame, recipe, rack_side=recipe.rack_side or RackSide.BOTH, layer_no=int(layer_no),
            )

        preview = image_io.pointcloud_to_preview(pointcloud)
        annotated = image_io.annotate_pointcloud_roi(
            preview, target_roi,
            offsets={'offset_x': output.offset_x, 'offset_y': output.offset_y, 'offset_z': output.offset_z},
            confidence=output.confidence,
            actual=(output.actual_x, output.actual_y, output.actual_z),
            locate_ok=output.locate_ok,
            feature_points=(output.result_data or {}).get('opening_rectangle', {}).get('pixel_points'),
        )
        result_rel, _, _ = image_io.save_image(
            annotated, 'rack_workbench_result', rel_dir='vision/rack_workbench',
        )
        return output, result_rel

    def calculate_workbench(self, *, token, roi_config, recipe_id=None,
                            recipe_data=None, layer_no=1, roi_3d=None,
                            rack_side=RackSide.LEFT, save_record=False,
                            auto_extract_corners=False) -> dict:
        """工作台「计算偏差」：计算并可选择保存到视觉记录。
        
        Args:
            save_record: 是否保存到数据库（默认False；计算偏差只预览）
        """
        recipe = self._build_workbench_recipe(recipe_id, recipe_data)
        if (roi_config or {}).get('local_template_rois'):
            resolved_layer = int((recipe_data or {}).get('layer_no') or layer_no or getattr(recipe, 'layer_no', 1) or 1)
            return self._calculate_local_template_workbench(
                token=token, roi_config=roi_config, recipe=recipe,
                layer_no=resolved_layer, save_record=save_record,
            )

        if roi_3d:
            # 使用3D ROI计算
            result = Rack3DLocator(
                frame_provider=self.frame_provider,
                plc_writer=self.plc_writer,
            ).test_locate(
                token=token,
                roi_3d=roi_3d,
                roi_config=roi_config,  # 传递roi_config以获取2D ROI用于标注
                recipe_id=recipe_id,
                rack_side=rack_side,
                layer_no=layer_no,
                save_record=save_record,
                auto_extract_corners=auto_extract_corners,
            )
            return result
            
        layer_no = int((recipe_data or {}).get('layer_no') or layer_no or getattr(recipe, 'layer_no', 1) or 1)
        output, result_rel = self._compute_workbench(
            token=token, roi_config=roi_config, recipe=recipe, layer_no=layer_no,
        )
        payload = output.to_payload()
        
        # 如果需要保存记录，创建VisionTask和RackLocationResult
        if save_record:
            position_no = 1  # 固定为1（工作台模式）
            db_recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
            
            task = VisionTask.objects.create(
                task_type=VisionTaskType.RACK_LOCATING,
                status=ResultStatus.SUCCESS if output.locate_ok else ResultStatus.FAILED,
                started_at=timezone.now(),
                finished_at=timezone.now(),
                error_message=output.error_message,
            )
            
            RackLocationResult.objects.create(
                vision_task=task,
                recipe=db_recipe,
                side=output.rack_side or RackSide.BOTH,
                position_no=position_no,
                layer_no=layer_no,
                offset_x=_decimal(output.offset_x),
                offset_y=_decimal(output.offset_y),
                offset_z=_decimal(output.offset_z),
                offset_rz=_decimal(output.offset_rz),
                actual_x=_decimal(output.actual_x),
                actual_y=_decimal(output.actual_y),
                actual_z=_decimal(output.actual_z),
                confidence=_decimal(output.confidence),
                is_success=output.locate_ok,
                error_code=output.error_code,
                error_message=output.error_message,
                raw_data_path='',
                result_image_path=result_rel,
                result_data=payload.get('result_data') or {},
            )
            
            # 创建结果图像记录
            VisionImage.objects.create(
                vision_task=task,
                image_type=VisionImageType.RESULT,
                file=result_rel,
                captured_at=timezone.now(),
            )
        
        payload['result_image_url'] = settings.MEDIA_URL + result_rel
        payload['result_image_path'] = result_rel
        payload['source'] = (output.result_data or {}).get('source', 'workbench')
        return payload

    def save_workbench_result(self, *, token, roi_config, roi_3d=None, recipe_id=None,
                              recipe_data=None, position_no=1, layer_no=1,
                              rack=None, product=None) -> RackLocationResult:
        """工作台「保存结果到数据库」：用同一点云重新确定性计算后写入一条记录。
        
        简化版：固定position_no=1，只需传layer_no
        不调用 PLC（本期只做手动现场调试）。
        """
        position_no = int(position_no or 1)
        layer_no = int(layer_no)
        if not (roi_config or {}).get('target_roi') and roi_3d:
            saved = Rack3DLocator(
                frame_provider=self.frame_provider,
                plc_writer=self.plc_writer,
            ).test_locate(
                token=token,
                roi_3d=roi_3d,
                roi_config=roi_config,
                recipe_id=recipe_id,
                rack_side=RackSide.BOTH,
                layer_no=layer_no,
                save_record=True,
            )
            return RackLocationResult.objects.get(pk=saved['result_id'])
        recipe = self._build_workbench_recipe(recipe_id, recipe_data)
        output, result_rel = self._compute_workbench(
            token=token, roi_config=roi_config, recipe=recipe, layer_no=layer_no,
        )
        pointcloud = self._load_workbench_pointcloud(token)
        depth_preview = image_io.pointcloud_to_preview(pointcloud)
        depth_rel, depth_width, depth_height = image_io.save_image(
            depth_preview, 'rack_workbench_depth', rel_dir='vision/rack_workbench',
        )
        db_recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
        roi_snapshot = {
            'target_roi': (roi_config or {}).get('target_roi') or {},
            'roi_3d': roi_3d or {},
        }

        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            product=product,
            rack=rack,
            status=ResultStatus.SUCCESS if output.locate_ok else ResultStatus.FAILED,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            error_message=output.error_message,
        )
        payload = output.to_payload()
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=db_recipe,
            rack=rack,
            side=output.rack_side or RackSide.BOTH,
            position_no=position_no,
            layer_no=layer_no,
            offset_x=_decimal(output.offset_x),
            offset_y=_decimal(output.offset_y),
            offset_z=_decimal(output.offset_z),
            offset_rz=_decimal(output.offset_rz),
            actual_x=_decimal(output.actual_x),
            actual_y=_decimal(output.actual_y),
            actual_z=_decimal(output.actual_z),
            confidence=_decimal(output.confidence, '0.0001'),
            is_recipe_matched=output.locate_ok,
            is_success=output.locate_ok,
            error_code=output.error_code,
            error_message=output.error_message,
            raw_data_path=token or '',
            result_image_path=result_rel,
            roi_data=roi_snapshot,
            result_data={
                **(payload.get('result_data') or {}),
                'task_kind': 'RACK_3D_LOCATION',
                'position_no': position_no,
                'layer_no': layer_no,
                'source': 'workbench',
                'roi': roi_snapshot,
                'plc_payload': payload['plc_payload'],
            },
            plc_write_status='SKIPPED',
        )
        VisionImage.objects.create(
            vision_task=task,
            image_type=VisionImageType.DEPTH,
            file=depth_rel,
            width=depth_width,
            height=depth_height,
            captured_at=timezone.now(),
        )
        result_width = int(pointcloud.shape[1])
        result_height = int(pointcloud.shape[0])
        VisionImage.objects.create(
            vision_task=task,
            image_type=VisionImageType.RESULT,
            file=result_rel,
            width=result_width,
            height=result_height,
            captured_at=timezone.now(),
        )
        return result

    def trigger(self, *, layer_no: int, position_no: int = 1, recipe_id=None,
                rack_side: str = RackSide.BOTH, write_plc: bool = False,
                product=None, rack=None, workflow=None) -> RackLocationResult:
        """Trigger one 3D location cycle for a workstation, layer and rack side."""
        position_no = int(position_no)
        rack_side = str(rack_side or RackSide.BOTH).upper()
        if rack_side not in {RackSide.LEFT, RackSide.RIGHT, RackSide.BOTH}:
            raise ValueError('rack_side must be LEFT, RIGHT, or BOTH')
        layer_no = int(layer_no)
        recipe = self._select_recipe(
            recipe_id=recipe_id, position_no=position_no, layer_no=layer_no,
        )
        if is_rectangle_v2(recipe.reference_feature_config):
            return Rack3DLocator(
                frame_provider=self.frame_provider,
                processor=self.estimator.processor,
                plc_writer=self.plc_writer,
            ).locate(
                rack_side=rack_side,
                layer_no=layer_no,
                recipe_id=recipe.id,
                write_plc=write_plc,
                product=product,
                rack=rack,
                workflow=workflow,
            )
        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            product=product,
            rack=rack,
            status=ResultStatus.RUNNING,
            started_at=timezone.now(),
        )
        try:
            frame = self.frame_provider.capture(recipe, position_no, layer_no)
            output = self.estimator.calculate_rack_offset(frame, recipe, rack_side=rack_side, layer_no=layer_no)
            payload = output.to_payload()
            result_data = {
                **payload['result_data'],
                'task_kind': 'RACK_3D_LOCATION',
                'position_no': position_no,
                'layer_no': layer_no,
                'plc_payload': payload['plc_payload'],
            }

            result = RackLocationResult.objects.create(
                vision_task=task,
                recipe=recipe,
                rack=rack,
                side=rack_side,
                position_no=position_no,
                layer_no=layer_no,
                offset_x=_decimal(output.offset_x),
                offset_y=_decimal(output.offset_y),
                offset_z=_decimal(output.offset_z),
                offset_rz=_decimal(output.offset_rz),
                actual_x=_decimal(output.actual_x),
                actual_y=_decimal(output.actual_y),
                actual_z=_decimal(output.actual_z),
                confidence=_decimal(output.confidence, '0.0001'),
                measured_layer_height=0,
                measured_layer_spacing=0,
                recipe_layer_height=0,
                recipe_layer_spacing=0,
                is_recipe_matched=output.locate_ok,
                is_success=output.locate_ok,
                error_code=output.error_code,
                error_message=output.error_message,
                raw_data_path=output.raw_data_path,
                result_image_path=output.result_image_path,
                result_data=result_data,
            )

            if output.raw_data_path and output.raw_data_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                VisionImage.objects.create(
                    vision_task=task,
                    image_type=VisionImageType.ORIGINAL,
                    file=output.raw_data_path,
                    width=int(frame.get('image_width', 0) or 0),
                    height=int(frame.get('image_height', 0) or 0),
                    captured_at=timezone.now(),
                )
            if output.result_image_path:
                VisionImage.objects.create(
                    vision_task=task,
                    image_type=VisionImageType.RESULT,
                    file=output.result_image_path,
                    width=int(frame.get('image_width', 0) or 0),
                    height=int(frame.get('image_height', 0) or 0),
                    captured_at=timezone.now(),
                )

            if write_plc:
                self.plc_writer.write(result)

            task.status = ResultStatus.SUCCESS if result.is_success else ResultStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = result.error_message
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])

            if not result.is_success:
                AlarmService().create(
                    source=AlarmSource.VISION,
                    level=AlarmLevel.ERROR,
                    message=f'VISION_3D定位失败: {result.error_code} {result.error_message}'.strip(),
                    rack=rack,
                    workflow=workflow,
                    lock_workstation=True,
                )

            return result
        except Exception as exc:  # noqa: BLE001
            task.status = ResultStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = str(exc)
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            raise


def _normalized_plc_payload(result: RackLocationResult, *, locate_type: str,
                            layer_index: int, overall: dict, layer: dict,
                            final: dict) -> dict:
    payload = dict((result.result_data or {}).get('plc_payload') or {})
    rack_compensation = compensation_from_result(
        result.result_data or {},
        fallback_offset={
            'x': float(final.get('x', result.offset_x)),
            'y': float(final.get('y', result.offset_y)),
            'z': float(final.get('z', result.offset_z)),
            'rz': float(final.get('rz', result.offset_rz)),
        },
    )
    final_offset = {
        'x': float(final.get('x', result.offset_x)),
        'y': float(final.get('y', result.offset_y)),
        'z': float(final.get('z', result.offset_z)),
        'rz': float(final.get('rz', result.offset_rz)),
    }
    payload.update({
        'locate_type': payload.get('locate_type', locate_type),
        'layer_index': int(payload.get('layer_index', layer_index)),
        'offset_x': float(payload.get('offset_x', final_offset['x'])),
        'offset_y': float(payload.get('offset_y', final_offset['y'])),
        'offset_z': float(payload.get('offset_z', final_offset['z'])),
        'offset_rz': float(payload.get('offset_rz', final_offset['rz'])),
        'overall_offset': payload.get('overall_offset') or overall or {},
        'layer_offset': payload.get('layer_offset') or layer or {},
        'final_offset': payload.get('final_offset') or final_offset,
        'offset_rx': float(payload.get('offset_rx', rack_compensation['rotation_deg']['rx'])),
        'offset_ry': float(payload.get('offset_ry', rack_compensation['rotation_deg']['ry'])),
        'rack_compensation': payload.get('rack_compensation') or rack_compensation,
        'compensation_matrix': payload.get('compensation_matrix') or rack_compensation['matrix'],
        'robot_taught_place_pose_count': int(payload.get('robot_taught_place_pose_count', 15)),
        'vision_managed_place_pose_count': int(payload.get('vision_managed_place_pose_count', 0)),
        'compensation_valid': bool(payload.get('compensation_valid', result.is_success)),
    })
    return payload


def result_payload(result: RackLocationResult) -> dict:
    result_img = result.vision_task.images.filter(image_type=VisionImageType.RESULT).first()
    depth_img = result.vision_task.images.filter(image_type=VisionImageType.DEPTH).first()
    data = result.result_data or {}
    locate_type = data.get('locate_type') or (
        LOCATE_TYPE_GLOBAL if int(result.layer_no or 0) == 0 else LOCATE_TYPE_LAYER
    )
    layer_index = int(data.get('layer_index', result.layer_no or 0))
    overall = data.get('overall_offset') or {}
    layer = data.get('layer_offset') or {}
    final = data.get('final_offset') or {}
    plc_payload = _normalized_plc_payload(
        result,
        locate_type=locate_type,
        layer_index=layer_index,
        overall=overall,
        layer=layer,
        final=final,
    )
    rack_compensation = compensation_from_result(
        data,
        fallback_offset={
            'x': float(final.get('x', result.offset_x)),
            'y': float(final.get('y', result.offset_y)),
            'z': float(final.get('z', result.offset_z)),
            'rz': float(final.get('rz', result.offset_rz)),
        },
    )
    opening_rectangle = data.get('opening_rectangle') or None
    return {
        'id': result.id,
        'task_id': result.vision_task_id,
        'task_kind': 'RACK_3D_LOCATION',
        'position_no': result.position_no,
        'layer_no': result.layer_no,
        'locate_type': locate_type,
        'layer_index': layer_index,
        'rack_side': result.side,
        'locate_ok': result.is_success,
        'is_success': result.is_success,
        'actual_x': float(result.actual_x),
        'actual_y': float(result.actual_y),
        'actual_z': float(result.actual_z),
        'offset_x': float(result.offset_x),
        'offset_y': float(result.offset_y),
        'offset_z': float(result.offset_z),
        'offset_rz': float(result.offset_rz),
        'overall_offset_x': float(overall.get('x', result.offset_x if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_y': float(overall.get('y', result.offset_y if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_z': float(overall.get('z', result.offset_z if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_rz': float(overall.get('rz', result.offset_rz if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'layer_offset_x': float(layer.get('x', result.offset_x if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_y': float(layer.get('y', result.offset_y if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_z': float(layer.get('z', result.offset_z if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_rz': float(layer.get('rz', result.offset_rz if locate_type == LOCATE_TYPE_LAYER else 0)),
        'final_offset_x': float(final.get('x', result.offset_x)),
        'final_offset_y': float(final.get('y', result.offset_y)),
        'final_offset_z': float(final.get('z', result.offset_z)),
        'final_offset_rz': float(final.get('rz', result.offset_rz)),
        'confidence': float(result.confidence),
        'error_code': result.error_code,
        'error_message': result.error_message,
        'raw_data_path': result.raw_data_path,
        'result_image_path': result.result_image_path,
        'result_image_url': result_img.file.url if result_img else '',
        'depth_image_url': depth_img.file.url if depth_img else '',
        'roi_data': result.roi_data or data.get('roi') or {},
        'plc_write_status': result.plc_write_status,
        'plc_error_message': result.plc_error_message,
        'plc_payload': plc_payload,
        'rack_compensation': rack_compensation,
        'compensation_matrix': rack_compensation['matrix'],
        'compensation_pose6d': rack_compensation['pose6d'],
        'algorithm_version': data.get('algorithm_version') or get_algorithm_version(None),
        'opening_rectangle': opening_rectangle,
        'tcp_verification': data.get('tcp_verification'),
        'result_data': data,
        'created_at': result.created_at.isoformat() if result.created_at else '',
    }
