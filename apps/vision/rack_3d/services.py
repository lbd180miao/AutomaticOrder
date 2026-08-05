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
    def execute_positioning(
        self,
        recipe_id: int,
        layer_no: int,
        save: bool = True,
    ) -> Dict[str, Any]:
        """执行单层完整定位流程，返回结果字典。"""
        from apps.vision.models import RackLocationRecipe

        try:
            recipe = RackLocationRecipe.objects.get(id=recipe_id)
        except RackLocationRecipe.DoesNotExist as exc:
            raise ConfigurationError(EC.RECIPE_NOT_FOUND, f"配方不存在: {recipe_id}") from exc

        logger.info("[%s] 开始定位: 配方=%s, 层=%d", self.mode, recipe.recipe_name, layer_no)

        # 1) 采集点云
        pc = self.depth_camera_provider.capture_pointcloud(recipe_id=recipe_id, layer_no=layer_no)

        # 2) 取手眼矩阵与机器人位姿
        T_fc = self.hand_eye_provider.get_hand_eye_matrix(recipe_id)
        T_bf = self.robot_pose_provider.get_robot_pose_matrix(layer_no, recipe_id)

        # 3) 坐标转换：相机 -> 机器人基坐标系
        robot_cloud = self.processor.transform_to_robot_coords(pc['data'], T_fc, T_bf)

        # 4) 加载并裁剪 ROI
        rois = self._load_rois(recipe_id, layer_no)
        crops = self._crop_all_rois(robot_cloud, rois)

        # 5) 三轴定位
        z_res = self.algorithm.detect_support_plane(crops[ROI_ROLE_SUPPORT])
        y_res = self.algorithm.detect_front_edge(crops[ROI_ROLE_EDGE])
        x_res = self.algorithm.detect_pillar(crops[ROI_ROLE_PILLAR])

        # 6) 补偿计算
        std_x, std_y, std_z = float(recipe.standard_x), float(recipe.standard_y), float(recipe.standard_z)
        offsets = self.calculator.calculate_offsets(
            x_res['x_actual'], y_res['y_actual'], z_res['z_actual'], std_x, std_y, std_z
        )
        compensations = self.calculator.calculate_compensations(**offsets)
        rack_compensation = compensation_from_output(
            offset_x=offsets['offset_x'],
            offset_y=offsets['offset_y'],
            offset_z=offsets['offset_z'],
            offset_rz=0,
        )

        # 7) 校验
        confidence = self.calculator.calculate_overall_confidence(
            x_res['confidence'], y_res['confidence'], z_res['confidence']
        )
        is_valid, error_msg = self.calculator.validate_result(
            offsets['offset_x'], offsets['offset_y'], offsets['offset_z'],
            float(recipe.max_offset_x), float(recipe.max_offset_y), float(recipe.max_offset_z),
            confidence, float(recipe.confidence_threshold),
        )

        result = {
            'mode': self.mode,
            'recipe_id': recipe_id,
            'layer_no': layer_no,
            'actual_x': x_res['x_actual'],
            'actual_y': y_res['y_actual'],
            'actual_z': z_res['z_actual'],
            'standard_x': std_x, 'standard_y': std_y, 'standard_z': std_z,
            **offsets,
            **compensations,
            'rack_compensation': rack_compensation,
            'compensation_transform': rack_compensation,
            'compensation_matrix': rack_compensation['matrix'],
            'robot_taught_place_pose_count': 15,
            'vision_managed_place_pose_count': 0,
            'confidence': confidence,
            'is_success': is_valid,
            'error_message': error_msg or '',
            'frame_index': pc.get('frame_index'),
            'point_count': int(robot_cloud.shape[0]),
            'raw_data_path': pc.get('raw_data_path', ''),
            'result_image_path': pc.get('result_image_path', ''),
            'algorithm_details': {
                'z_detection': z_res,
                'y_detection': y_res,
                'x_detection': x_res,
                'rack_compensation': rack_compensation,
                'compensation_transform': rack_compensation,
            },
        }

        if save:
            ids = self._save_result(recipe, layer_no, result)
            result.update(ids)

        logger.info("[%s] 定位完成: success=%s, confidence=%.3f", self.mode, is_valid, confidence)
        return result

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
        ).order_by('priority')

        roi_map: Dict[str, Dict[str, float]] = {}
        for roi in qs:
            role = _ROI_TYPE_TO_ROLE.get(roi.roi_type)
            if role and role not in roi_map:  # priority 已排序，取第一个
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

    def _crop_all_rois(
        self, robot_cloud: np.ndarray, rois: Dict[str, Dict[str, float]]
    ) -> Dict[str, np.ndarray]:
        crops: Dict[str, np.ndarray] = {}
        for role, bounds in rois.items():
            cropped = self.processor.crop_roi(robot_cloud, **bounds)
            if cropped.shape[0] > 5000:
                cropped = self.processor.downsample(cropped, voxel_size=3.0)
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
            side=recipe.rack_side,
            position_no=recipe.position_no,
            layer_no=layer_no,
            actual_x=_dec(result['actual_x']),
            actual_y=_dec(result['actual_y']),
            actual_z=_dec(result['actual_z']),
            offset_x=_dec(result['offset_x']),
            offset_y=_dec(result['offset_y']),
            offset_z=_dec(result['offset_z']),
            confidence=_dec(result['confidence']),
            is_success=result['is_success'],
            error_message=result.get('error_message', ''),
            raw_data_path=result.get('raw_data_path', ''),
            result_image_path=result.get('result_image_path', ''),
            result_data=result.get('algorithm_details', {}),
        )
        logger.info("定位结果已保存: result_id=%d, task_id=%d", record.id, task.id)
        return {'result_id': record.id, 'task_id': task.id}
