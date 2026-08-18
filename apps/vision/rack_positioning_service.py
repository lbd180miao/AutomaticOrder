"""
料架定位服务

提供完整的料架定位业务逻辑，包括：
1. 点云预处理
2. ROI裁剪
3. 刚性基准提取
4. 偏移计算
5. 结果保存
"""
import numpy as np
import logging
from typing import Dict, Optional, Tuple
from django.db import transaction
from decimal import Decimal

from .rack_positioning_algorithm import (
    RackPositioningAlgorithm,
    RackPositioningResult
)
from .roi_3d_service import ROI3DService
from .coordinate_transform import CoordinateTransformService
from .models import RackLocationRecipe, RackLocationResult
from .models_3d_roi import ROI3DType

logger = logging.getLogger(__name__)


class RackPositioningService:
    """料架定位服务"""
    
    def __init__(self):
        """初始化服务"""
        self.algorithm = RackPositioningAlgorithm()
        self.roi_service = ROI3DService()
        self.transform_service = CoordinateTransformService()
    
    def process_layer_positioning(
        self,
        recipe_id: int,
        layer_no: int,
        pointcloud: np.ndarray,
        robot_pose: Optional[np.ndarray] = None,
        coordinate_system: str = 'ROBOT',
        vision_task_id: Optional[int] = None,
        rack_id: Optional[int] = None,
        algorithm_params: Optional[Dict] = None
    ) -> RackPositioningResult:
        """
        处理单层料架定位（完整流程）
        
        流程：
        1. 获取配方信息
        2. 坐标转换（如果需要）
        3. 裁剪ROI
        4. 提取刚性基准
        5. 计算偏移
        6. 保存结果（如果提供了vision_task_id）
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            pointcloud: 点云数据 (N, 3) [x, y, z]，坐标系由coordinate_system指定
            robot_pose: 机器人位姿 (可选，用于坐标转换)
            coordinate_system: 点云坐标系 ('ROBOT'/'CAMERA')
            vision_task_id: 视觉任务ID（可选，用于保存结果）
            rack_id: 料架ID（可选，用于保存结果）
            algorithm_params: 算法参数（可选）
            
        Returns:
            RackPositioningResult: 定位结果
        """
        algorithm_params = algorithm_params or {}
        
        # 1. 获取配方
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        
        logger.info(
            f"开始处理料架定位: 配方={recipe.recipe_name}, "
            f"层={layer_no}, 点云={pointcloud.shape[0]}点"
        )
        
        # 2. 坐标转换（如果点云是相机坐标系）
        if coordinate_system == 'CAMERA':
            if robot_pose is None:
                raise ValueError("相机坐标系点云需要提供robot_pose进行坐标转换")
            
            if recipe.hand_eye_calibration is None:
                raise ValueError("配方未关联手眼标定配置，无法进行坐标转换")
            
            logger.info("执行坐标转换: 相机坐标 → 机器人坐标")
            pointcloud = self.transform_service.transform_pointcloud_to_robot(
                pointcloud=pointcloud,
                T_base_flange=robot_pose,
                calibration_id=recipe.hand_eye_calibration.id
            )
            coordinate_system = 'ROBOT'
        
        # 3. 裁剪ROI
        logger.info(f"裁剪第{layer_no}层的ROI")
        cropped_clouds = self.roi_service.crop_pointcloud_by_layer(
            pointcloud=pointcloud,
            recipe_id=recipe_id,
            layer_no=layer_no,
            roi_type=None  # 裁剪所有类型
        )
        
        # 提取各类型ROI的点云
        support_plane_cloud = cropped_clouds.get(ROI3DType.SUPPORT_PLANE.lower(), np.array([]).reshape(0, 3))
        front_edge_cloud = cropped_clouds.get(ROI3DType.FRONT_EDGE.lower(), np.array([]).reshape(0, 3))
        pillar_cloud = cropped_clouds.get(ROI3DType.PILLAR.lower(), np.array([]).reshape(0, 3))
        
        logger.info(
            f"ROI裁剪完成: "
            f"支撑面={support_plane_cloud.shape[0]}点, "
            f"前边缘={front_edge_cloud.shape[0]}点, "
            f"立柱={pillar_cloud.shape[0]}点"
        )
        
        # 4. 计算定位（提取刚性基准）
        logger.info("开始提取刚性基准并计算偏移")
        
        # 从配方获取标准位置
        standard_x = float(recipe.standard_x)
        standard_y = float(recipe.standard_y)
        standard_z = float(recipe.standard_z)
        
        # 执行定位算法
        positioning_result = self.algorithm.calculate_rack_position(
            support_plane_cloud=support_plane_cloud,
            front_edge_cloud=front_edge_cloud,
            pillar_cloud=pillar_cloud,
            standard_x=standard_x,
            standard_y=standard_y,
            standard_z=standard_z,
            plane_params=algorithm_params.get('plane_params'),
            edge_params=algorithm_params.get('edge_params'),
            pillar_params=algorithm_params.get('pillar_params')
        )
        
        # 5. 保存结果到数据库（如果提供了vision_task_id）
        if vision_task_id is not None:
            self._save_positioning_result(
                recipe=recipe,
                layer_no=layer_no,
                vision_task_id=vision_task_id,
                rack_id=rack_id,
                positioning_result=positioning_result
            )
        
        logger.info(
            f"料架定位完成: "
            f"偏移 X={positioning_result.offset_x:.2f}mm, "
            f"Y={positioning_result.offset_y:.2f}mm, "
            f"Z={positioning_result.offset_z:.2f}mm, "
            f"成功={positioning_result.is_success}"
        )
        
        return positioning_result
    
    @transaction.atomic
    def _save_positioning_result(
        self,
        recipe: RackLocationRecipe,
        layer_no: int,
        vision_task_id: int,
        rack_id: Optional[int],
        positioning_result: RackPositioningResult
    ) -> RackLocationResult:
        """
        保存定位结果到数据库
        
        Args:
            recipe: 配方
            layer_no: 层号
            vision_task_id: 视觉任务ID
            rack_id: 料架ID
            positioning_result: 定位结果
            
        Returns:
            RackLocationResult: 保存的结果记录
        """
        from apps.vision.models import VisionTask
        
        vision_task = VisionTask.objects.get(id=vision_task_id)
        
        # 创建结果记录
        result = RackLocationResult.objects.create(
            vision_task=vision_task,
            recipe=recipe,
            rack_id=rack_id,
            side=recipe.rack_side,
            position_no=recipe.position_no,
            layer_no=layer_no,
            
            # 偏移值
            offset_x=Decimal(str(positioning_result.offset_x)),
            offset_y=Decimal(str(positioning_result.offset_y)),
            offset_z=Decimal(str(positioning_result.offset_z)),
            
            # 实际值
            actual_x=Decimal(str(positioning_result.actual_x)),
            actual_y=Decimal(str(positioning_result.actual_y)),
            actual_z=Decimal(str(positioning_result.actual_z)),
            
            # 置信度（取平均）
            confidence=Decimal(str(
                (positioning_result.confidence_x +
                 positioning_result.confidence_y +
                 positioning_result.confidence_z) / 3
            )),
            
            # 成功标志
            is_success=positioning_result.is_success,
            error_message=positioning_result.error_message,
            
            # 详细数据（JSON格式）
            result_data={
                'confidence_x': positioning_result.confidence_x,
                'confidence_y': positioning_result.confidence_y,
                'confidence_z': positioning_result.confidence_z,
                'standard_x': positioning_result.standard_x,
                'standard_y': positioning_result.standard_y,
                'standard_z': positioning_result.standard_z,
                'plane_result': {
                    'z_position': positioning_result.plane_result.z_position,
                    'z_std': positioning_result.plane_result.z_std,
                    'inliers_count': int(positioning_result.plane_result.inliers.shape[0])
                } if positioning_result.plane_result else None,
                'edge_result': {
                    'y_position': positioning_result.edge_result.y_position,
                    'y_std': positioning_result.edge_result.y_std,
                    'edge_points_count': int(positioning_result.edge_result.edge_points.shape[0])
                } if positioning_result.edge_result else None,
                'pillar_result': {
                    'x_position': positioning_result.pillar_result.x_position,
                    'x_std': positioning_result.pillar_result.x_std,
                    'pillar_points_count': int(positioning_result.pillar_result.pillar_points.shape[0])
                } if positioning_result.pillar_result else None,
            }
        )
        
        logger.info(f"定位结果已保存: ID={result.id}")
        
        return result
    
    def get_positioning_history(
        self,
        recipe_id: int,
        layer_no: Optional[int] = None,
        limit: int = 10
    ) -> list:
        """
        获取定位历史记录
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号（可选）
            limit: 返回记录数
            
        Returns:
            定位结果列表
        """
        queryset = RackLocationResult.objects.filter(
            recipe_id=recipe_id
        ).order_by('-created_at')
        
        if layer_no is not None:
            queryset = queryset.filter(layer_no=layer_no)
        
        return list(queryset[:limit])
    
    def get_average_offsets(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 10
    ) -> Dict:
        """
        获取最近N次的平均偏移值
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            平均偏移值
        """
        results = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no,
            is_success=True
        ).order_by('-created_at')[:count]
        
        if not results:
            return {
                'count': 0,
                'avg_offset_x': 0,
                'avg_offset_y': 0,
                'avg_offset_z': 0,
                'std_offset_x': 0,
                'std_offset_y': 0,
                'std_offset_z': 0
            }
        
        # 计算平均值和标准差
        offsets_x = [float(r.offset_x) for r in results]
        offsets_y = [float(r.offset_y) for r in results]
        offsets_z = [float(r.offset_z) for r in results]
        
        return {
            'count': len(results),
            'avg_offset_x': float(np.mean(offsets_x)),
            'avg_offset_y': float(np.mean(offsets_y)),
            'avg_offset_z': float(np.mean(offsets_z)),
            'std_offset_x': float(np.std(offsets_x)),
            'std_offset_y': float(np.std(offsets_y)),
            'std_offset_z': float(np.std(offsets_z))
        }
    
    def analyze_positioning_stability(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 20
    ) -> Dict:
        """
        分析定位稳定性
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            稳定性分析结果
        """
        results = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no,
            is_success=True
        ).order_by('-created_at')[:count]
        
        if len(results) < 5:
            return {
                'sufficient_data': False,
                'message': '数据不足，需要至少5次成功定位记录'
            }
        
        # 提取数据
        offsets_x = np.array([float(r.offset_x) for r in results])
        offsets_y = np.array([float(r.offset_y) for r in results])
        offsets_z = np.array([float(r.offset_z) for r in results])
        confidences = np.array([float(r.confidence) for r in results])
        
        # 计算统计指标
        return {
            'sufficient_data': True,
            'sample_count': len(results),
            
            # X轴稳定性
            'x_mean': float(np.mean(offsets_x)),
            'x_std': float(np.std(offsets_x)),
            'x_range': float(np.ptp(offsets_x)),  # 极差
            'x_cv': float(np.std(offsets_x) / (np.mean(np.abs(offsets_x)) + 1e-6)),  # 变异系数
            
            # Y轴稳定性
            'y_mean': float(np.mean(offsets_y)),
            'y_std': float(np.std(offsets_y)),
            'y_range': float(np.ptp(offsets_y)),
            'y_cv': float(np.std(offsets_y) / (np.mean(np.abs(offsets_y)) + 1e-6)),
            
            # Z轴稳定性
            'z_mean': float(np.mean(offsets_z)),
            'z_std': float(np.std(offsets_z)),
            'z_range': float(np.ptp(offsets_z)),
            'z_cv': float(np.std(offsets_z) / (np.mean(np.abs(offsets_z)) + 1e-6)),
            
            # 整体置信度
            'avg_confidence': float(np.mean(confidences)),
            'min_confidence': float(np.min(confidences)),
            
            # 稳定性评级（基于标准差）
            'stability_rating': self._calculate_stability_rating(
                np.std(offsets_x),
                np.std(offsets_y),
                np.std(offsets_z)
            )
        }
    
    def _calculate_stability_rating(
        self,
        std_x: float,
        std_y: float,
        std_z: float
    ) -> str:
        """
        计算稳定性评级
        
        Args:
            std_x, std_y, std_z: 各轴标准差
            
        Returns:
            评级字符串
        """
        # 阈值定义（mm）
        excellent_threshold = 1.0
        good_threshold = 2.0
        fair_threshold = 5.0
        
        max_std = max(std_x, std_y, std_z)
        
        if max_std < excellent_threshold:
            return 'EXCELLENT'  # 优秀
        elif max_std < good_threshold:
            return 'GOOD'       # 良好
        elif max_std < fair_threshold:
            return 'FAIR'       # 一般
        else:
            return 'POOR'       # 较差


# =============================================================================
# V2 刚体变换补偿服务
# =============================================================================

import datetime as _datetime
from django.utils import timezone as _timezone


class RigidBodyCompensationService:
    """
    料架定位补偿服务 V2 —— 局部三维几何模板刚体变换方案。

    职责：
      - 示教阶段：接收三个 ROI 区域的原始点云 → 调用算法建立 T_std → 持久化到数据库
      - 生产阶段：读取配方中的 T_std → 重新拟合当前点云 → 计算 ΔT → 返回 6DoF 补偿量

    输出给 PLC 的最终数据格式：
      {"dX": float, "dY": float, "dZ": float, "dRx": float, "dRy": float, "dRz": float}
      单位：mm 和 度(°)
    """

    def __init__(self, **algo_kwargs):
        from .rack_positioning_algorithm import RigidBodyCompensationAlgorithm
        self._algo = RigidBodyCompensationAlgorithm(**algo_kwargs)

    # ------------------------------------------------------------------
    # 示教阶段
    # ------------------------------------------------------------------

    @transaction.atomic
    def build_standard_template(
        self,
        recipe_id: int,
        roi1_cloud: np.ndarray,
        roi2_cloud: np.ndarray,
        roi3_cloud: np.ndarray,
    ) -> dict:
        """
        示教阶段：建立标准局部坐标系模板并持久化到配方。

        Args:
            recipe_id: 配方 ID
            roi1_cloud: 区域1（上水平面）点云 (N, 3)，单位 mm，相机坐标系
            roi2_cloud: 区域2（左竖直面）点云 (M, 3)，单位 mm，相机坐标系
            roi3_cloud: 区域3（下水平面）点云 (K, 3)，单位 mm，相机坐标系

        Returns:
            {
                "status": "ok",
                "recipe_id": int,
                "template_summary": {...},
                "built_at": "ISO8601"
            }

        Raises:
            RackLocationRecipe.DoesNotExist: 配方不存在
            RackStructureError: 点云质量不合格
        """
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)

        # 调用算法建立模板
        template_dict = self._algo.teach_mode_build_template(roi1_cloud, roi2_cloud, roi3_cloud)

        # 读取权重配置（若配方中有配置则覆盖默认值）
        # （权重已在 RigidBodyCompensationAlgorithm 构造时设定，此处仅记录）

        # 持久化到数据库
        recipe.local_template_std = template_dict
        recipe.local_template_built_at = _timezone.now()
        recipe.local_template_version = template_dict.get("algorithm_version", "v2_rigid_body")
        recipe.save(update_fields=[
            "local_template_std",
            "local_template_built_at",
            "local_template_version",
        ])

        built_at = recipe.local_template_built_at.isoformat()
        logger.info(
            "标准模板已保存 | recipe_id=%s | recipe_name=%s | built_at=%s",
            recipe_id, recipe.recipe_name, built_at,
        )

        return {
            "status": "ok",
            "recipe_id": recipe_id,
            "recipe_name": recipe.recipe_name,
            "template_summary": template_dict.get("template_summary", {}),
            "built_at": built_at,
        }

    # ------------------------------------------------------------------
    # 生产阶段
    # ------------------------------------------------------------------

    def compute_compensation(
        self,
        recipe_id: int,
        roi1_cloud: np.ndarray,
        roi2_cloud: np.ndarray,
        roi3_cloud: np.ndarray,
        save_result: bool = True,
    ) -> dict:
        """
        生产阶段：计算相对于标准模板的 6DoF 刚体补偿偏差。

        Args:
            recipe_id: 配方 ID
            roi1_cloud, roi2_cloud, roi3_cloud: 当前料架三个基准区域的点云
            save_result: 是否将计算结果写入 RackLocationResult 历史记录表

        Returns:
            {
                "status": "ok" | "error",
                "recipe_id": int,
                "compensation": {"dX", "dY", "dZ", "dRx", "dRy", "dRz"},
                "validation": {...},
                "confidence": float,
                "delta_T": [[4x4]],
                "compute_timestamp": str
            }
        """
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)

        # 检查标准模板是否存在
        if not recipe.local_template_std:
            return {
                "status": "error",
                "error_code": "NO_TEMPLATE",
                "message": f"配方 {recipe.recipe_name} 尚未建立标准模板，请先在示教模式下采集并保存标准模板",
                "recipe_id": recipe_id,
            }

        # 调用算法计算补偿（校验失败时不抛异常，而是返回 is_valid=False 的结果）
        from .rack_positioning_algorithm import RackStructureError
        try:
            result = self._algo.production_mode_compute(
                template_std_dict=recipe.local_template_std,
                roi1_cloud=roi1_cloud,
                roi2_cloud=roi2_cloud,
                roi3_cloud=roi3_cloud,
                raise_on_invalid=False,  # 让上层决定是否阻止发送
            )
        except Exception as e:
            logger.exception("补偿计算出现未预期错误 | recipe_id=%s", recipe_id)
            return {
                "status": "error",
                "error_code": "COMPUTE_ERROR",
                "message": str(e),
                "recipe_id": recipe_id,
            }

        result["status"] = "ok" if result.get("is_valid") else "error"
        if not result.get("is_valid"):
            result["error_code"] = result.get("validation", {}).get("error_code", "INVALID_TEMPLATE")
            result["message"] = result.get("validation", {}).get("message", "三平面结构校验未通过")
        result["recipe_id"] = recipe_id
        result["recipe_name"] = recipe.recipe_name

        if save_result:
            self._save_result(recipe, result)

        return result

    # ------------------------------------------------------------------
    # 模板状态管理
    # ------------------------------------------------------------------

    def get_template_status(self, recipe_id: int) -> dict:
        """获取配方模板状态"""
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)
        if not recipe.local_template_std:
            return {
                "has_template": False,
                "recipe_id": recipe_id,
                "recipe_name": recipe.recipe_name,
            }

        tpl = recipe.local_template_std
        return {
            "has_template": True,
            "recipe_id": recipe_id,
            "recipe_name": recipe.recipe_name,
            "built_at": recipe.local_template_built_at.isoformat() if recipe.local_template_built_at else None,
            "algorithm_version": recipe.local_template_version,
            "template_summary": tpl.get("template_summary", {}),
            "plane1_normal": tpl.get("plane1", {}).get("normal"),
            "plane2_normal": tpl.get("plane2", {}).get("normal"),
            "plane3_normal": tpl.get("plane3", {}).get("normal"),
        }

    @transaction.atomic
    def clear_template(self, recipe_id: int) -> dict:
        """清除标准模板（重新示教前调用）"""
        recipe = RackLocationRecipe.objects.get(pk=recipe_id)
        recipe.local_template_std = None
        recipe.local_template_built_at = None
        recipe.save(update_fields=["local_template_std", "local_template_built_at"])
        logger.info("标准模板已清除 | recipe_id=%s | recipe_name=%s", recipe_id, recipe.recipe_name)
        return {"status": "ok", "message": f"配方 {recipe.recipe_name} 的标准模板已清除"}

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _save_result(self, recipe: RackLocationRecipe, result: dict) -> None:
        """将补偿计算结果写入历史记录（非关键路径，失败时仅记录日志）"""
        try:
            comp = result.get("compensation", {})
            RackLocationResult.objects.create(
                recipe=recipe,
                layer_no=getattr(recipe, "layer_no", 0),
                offset_x=comp.get("dX", 0),
                offset_y=comp.get("dY", 0),
                offset_z=comp.get("dZ", 0),
                offset_rz=comp.get("dRz", 0),
                confidence=result.get("confidence", 0),
                is_success=result.get("is_valid", False),
                error_code="" if result.get("is_valid") else result.get("validation", {}).get("error_code", ""),
                error_message="" if result.get("is_valid") else result.get("validation", {}).get("message", ""),
                result_data=result,
            )
        except Exception:
            logger.exception("保存补偿结果到历史记录失败（非致命）| recipe_id=%s", recipe.pk)
