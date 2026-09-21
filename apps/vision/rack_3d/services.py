"""
主服务协调器 (Rack Positioning Service)

协调 Provider、处理器、算法与计算器，完成单层料架定位的完整流程：
  加载配方 → 采集点云 → 取手眼/位姿矩阵 → 坐标转换 → 加载并裁剪 ROI
  → 三轴定位 → 计算补偿 → 校验 → 保存结果

支持 MOCK / REAL 双模式（由 ProviderFactory 依据 mode 决定数据来源）。

Requirements: 1.1, 2.1-2.3, 3.5, 4.1-4.4, 5.1, 6.1, 7.1, 8.1-8.5, 9.1-9.6, 14.10-14.11
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import numpy as np
from django.conf import settings
from django.db import transaction

from apps.vision.rack_compensation import compensation_from_output

from .providers import ProviderFactory
from .processors import PointCloudProcessor
from .algorithms import PositioningAlgorithm
from .calculators import CompensationCalculator
from .config import load_config, quality_score
from .fusion import fuse_frames
from .exceptions import (
    RackPositioningErrorCode as EC,
    RackPositioningException,
    ROIError,
    ConfigurationError,
)

logger = logging.getLogger(__name__)

# RackLocationROI3DEnhanced.roi_type -> 逻辑角色
ROI_ROLE_SUPPORT = 'support'
ROI_ROLE_EDGE = 'edge'
ROI_ROLE_PILLAR = 'pillar'

_ROI_TYPE_TO_ROLE = {
    'SUPPORT_PLANE': ROI_ROLE_SUPPORT,
    'FRONT_EDGE': ROI_ROLE_EDGE,
    'PILLAR': ROI_ROLE_PILLAR,
    'SIDE_EDGE': ROI_ROLE_PILLAR,
}


def _dec(value: float) -> Decimal:
    """float -> Decimal，保留 3 位小数（匹配模型 decimal_places=3）。"""
    return Decimal(str(round(float(value), 3)))


class RackPositioningService:
    """料架 3D 定位主服务。"""

    def __init__(self, mode: Optional[str] = None, **provider_kwargs):
        self.mode = (mode or getattr(settings, 'RACK_3D_POSITIONING_MODE', 'MOCK')).upper()
        self.hand_eye_provider = ProviderFactory.create_hand_eye_provider(self.mode, **provider_kwargs)
        self.robot_pose_provider = ProviderFactory.create_robot_pose_provider(self.mode, **provider_kwargs)
        self.depth_camera_provider = ProviderFactory.create_depth_camera_provider(self.mode, **provider_kwargs)
        self.processor = PointCloudProcessor()
        self.algorithm = PositioningAlgorithm()
        self.calculator = CompensationCalculator()

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def execute_positioning(self, recipe_id: int, layer_no: int, save: bool = True) -> Dict[str, Any]:
        """Always return a diagnostic result; failed measurements expose no compensation."""
        from apps.vision.models import RackLocationRecipe
        recipe = None
        config = load_config()
        frames, artifacts = [], {}
        seen_frame_indices = set()
        result = {
            'mode': self.mode, 'recipe_id': recipe_id, 'layer_no': layer_no,
            'actual_x': None, 'actual_y': None, 'actual_z': None,
            'confidence': 0.0, 'is_success': False, 'error_code': '', 'error_message': '',
            'algorithm_details': {'algorithm_version': 'geometry_v3', 'frames': frames},
        }
        details = result['algorithm_details']
        try:
            recipe = RackLocationRecipe.objects.filter(id=recipe_id).first()
            if recipe is None:
                raise ConfigurationError(EC.RECIPE_NOT_FOUND, f'配方不存在: {recipe_id}')
            config = load_config(recipe.positioning_config)
            details['parameters'] = config
            if not recipe.enabled or not 1 <= layer_no <= recipe.layer_count:
                raise ConfigurationError(EC.INVALID_PARAMETERS, '配方未启用或层号越界')
            algorithm = PositioningAlgorithm(config)
            rois = self._load_rois(recipe_id, layer_no)
            details['rois'] = rois
            for index in range(config['frame_count']):
                frame = {'index': index, 'is_success': False, 'roi_metrics': {}}
                frames.append(frame)
                try:
                    pc = self.depth_camera_provider.capture_pointcloud(recipe_id=recipe_id, layer_no=layer_no)
                    if self.mode == 'REAL' and config['frame_count'] > 1:
                        frame_id = pc.get('frame_index')
                        if frame_id is None or frame_id in seen_frame_indices:
                            raise RackPositioningException(EC.MULTIFRAME_UNSTABLE, '缺少真实帧号或相机重复返回同一帧')
                        seen_frame_indices.add(frame_id)
                    frame.update({k: pc.get(k) for k in ('frame_index', 'raw_data_path', 'result_image_path')})
                    result.update({k: pc.get(k, '') for k in ('raw_data_path', 'result_image_path')})
                    result['frame_index'] = pc.get('frame_index')
                    T_fc = self.hand_eye_provider.get_hand_eye_matrix(recipe_id)
                    T_bf = self.robot_pose_provider.get_robot_pose_matrix(layer_no, recipe_id)
                    cloud = self.processor.transform_to_robot_coords(pc['data'], T_fc, T_bf)
                    frame['point_count'] = len(cloud)
                    frame['T_flange_camera'] = np.asarray(T_fc).tolist()
                    frame['T_base_flange'] = np.asarray(T_bf).tolist()
                    result['point_count'] = len(cloud)
                    crops = self._crop_all_rois(cloud, rois, config, frame['roi_metrics'], artifacts, index)
                    support = rois[ROI_ROLE_SUPPORT]
                    xy = [(support[f'{a}_min'] + support[f'{a}_max']) / 2 for a in ('x', 'y')]
                    frame['z_detection'] = algorithm.detect_support_plane(crops[ROI_ROLE_SUPPORT], reference_xy=xy)
                    frame['y_detection'] = algorithm.detect_front_edge(crops[ROI_ROLE_EDGE])
                    frame['x_detection'] = algorithm.detect_pillar(crops[ROI_ROLE_PILLAR])
                    for axis, role in (('x', 'pillar'), ('y', 'edge'), ('z', 'support')):
                        detection = frame[f'{axis}_detection']
                        metric = frame['roi_metrics'][role]
                        detection['quality_scores'].update({
                            'density': min(1.0, metric['filtered_density'] / config['target_density']),
                            'points': min(1.0, metric['filtered_count'] / config['target_points']),
                        })
                        detection['confidence'] = quality_score(detection['quality_scores'])
                    frame['is_success'] = True
                except RackPositioningException as exc:
                    frame.update(error_code=exc.error_code, error_message=exc.message, failure_details=exc.details)
            valid = [f for f in frames if f['is_success']]
            if not valid:
                first = frames[0]
                raise RackPositioningException(first['error_code'], first['error_message'], first.get('failure_details'))
            fused, fusion = fuse_frames(valid, config)
            details['fusion'] = fusion
            kept = [valid[i] for i in fusion['accepted_indices']]
            for axis in 'xyz':
                result[f'actual_{axis}'] = float(fused['xyz'.index(axis)])
                # Keep a representative fit plus all frame-specific fits in frames.
                details[f'{axis}_detection'] = kept[0][f'{axis}_detection']
                result[f'standard_{axis}'] = float(getattr(recipe, f'standard_{axis}'))
            confidence = min(f[f'{a}_detection']['confidence'] for f in kept for a in 'xyz')
            confidence = min(confidence, fusion['confidence'])
            result['confidence'] = confidence
            offsets = self.calculator.calculate_offsets(*fused, *(result[f'standard_{a}'] for a in 'xyz'))
            result.update(offsets)
            max_offsets = [float(getattr(recipe, f'max_offset_{a}')) for a in 'xyz']
            if not self.calculator.validate_offsets(*offsets.values(), *max_offsets):
                raise RackPositioningException(EC.OFFSET_OUT_OF_RANGE, '相对标准坐标偏差超限', offsets)
            self._validate_history(recipe, layer_no, fused, config, details)
            if confidence < float(recipe.confidence_threshold):
                raise RackPositioningException(EC.LOW_CONFIDENCE, '综合置信度低于配方阈值', {'confidence': confidence})
            result.update(self.calculator.calculate_compensations(**offsets))
            compensation = compensation_from_output(**offsets, offset_rz=0)
            result.update(rack_compensation=compensation, compensation_transform=compensation,
                          compensation_matrix=compensation['matrix'], robot_taught_place_pose_count=15,
                          vision_managed_place_pose_count=0, is_success=True)
            details.update(rack_compensation=compensation, compensation_transform=compensation)
        except RackPositioningException as exc:
            result.update(error_code=exc.error_code, error_message=exc.message)
            details['failure'] = exc.to_dict()
        except Exception as exc:
            logger.exception('定位过程中发生异常')
            result.update(error_code=EC.INTERNAL_ERROR, error_message=f'定位异常: {type(exc).__name__}: {exc}')
            details['failure'] = {'code': EC.INTERNAL_ERROR, 'message': result['error_message']}
        if not result['is_success'] and save and config['save_failure_artifacts'] and artifacts:
            try:
                details['debug_artifacts'] = self._save_debug_artifacts(artifacts)
            except Exception as exc:
                logger.exception('保存诊断点云失败')
                details['debug_artifact_error'] = str(exc)
        details['error_code'] = result['error_code']
        if save:
            # Do not swallow persistence errors or claim that an unsaved result was saved.
            result.update(self._save_result(recipe, layer_no, result))
        return result

    @staticmethod
    def _validate_history(recipe, layer_no, xyz, config, details):
        from apps.vision.models import RackLocationResult
        limit = config['max_history_jump_mm']
        if limit is None:
            details['history_check'] = {'status': 'disabled'}
            return
        previous = RackLocationResult.objects.filter(recipe=recipe, layer_no=layer_no,
            is_success=True, result_data__algorithm_version='geometry_v3').order_by('-created_at', '-id').first()
        if previous is None:
            details['history_check'] = {'status': 'no_baseline'}
            return
        delta = np.abs(xyz - [float(getattr(previous, f'actual_{a}')) for a in 'xyz'])
        details['history_check'] = {'result_id': previous.id, 'delta_mm': delta.tolist(), 'limit_mm': limit}
        if np.any(delta > limit):
            raise RackPositioningException(EC.GEOMETRY_INCONSISTENT, '相对历史成功测量突变', details['history_check'])

    @staticmethod
    def _save_debug_artifacts(artifacts):
        from pathlib import Path
        from uuid import uuid4
        from PIL import Image, ImageDraw
        relative = Path('vision/rack_3d/debug') / uuid4().hex
        folder = Path(settings.MEDIA_ROOT) / relative
        folder.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(folder / 'rois.npz', **artifacts)
        image = Image.new('RGB', (900, max(220, 220 * len(artifacts))), 'white')
        draw = ImageDraw.Draw(image)
        for row, (name, cloud) in enumerate(artifacts.items()):
            draw.text((10, row * 220 + 5), f'{name}: {len(cloud)} points; XY / XZ / YZ (mm)', fill='black')
            if not len(cloud):
                continue
            sample = cloud[::max(1, int(np.ceil(len(cloud) / 2000)))]
            for panel, axes in enumerate(((0, 1), (0, 2), (1, 2))):
                points = sample[:, axes]
                low, high = points.min(0), points.max(0)
                pixels = (points - low) / np.maximum(high - low, 1e-6) * [260, 165]
                for x, y in pixels:
                    draw.point((int(x) + panel * 300 + 15, row * 220 + 195 - int(y)), fill=(25, 85, 160))
                draw.text((panel * 300 + 10, row * 220 + 200), f'{low.round(1)} .. {high.round(1)}', fill='black')
        image.save(folder / 'projections.png')
        return {'roi_clouds': (relative / 'rois.npz').as_posix(),
                'projection_image': (relative / 'projections.png').as_posix()}

    def capture_and_transform(
        self,
        recipe_id: int,
        layer_no: int,
        max_preview_points: int = 4000,
    ) -> Dict[str, Any]:
        """采集点云并转换到机器人基坐标系，返回预览用（降采样）点集与边界。

        供前端「采集点云」按钮渲染 Canvas；不做定位计算、不落库。
        """
        pc = self.depth_camera_provider.capture_pointcloud(recipe_id=recipe_id, layer_no=layer_no)
        T_fc = self.hand_eye_provider.get_hand_eye_matrix(recipe_id)
        T_bf = self.robot_pose_provider.get_robot_pose_matrix(layer_no, recipe_id)
        robot_cloud = self.processor.transform_to_robot_coords(pc['data'], T_fc, T_bf)

        preview = robot_cloud
        if preview.shape[0] > max_preview_points:
            step = int(np.ceil(preview.shape[0] / max_preview_points))
            preview = preview[::step]

        bounds = {}
        if robot_cloud.shape[0]:
            bounds = {
                'x_min': float(robot_cloud[:, 0].min()), 'x_max': float(robot_cloud[:, 0].max()),
                'y_min': float(robot_cloud[:, 1].min()), 'y_max': float(robot_cloud[:, 1].max()),
                'z_min': float(robot_cloud[:, 2].min()), 'z_max': float(robot_cloud[:, 2].max()),
            }
        return {
            'mode': self.mode,
            'frame_index': pc.get('frame_index'),
            'point_count': int(robot_cloud.shape[0]),
            'preview_points': preview.round(2).tolist(),
            'bounds': bounds,
        }

    # ------------------------------------------------------------------
    # ROI 加载与裁剪
    # ------------------------------------------------------------------
    def _load_rois(self, recipe_id: int, layer_no: int) -> Dict[str, Dict[str, float]]:
        """从 RackLocationROI3DEnhanced 加载当前层的 support/edge/pillar ROI 边界。"""
        from apps.vision.models import RackLocationROI3DEnhanced

        qs = RackLocationROI3DEnhanced.objects.filter(
            recipe_id=recipe_id, layer_no=layer_no, enabled=True
        ).order_by('priority', 'id')

        roi_map: Dict[str, Dict[str, float]] = {}
        for roi in qs:
            role = _ROI_TYPE_TO_ROLE.get(roi.roi_type)
            if role and role not in roi_map:  # priority 已排序，取第一个
                if roi.coordinate_system != 'ROBOT':
                    raise ROIError(EC.ROI_INVALID_BOUNDS, f'{role}: 定位 ROI 必须使用机器人基坐标系')
                roi_map[role] = {
                    'x_min': float(roi.x_min), 'x_max': float(roi.x_max),
                    'y_min': float(roi.y_min), 'y_max': float(roi.y_max),
                    'z_min': float(roi.z_min), 'z_max': float(roi.z_max),
                }

        missing = [r for r in (ROI_ROLE_SUPPORT, ROI_ROLE_EDGE, ROI_ROLE_PILLAR) if r not in roi_map]
        if missing:
            raise ROIError(
                EC.ROI_NOT_FOUND,
                f"配方 {recipe_id} 第 {layer_no} 层缺少 ROI: {missing}",
                {'missing_roles': missing},
            )
        return roi_map

    def _crop_all_rois(self, robot_cloud, rois, config=None, metrics=None, artifacts=None, frame_index=0):
        config = load_config(config)
        metrics = metrics if metrics is not None else {}
        artifacts = artifacts if artifacts is not None else {}
        crops = {}
        for role, bounds in rois.items():
            extents = np.array([bounds[f'{a}_max'] - bounds[f'{a}_min'] for a in 'xyz'])
            if not np.isfinite(list(bounds.values())).all() or np.any(extents <= 0):
                raise ROIError(EC.ROI_INVALID_BOUNDS, f'{role}: ROI 边界无效')
            volume = float(np.prod(extents))
            cropped = self.processor.crop_roi(robot_cloud, **bounds)
            artifacts[f'frame_{frame_index}_{role}_raw'] = cropped
            metric = {'raw_count': len(cropped), 'volume_mm3': volume, 'raw_density': len(cropped) / volume}
            metrics[role] = metric
            if len(cropped) < config['min_roi_points'] or metric['raw_density'] < config['min_density']:
                raise ROIError(EC.ROI_NO_TARGET, f'{role}: ROI 无目标或有效点密度不足', {'role': role, **metric})
            cropped = self.processor.filter_outliers(cropped, config['nb_neighbors'], config['std_ratio'])
            metric.update(filtered_count=len(cropped), filtered_density=len(cropped) / volume)
            artifacts[f'frame_{frame_index}_{role}_filtered'] = cropped
            if len(cropped) < config['min_roi_points'] or metric['filtered_density'] < config['min_density']:
                raise ROIError(EC.ROI_NO_TARGET, f'{role}: 滤波后有效点不足', {'role': role, **metric})
            if len(cropped) > config['downsample_threshold']:
                cropped = self.processor.downsample(cropped, voxel_size=config['voxel_size_mm'])
            metric['algorithm_count'] = len(cropped)
            crops[role] = cropped
        return crops

    # ------------------------------------------------------------------
    # 结果保存
    # ------------------------------------------------------------------
    @transaction.atomic
    def _save_result(self, recipe, layer_no: int, result: Dict[str, Any]) -> Dict[str, int]:
        from apps.core.constants import ResultStatus, VisionTaskType
        from apps.vision.models import VisionTask, RackLocationResult

        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            status=ResultStatus.SUCCESS if result['is_success'] else ResultStatus.FAILED,
            error_message=result.get('error_message', ''),
        )
        record = RackLocationResult.objects.create(
            vision_task=task,
            recipe=recipe,
            side=recipe.rack_side if recipe else 'BOTH',
            position_no=recipe.position_no if recipe else 1,
            layer_no=layer_no,
            actual_x=_dec(result.get('actual_x') or 0),
            actual_y=_dec(result.get('actual_y') or 0),
            actual_z=_dec(result.get('actual_z') or 0),
            offset_x=_dec(result.get('offset_x') or 0),
            offset_y=_dec(result.get('offset_y') or 0),
            offset_z=_dec(result.get('offset_z') or 0),
            confidence=_dec(result['confidence']),
            is_success=result['is_success'],
            error_code=result.get('error_code', ''),
            roi_data=result.get('algorithm_details', {}).get('rois', {}),
            error_message=result.get('error_message', ''),
            raw_data_path=result.get('raw_data_path', ''),
            result_image_path=result.get('result_image_path', ''),
            result_data=result.get('algorithm_details', {}),
        )
        logger.info("定位结果已保存: result_id=%d, task_id=%d", record.id, task.id)
        return {'result_id': record.id, 'task_id': task.id}
