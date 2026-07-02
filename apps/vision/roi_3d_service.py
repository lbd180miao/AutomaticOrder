"""
3D ROI配方服务

提供3D ROI的CRUD操作、模板管理、点云裁剪等功能
"""
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from django.db import transaction
from django.db.models import Q

from .models_3d_roi import (
    RackLocationROI3DEnhanced,
    ROI3DTemplate,
    ROI3DType,
    ROI3DCoordinateSystem
)

logger = logging.getLogger(__name__)


class ROI3DService:
    """3D ROI配方服务"""
    
    @transaction.atomic
    def create_roi(
        self,
        recipe_id: int,
        roi_name: str,
        roi_type: str,
        layer_no: int,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        z_min: float,
        z_max: float,
        position_no: int = 1,
        coordinate_system: str = ROI3DCoordinateSystem.ROBOT,
        priority: int = 100,
        weight: float = 1.0,
        algorithm_params: Optional[Dict] = None,
        description: str = ''
    ) -> RackLocationROI3DEnhanced:
        """
        创建3D ROI
        
        Args:
            recipe_id: 配方ID
            roi_name: ROI名称
            roi_type: ROI类型（MAIN/SUPPORT_PLANE/FRONT_EDGE/PILLAR）
            layer_no: 层号
            x_min, x_max, y_min, y_max, z_min, z_max: 边界坐标
            position_no: 点位序号
            coordinate_system: 坐标系
            priority: 优先级
            weight: 权重
            algorithm_params: 算法参数
            description: 描述
            
        Returns:
            创建的ROI实例
        """
        from .models import RackLocationRecipe
        
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        
        roi = RackLocationROI3DEnhanced.objects.create(
            recipe=recipe,
            roi_name=roi_name,
            roi_type=roi_type,
            position_no=position_no,
            layer_no=layer_no,
            coordinate_system=coordinate_system,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            z_min=z_min,
            z_max=z_max,
            priority=priority,
            weight=weight,
            algorithm_params=algorithm_params or {},
            description=description,
            enabled=True
        )
        
        logger.info(f"创建3D ROI: {roi.roi_name} (类型: {roi.get_roi_type_display()}, 层: {layer_no})")
        return roi
    
    def get_rois_by_layer(
        self,
        recipe_id: int,
        layer_no: int,
        roi_type: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[RackLocationROI3DEnhanced]:
        """
        获取指定层的ROI列表
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            roi_type: ROI类型（可选，不指定则返回所有类型）
            enabled_only: 是否只返回启用的ROI
            
        Returns:
            ROI列表
        """
        queryset = RackLocationROI3DEnhanced.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no
        )
        
        if roi_type:
            queryset = queryset.filter(roi_type=roi_type)
        
        if enabled_only:
            queryset = queryset.filter(enabled=True)
        
        return list(queryset.order_by('priority'))
    
    def get_rois_by_type(
        self,
        recipe_id: int,
        roi_type: str,
        enabled_only: bool = True
    ) -> List[RackLocationROI3DEnhanced]:
        """
        获取指定类型的所有ROI
        
        Args:
            recipe_id: 配方ID
            roi_type: ROI类型
            enabled_only: 是否只返回启用的ROI
            
        Returns:
            ROI列表
        """
        queryset = RackLocationROI3DEnhanced.objects.filter(
            recipe_id=recipe_id,
            roi_type=roi_type
        )
        
        if enabled_only:
            queryset = queryset.filter(enabled=True)
        
        return list(queryset.order_by('layer_no', 'priority'))
    
    def get_layer_roi_summary(self, recipe_id: int, layer_no: int) -> Dict:
        """
        获取指定层的ROI汇总信息
        
        Returns:
            {
                'layer_no': 层号,
                'total_rois': 总ROI数,
                'main_roi': 主ROI,
                'support_plane_rois': [支撑面ROI列表],
                'front_edge_rois': [前边缘ROI列表],
                'pillar_rois': [立柱ROI列表],
                'other_rois': [其他ROI列表]
            }
        """
        rois = self.get_rois_by_layer(recipe_id, layer_no, enabled_only=True)
        
        summary = {
            'layer_no': layer_no,
            'total_rois': len(rois),
            'main_roi': None,
            'support_plane_rois': [],
            'front_edge_rois': [],
            'pillar_rois': [],
            'side_edge_rois': [],
            'other_rois': []
        }
        
        for roi in rois:
            if roi.roi_type == ROI3DType.MAIN:
                if summary['main_roi'] is None or roi.priority < summary['main_roi'].priority:
                    summary['main_roi'] = roi
            elif roi.roi_type == ROI3DType.SUPPORT_PLANE:
                summary['support_plane_rois'].append(roi)
            elif roi.roi_type == ROI3DType.FRONT_EDGE:
                summary['front_edge_rois'].append(roi)
            elif roi.roi_type == ROI3DType.PILLAR:
                summary['pillar_rois'].append(roi)
            elif roi.roi_type == ROI3DType.SIDE_EDGE:
                summary['side_edge_rois'].append(roi)
            else:
                summary['other_rois'].append(roi)
        
        return summary
    
    @transaction.atomic
    def update_roi(
        self,
        roi_id: int,
        **kwargs
    ) -> RackLocationROI3DEnhanced:
        """
        更新ROI
        
        Args:
            roi_id: ROI ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的ROI
        """
        roi = RackLocationROI3DEnhanced.objects.get(id=roi_id)
        
        updatable_fields = [
            'roi_name', 'roi_type', 'layer_no', 'coordinate_system',
            'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max',
            'priority', 'weight', 'algorithm_params', 'enabled', 'description'
        ]
        
        for field, value in kwargs.items():
            if field in updatable_fields and value is not None:
                setattr(roi, field, value)
        
        roi.save()
        logger.info(f"更新3D ROI: {roi.roi_name}")
        return roi
    
    @transaction.atomic
    def delete_roi(self, roi_id: int) -> bool:
        """删除ROI"""
        try:
            roi = RackLocationROI3DEnhanced.objects.get(id=roi_id)
            roi_name = roi.roi_name
            roi.delete()
            logger.info(f"删除3D ROI: {roi_name}")
            return True
        except RackLocationROI3DEnhanced.DoesNotExist:
            return False
    
    @transaction.atomic
    def batch_create_layer_rois(
        self,
        recipe_id: int,
        layer_no: int,
        position_no: int = 1
    ) -> Dict[str, RackLocationROI3DEnhanced]:
        """
        批量创建一层的标准ROI配置
        
        为指定层创建4种标准ROI：
        1. 主定位ROI
        2. 支撑面ROI
        3. 前边缘ROI
        4. 立柱ROI
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            position_no: 点位序号
            
        Returns:
            {
                'main': 主ROI,
                'support_plane': 支撑面ROI,
                'front_edge': 前边缘ROI,
                'pillar': 立柱ROI
            }
        """
        from .models import RackLocationRecipe
        
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        
        # 基于配方的标准位置计算默认ROI
        # 假设层间距为120mm（标准料架）
        layer_spacing = 120
        base_z = float(recipe.standard_z) + (layer_no - 1) * layer_spacing
        
        # 默认ROI尺寸（可根据实际情况调整）
        roi_configs = {
            'main': {
                'roi_name': f'第{layer_no}层主ROI',
                'roi_type': ROI3DType.MAIN,
                'x_min': -200, 'x_max': 200,
                'y_min': -150, 'y_max': 150,
                'z_min': base_z - 20, 'z_max': base_z + 100,
                'priority': 10,
                'weight': 1.0,
                'description': '整体定位区域',
            },
            'support_plane': {
                'roi_name': f'第{layer_no}层支撑面ROI',
                'roi_type': ROI3DType.SUPPORT_PLANE,
                'x_min': -180, 'x_max': 180,
                'y_min': -130, 'y_max': -80,  # 靠近前边缘的支撑面
                'z_min': base_z - 10, 'z_max': base_z + 10,
                'priority': 20,
                'weight': 1.0,
                'description': '用于提取平面，计算Z轴偏移',
                'algorithm_params': {
                    'plane_fit_method': 'ransac',
                    'distance_threshold': 2.0,
                    'min_samples': 100
                }
            },
            'front_edge': {
                'roi_name': f'第{layer_no}层前边缘ROI',
                'roi_type': ROI3DType.FRONT_EDGE,
                'x_min': -180, 'x_max': 180,
                'y_min': -140, 'y_max': -120,  # 前边缘区域
                'z_min': base_z, 'z_max': base_z + 50,
                'priority': 30,
                'weight': 1.0,
                'description': '用于提取边缘线，计算Y轴偏移',
                'algorithm_params': {
                    'edge_detection_method': 'gradient',
                    'gradient_threshold': 50.0,
                    'min_edge_length': 50
                }
            },
            'pillar': {
                'roi_name': f'第{layer_no}层立柱ROI',
                'roi_type': ROI3DType.PILLAR,
                'x_min': -190, 'x_max': -170,  # 左侧立柱
                'y_min': -130, 'y_max': 130,
                'z_min': base_z, 'z_max': base_z + 80,
                'priority': 40,
                'weight': 1.0,
                'description': '用于提取侧边/立柱，计算X轴偏移',
                'algorithm_params': {
                    'pillar_detection_method': 'vertical_edge',
                    'vertical_tolerance': 5.0,
                    'min_pillar_height': 50
                }
            }
        }
        
        created_rois = {}
        for key, config in roi_configs.items():
            roi = self.create_roi(
                recipe_id=recipe_id,
                position_no=position_no,
                layer_no=layer_no,
                **config
            )
            created_rois[key] = roi
        
        logger.info(f"批量创建第{layer_no}层的4种标准ROI")
        return created_rois
    
    def crop_pointcloud(
        self,
        pointcloud: np.ndarray,
        roi: RackLocationROI3DEnhanced
    ) -> np.ndarray:
        """
        使用ROI裁剪点云
        
        Args:
            pointcloud: 点云数据 (N, 3) 或 (N, 4) 或 (N, 6) 格式
                       [x, y, z] 或 [x, y, z, intensity] 或 [x, y, z, r, g, b]
            roi: ROI对象
            
        Returns:
            裁剪后的点云 (M, 3) 或 (M, 4) 或 (M, 6)，M <= N
        """
        if pointcloud.shape[0] == 0:
            return pointcloud
        
        # 提取XYZ坐标
        xyz = pointcloud[:, :3]
        
        # 构建掩码
        mask = (
            (xyz[:, 0] >= float(roi.x_min)) & (xyz[:, 0] <= float(roi.x_max)) &
            (xyz[:, 1] >= float(roi.y_min)) & (xyz[:, 1] <= float(roi.y_max)) &
            (xyz[:, 2] >= float(roi.z_min)) & (xyz[:, 2] <= float(roi.z_max))
        )
        
        # 应用掩码
        cropped = pointcloud[mask]
        
        logger.debug(
            f"ROI裁剪: {pointcloud.shape[0]} → {cropped.shape[0]} 点 "
            f"({roi.roi_name})"
        )
        
        return cropped
    
    def crop_pointcloud_by_layer(
        self,
        pointcloud: np.ndarray,
        recipe_id: int,
        layer_no: int,
        roi_type: Optional[str] = None
    ) -> Dict[str, np.ndarray]:
        """
        使用指定层的ROI裁剪点云
        
        Args:
            pointcloud: 点云数据
            recipe_id: 配方ID
            layer_no: 层号
            roi_type: ROI类型（可选，不指定则裁剪所有类型）
            
        Returns:
            {
                'main': 主ROI裁剪的点云,
                'support_plane': 支撑面ROI裁剪的点云,
                'front_edge': 前边缘ROI裁剪的点云,
                'pillar': 立柱ROI裁剪的点云
            }
        """
        rois = self.get_rois_by_layer(recipe_id, layer_no, roi_type, enabled_only=True)
        
        cropped_clouds = {}
        
        for roi in rois:
            key = roi.roi_type.lower()
            cropped = self.crop_pointcloud(pointcloud, roi)
            
            # 如果同类型有多个ROI，合并点云
            if key in cropped_clouds:
                cropped_clouds[key] = np.vstack([cropped_clouds[key], cropped])
            else:
                cropped_clouds[key] = cropped
        
        return cropped_clouds
    
    # ========== 模板管理 ==========
    
    @transaction.atomic
    def create_template(
        self,
        template_name: str,
        rack_type: str,
        layer_count: int,
        roi_configs: List[Dict],
        default_algorithm_params: Optional[Dict] = None,
        description: str = ''
    ) -> ROI3DTemplate:
        """
        创建ROI模板
        
        Args:
            template_name: 模板名称
            rack_type: 料架类型
            layer_count: 层数
            roi_configs: ROI配置列表
            default_algorithm_params: 默认算法参数
            description: 描述
            
        Returns:
            创建的模板
        """
        template = ROI3DTemplate.objects.create(
            template_name=template_name,
            rack_type=rack_type,
            layer_count=layer_count,
            roi_configs=roi_configs,
            default_algorithm_params=default_algorithm_params or {},
            description=description,
            is_active=True
        )
        
        logger.info(f"创建ROI模板: {template_name}")
        return template
    
    @transaction.atomic
    def apply_template(
        self,
        template_id: int,
        recipe_id: int,
        clear_existing: bool = False
    ) -> List[RackLocationROI3DEnhanced]:
        """
        将模板应用到配方
        
        Args:
            template_id: 模板ID
            recipe_id: 配方ID
            clear_existing: 是否清除现有ROI
            
        Returns:
            创建的ROI列表
        """
        from .models import RackLocationRecipe
        
        template = ROI3DTemplate.objects.get(id=template_id)
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        
        # 清除现有ROI
        if clear_existing:
            RackLocationROI3DEnhanced.objects.filter(recipe=recipe).delete()
            logger.info(f"清除配方 {recipe.recipe_name} 的现有ROI")
        
        # 应用模板
        created_rois = template.apply_to_recipe(recipe)
        
        logger.info(
            f"应用模板 {template.template_name} 到配方 {recipe.recipe_name}，"
            f"创建了 {len(created_rois)} 个ROI"
        )
        
        return created_rois
    
    def get_templates_by_rack_type(
        self,
        rack_type: str,
        active_only: bool = True
    ) -> List[ROI3DTemplate]:
        """获取指定料架类型的模板"""
        queryset = ROI3DTemplate.objects.filter(rack_type=rack_type)
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        return list(queryset)
    
    # ========== 统计和分析 ==========
    
    def get_recipe_roi_statistics(self, recipe_id: int) -> Dict:
        """
        获取配方的ROI统计信息
        
        Returns:
            {
                'total_rois': 总ROI数,
                'by_type': {类型: 数量},
                'by_layer': {层号: 数量},
                'enabled_count': 启用的ROI数,
                'disabled_count': 禁用的ROI数
            }
        """
        rois = RackLocationROI3DEnhanced.objects.filter(recipe_id=recipe_id)
        
        stats = {
            'total_rois': rois.count(),
            'by_type': {},
            'by_layer': {},
            'enabled_count': rois.filter(enabled=True).count(),
            'disabled_count': rois.filter(enabled=False).count(),
        }
        
        # 按类型统计
        for roi_type in ROI3DType:
            count = rois.filter(roi_type=roi_type).count()
            if count > 0:
                stats['by_type'][roi_type.label] = count
        
        # 按层统计
        layers = rois.values_list('layer_no', flat=True).distinct()
        for layer_no in layers:
            stats['by_layer'][layer_no] = rois.filter(layer_no=layer_no).count()
        
        return stats
