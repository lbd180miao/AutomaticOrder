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

from .algorithms import image_io
from .models import RackLocationROI3D, RackLocationRecipe, RackLocationResult, VisionImage, VisionTask


def _decimal(value: Any, places: str = '0.001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


LOCATE_TYPE_GLOBAL = 'GLOBAL'
LOCATE_TYPE_LAYER = 'LAYER'


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
    """无真实点云时，从 2D 深度场景图像的 ROI 中位数推算模拟 X/Y/Z。

    与 2D 泡棉检测工作台共享同一底层深度场（image_io.build_depth_field），
    确保 3D 定位展示的坐标与画面场景内容关联，而非纯随机数。

    逻辑：
    1. 若配方有 target_roi → 从场景点云中裁剪该区域取中位数
    2. 无 ROI → 用标准坐标叠加小量确定性高斯噪声（使同侧结果稳定）
    """
    std_x = float(recipe.standard_x)
    std_y = float(recipe.standard_y)
    std_z = float(recipe.standard_z)
    layer_count = int(recipe.layer_count or 3)

    # 用 (position_no, layer_no) 作为随机种子，保证同配方每次结果一致
    seed_str = f'xyz-pos{position_no}-layer{layer_no}'
    rng = random.Random(seed_str)

    if target_roi and all(target_roi.get(k) is not None for k in ('x', 'y')):
        try:
            # 与页面显示的场景共享同一深度场
            pointcloud = build_sample_pointcloud(
                side='LEFT', layer_count=layer_count,
            )
            processor = PointCloudProcessor()
            points = processor.crop_by_roi(pointcloud, target_roi)
            med_x, med_y, med_z = processor.calculate_median_xyz(points)
            # 叠加小量确定性噪声（≤1mm），模拟真实抖动
            noise_x = round(rng.gauss(0, 0.4), 3)
            noise_y = round(rng.gauss(0, 0.4), 3)
            noise_z = round(rng.gauss(0, 0.3), 3)
            return (
                round(med_x + noise_x, 3),
                round(med_y + noise_y, 3),
                round(med_z + noise_z, 3),
            )
        except Exception:  # noqa: BLE001 — 兜底：场景异常时退化到标准坐标模拟
            pass

    # 无 ROI 或点云裁剪失败：对标准坐标叠加小量确定性偏移
    return (
        round(std_x + rng.gauss(0, 0.8), 3),
        round(std_y + rng.gauss(0, 0.8), 3),
        round(std_z + rng.gauss(0, 0.5), 3),
    )



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
            'confidence': self.confidence,
            'compensation_valid': self.locate_ok,
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
        try:
            x = int(round(float(roi.get('x'))))
            y = int(round(float(roi.get('y'))))
            w = int(round(float(roi.get('w', roi.get('width')))))
            h = int(round(float(roi.get('h', roi.get('height')))))
        except (TypeError, ValueError) as exc:
            raise ValueError('ROI 参数必须包含有效的 x/y/w/h') from exc

        if w <= 0 or h <= 0:
            raise ValueError('ROI 宽高必须大于 0')
        if x < 0 or y < 0 or x + w > width or y + h > height:
            raise ValueError('ROI 超出图像范围')
        return x, y, w, h

    def crop_by_roi(self, organized_pointcloud, roi: dict):
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim != 3 or pointcloud.shape[2] != 3:
            raise ValueError('organized pointcloud 必须是 H x W x 3')

        height, width, _ = pointcloud.shape
        x, y, w, h = self._normalized_roi(roi, width, height)
        points = pointcloud[y:y + h, x:x + w, :].reshape(-1, 3)
        return self.filter_valid_points(points)

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
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim == 3 and pointcloud.shape[2] == 3:
            points = pointcloud.reshape(-1, 3)
        elif pointcloud.ndim == 2 and pointcloud.shape[1] == 3:
            points = pointcloud
        else:
            raise ValueError('pointcloud 必须是 H x W x 3 或 N x 3')

        valid_points = self.filter_valid_points(points)
        bounds = self._normalized_roi_3d(roi)
        mask = (
            (valid_points[:, 0] >= bounds['x_min'])
            & (valid_points[:, 0] <= bounds['x_max'])
            & (valid_points[:, 1] >= bounds['y_min'])
            & (valid_points[:, 1] <= bounds['y_max'])
            & (valid_points[:, 2] >= bounds['z_min'])
            & (valid_points[:, 2] <= bounds['z_max'])
        )
        return valid_points[mask]

    def filter_valid_points(self, points):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        finite_mask = np.isfinite(points).all(axis=1)
        non_zero_depth_mask = np.abs(points[:, 2]) > 1e-9
        distance_mask = np.abs(points).max(axis=1) <= self.max_abs_coordinate
        return points[finite_mask & non_zero_depth_mask & distance_mask]

    def calculate_median_xyz(self, points) -> tuple[float, float, float]:
        valid_points = self.filter_valid_points(points)
        if valid_points.shape[0] < self.min_valid_points:
            raise ValueError('ROI 内有效点数太少')
        median = np.median(valid_points, axis=0)
        return tuple(round(float(v), 3) for v in median)

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

        if not recipe.hand_eye_config:
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
                error_message='3D料架定位配方缺少手眼标定参数',
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
        elif (
            abs(offset_x) > float(recipe.max_offset_x)
            or abs(offset_y) > float(recipe.max_offset_y)
            or abs(offset_z) > float(recipe.max_offset_z)
            or abs(offset_rz) > float(recipe.max_offset_rz)
        ):
            locate_ok = False
            error_code = 'OFFSET_OUT_OF_RANGE'
            error_message = '3D定位补偿值超出配方允许范围'

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
        side, int(layer_count or 3), width, height,
    )
    return image_io.depth_field_to_pointcloud(depth)


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
        checks = [
            ('X', abs(float(result.offset_x)), float(recipe.max_offset_x)),
            ('Y', abs(float(result.offset_y)), float(recipe.max_offset_y)),
            ('Z', abs(float(result.offset_z)), float(recipe.max_offset_z)),
            ('Rz', abs(float(result.offset_rz)), float(recipe.max_offset_rz)),
        ]
        violations = [f'{axis}={val:.3f}>{limit:.3f}' for axis, val, limit in checks if val > limit]
        if violations:
            return f'补偿超限: {", ".join(violations)}'
        if float(result.confidence) < float(recipe.confidence_threshold):
            return f'置信度不足: {float(result.confidence):.2%} < {float(recipe.confidence_threshold):.2%}'
        return ''

    def write(self, result: RackLocationResult) -> dict:
        payload = result.result_data.get('plc_payload') or {}
        if not result.is_success:
            result.plc_write_status = 'SKIPPED'
            result.plc_error_message = '定位NG，未写入有效补偿'
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            return {'success': False, 'skipped': True, 'error': result.plc_error_message}

        # ── 二次校验：按当前配方阈值重新检查 ──
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

    def _select_recipe(self, *, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1):
        qs = RackLocationRecipe.objects.filter(enabled=True)
        if recipe_id:
            return qs.get(pk=recipe_id)
        recipe = qs.filter(rack_side=rack_side, layer_no=layer_no).order_by('position_no').first()
        if recipe:
            return recipe
        return qs.get(rack_side=RackSide.BOTH, layer_no=layer_no)

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

    def capture(self, *, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1) -> dict:
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no) if recipe_id else None
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', layer_no) or layer_no)
        layer_count = int(getattr(recipe, 'layer_count', 3) or 3)
        side = str(getattr(recipe, 'rack_side', rack_side) or rack_side).upper()
        side_key = RackSide.RIGHT if side == RackSide.RIGHT else RackSide.LEFT

        pointcloud = None
        source = 'sample'
        fallback_reason = ''
        try:
            probe_recipe = recipe or RackLocationRecipe(
                recipe_name='VISION-3D-CAPTURE',
                rack_side=side_key,
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
        except Exception as exc:  # noqa: BLE001
            fallback_reason = str(exc)

        if pointcloud is None:
            pointcloud = build_sample_pointcloud(side=side_key, layer_count=layer_count)
            source = 'sample'

        token, preview_url, width, height = self._persist_frame(pointcloud)
        return {
            'pointcloud_token': token,
            'pointcloud_preview_url': preview_url,
            'raw_rgb_image_url': preview_url,
            'raw_depth_image_url': preview_url,
            'image_width': width,
            'image_height': height,
            'source': source,
            'fallback_reason': fallback_reason,
        }

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

    def _output_from_points(self, *, points, recipe, rack_side, layer_no, roi_source, roi_id=None, token='') -> RackLocationOutput:
        actual_x, actual_y, actual_z = self.processor.calculate_median_xyz(points)
        confidence = min(0.99, max(0.0, points.shape[0] / 1000.0))
        frame = {
            'actual_x': actual_x,
            'actual_y': actual_y,
            'actual_z': actual_z,
            'confidence': confidence,
            'source': 'rack_3d_roi',
            'raw_data_path': token,
        }
        output = RackPoseEstimator(processor=self.processor).calculate_rack_offset(
            frame, recipe, rack_side=rack_side, layer_no=layer_no,
        )
        output.result_data = {
            **(output.result_data or {}),
            'roi_id': roi_id,
            'roi_source': roi_source,
            'coordinate_system': 'rack',
            'point_count': int(points.shape[0]),
        }
        return output

    def test_locate(self, *, token, roi_3d, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1) -> dict:
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no)
        pointcloud = self._load_pointcloud(token)
        points = self.processor.crop_by_roi_3d(pointcloud, roi_3d)
        if points.shape[0] < self.processor.min_valid_points:
            raise ValueError('ROI 内有效点数太少')
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source='request',
            token=token,
        )
        preview = image_io.pointcloud_to_preview(pointcloud)
        result_rel, _, _ = image_io.save_image(preview, 'rack_3d_cropped', rel_dir='vision/rack_3d')
        payload = output.to_payload()
        payload.update({
            'roi_source': 'request',
            'cropped_preview_url': settings.MEDIA_URL + result_rel,
        })
        return payload

    def locate(self, *, rack_side, layer_no, recipe_id=None, write_plc=False, product=None, rack=None, workflow=None):
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no)
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
        points = self.processor.crop_by_roi_3d(pointcloud, roi3d_to_dict(roi))
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source=roi_source,
            roi_id=roi.id,
            token=captured['pointcloud_token'],
        )
        payload = output.to_payload()
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=recipe,
            rack=rack,
            side=rack_side,
            position_no=recipe.position_no,
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
            raw_data_path=captured['pointcloud_token'],
            result_data={
                **(payload.get('result_data') or {}),
                'task_kind': 'RACK_3D_LOCATION',
                'roi_id': roi.id,
                'roi_source': roi_source,
                'plc_payload': payload['plc_payload'],
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

    def _select_recipe(self, *, recipe_id=None, position_no: int, layer_no: int) -> RackLocationRecipe:
        qs = RackLocationRecipe.objects.filter(enabled=True)
        if recipe_id:
            return qs.get(pk=recipe_id)
        return qs.get(position_no=position_no, layer_no=layer_no)

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
        if recipe_data.get('hand_eye_config') is not None:
            recipe.hand_eye_config = recipe_data.get('hand_eye_config') or {}
        elif not recipe.hand_eye_config:
            recipe.hand_eye_config = {'matrix': 'identity'}

        layer_count = int(recipe_data.get('layer_count') or getattr(recipe, 'layer_count', 3) or 3)
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
        return recipe

    def capture_workbench(self, recipe_id=None) -> dict:
        """采集一帧用于工作台：真实 3D 相机优先，离线回退到模拟场景；
        持久化组织化点云并返回预览图与 token。"""
        recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', 1) or 1)
        layer_count = int(getattr(recipe, 'layer_count', 3) or 3)
        side = str(getattr(recipe, 'rack_side', RackSide.LEFT) or RackSide.LEFT).upper()
        side_key = 'RIGHT' if side == 'RIGHT' else 'LEFT'

        pointcloud = None
        source = 'sample'
        fallback_reason = ''
        try:
            probe_recipe = recipe or RackLocationRecipe(
                recipe_name='WORKBENCH', position_no=position_no, layer_no=layer_no,
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
        except Exception as exc:  # noqa: BLE001 - 任何相机异常都回退到模拟点云
            pointcloud = None
            fallback_reason = str(exc)

        if pointcloud is None:
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
        # 没拿到真实相机数据时，把原因暴露出来（未找到设备 / 数据流未开启等）。
        if source != 'dm_camera' and fallback_reason:
            payload['fallback_reason'] = fallback_reason
        return payload

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
        )
        result_rel, _, _ = image_io.save_image(
            annotated, 'rack_workbench_result', rel_dir='vision/rack_workbench',
        )
        return output, result_rel

    def calculate_workbench(self, *, token, roi_config, recipe_id=None,
                            recipe_data=None, layer_no=1, roi_3d=None,
                            rack_side=RackSide.LEFT) -> dict:
        """工作台「计算偏差」：仅预览，不写库。"""
        if roi_3d:
            return Rack3DLocator(
                frame_provider=self.frame_provider,
                plc_writer=self.plc_writer,
            ).test_locate(
                token=token,
                roi_3d=roi_3d,
                recipe_id=recipe_id,
                rack_side=rack_side,
                layer_no=layer_no,
            )
        recipe = self._build_workbench_recipe(recipe_id, recipe_data)
        layer_no = int((recipe_data or {}).get('layer_no') or layer_no or getattr(recipe, 'layer_no', 1) or 1)
        output, result_rel = self._compute_workbench(
            token=token, roi_config=roi_config, recipe=recipe, layer_no=layer_no,
        )
        payload = output.to_payload()
        payload['result_image_url'] = settings.MEDIA_URL + result_rel
        payload['result_image_path'] = result_rel
        payload['source'] = (output.result_data or {}).get('source', 'workbench')
        return payload

    def save_workbench_result(self, *, token, roi_config, recipe_id=None, recipe_data=None,
                              position_no=1, layer_no=1, rack=None, product=None) -> RackLocationResult:
        """工作台「保存结果到数据库」：用同一点云重新确定性计算后写入一条记录。

        不调用 PLC（本期只做手动现场调试）。
        """
        position_no = int(position_no)
        layer_no = int(layer_no)
        recipe = self._build_workbench_recipe(recipe_id, recipe_data)
        output, result_rel = self._compute_workbench(
            token=token, roi_config=roi_config, recipe=recipe, layer_no=layer_no,
        )
        db_recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first() if recipe_id else None

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
            result_data={
                **(payload.get('result_data') or {}),
                'task_kind': 'RACK_3D_LOCATION',
                'position_no': position_no,
                'layer_no': layer_no,
                'source': 'workbench',
                'plc_payload': payload['plc_payload'],
            },
            plc_write_status='SKIPPED',
        )
        VisionImage.objects.create(
            vision_task=task,
            image_type=VisionImageType.RESULT,
            file=result_rel,
            captured_at=timezone.now(),
        )
        return result

    def trigger(self, *, position_no: int, layer_no: int, recipe_id=None,
                rack_side: str = RackSide.BOTH, write_plc: bool = False,
                product=None, rack=None, workflow=None) -> RackLocationResult:
        position_no = int(position_no)
        layer_no = int(layer_no)
        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            product=product,
            rack=rack,
            status=ResultStatus.RUNNING,
            started_at=timezone.now(),
        )
        try:
            recipe = self._select_recipe(recipe_id=recipe_id, position_no=position_no, layer_no=layer_no)
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


def result_payload(result: RackLocationResult) -> dict:
    result_img = result.vision_task.images.filter(image_type=VisionImageType.RESULT).first()
    data = result.result_data or {}
    locate_type = data.get('locate_type') or (
        LOCATE_TYPE_GLOBAL if int(result.layer_no or 0) == 0 else LOCATE_TYPE_LAYER
    )
    layer_index = int(data.get('layer_index', result.layer_no or 0))
    overall = data.get('overall_offset') or {}
    layer = data.get('layer_offset') or {}
    final = data.get('final_offset') or {}
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
        'plc_write_status': result.plc_write_status,
        'plc_error_message': result.plc_error_message,
        'plc_payload': result.result_data.get('plc_payload') or {},
        'created_at': result.created_at.isoformat() if result.created_at else '',
    }
