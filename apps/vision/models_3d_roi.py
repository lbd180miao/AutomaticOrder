"""
3D ROI配方模块 - 增强版

用于保存每一层的三维裁剪范围，支持多种ROI类型：
1. 主定位ROI - 整体定位区域
2. 支撑面ROI - 用于计算Z轴偏移
3. 前边缘ROI - 用于计算Y轴偏移
4. 立柱ROI - 用于计算X轴偏移
"""
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel


class ROI3DType(models.TextChoices):
    """3D ROI类型枚举"""
    MAIN = 'MAIN', '主定位ROI'
    SUPPORT_PLANE = 'SUPPORT_PLANE', '支撑面ROI'
    FRONT_EDGE = 'FRONT_EDGE', '前边缘ROI'
    PILLAR = 'PILLAR', '立柱ROI'
    SIDE_EDGE = 'SIDE_EDGE', '侧边缘ROI'
    CUSTOM = 'CUSTOM', '自定义ROI'


class ROI3DCoordinateSystem(models.TextChoices):
    """坐标系类型"""
    ROBOT = 'ROBOT', '机器人基坐标系'
    CAMERA = 'CAMERA', '相机坐标系'
    RACK = 'RACK', '料架坐标系'


class RackLocationROI3DEnhanced(TimeStampedModel):
    """
    增强版3D ROI模型
    
    支持为每一层定义多种类型的ROI，用于不同的定位计算：
    - 主定位ROI：整体定位区域
    - 支撑面ROI：提取平面，计算Z轴偏移
    - 前边缘ROI：提取边缘线，计算Y轴偏移
    - 立柱ROI：提取侧边/立柱，计算X轴偏移
    """
    
    # 关联的配方
    recipe = models.ForeignKey(
        'vision.RackLocationRecipe',
        on_delete=models.CASCADE,
        related_name='enhanced_rois_3d',
        verbose_name='所属配方'
    )
    
    # ROI基本信息
    roi_name = models.CharField(
        '名称',
        max_length=128,
        help_text='例如：第2层主ROI、第2层支撑面ROI'
    )
    roi_type = models.CharField(
        'ROI类型',
        max_length=32,
        choices=ROI3DType.choices,
        default=ROI3DType.MAIN,
        help_text='ROI的功能类型'
    )
    
    # 层信息
    position_no = models.PositiveIntegerField(
        '点位序号',
        default=1,
        db_index=True,
        help_text='对应RackLocationRecipe的position_no'
    )
    layer_no = models.PositiveIntegerField(
        '层号',
        db_index=True,
        help_text='料架的第几层（1, 2, 3...）'
    )
    
    # 坐标系
    coordinate_system = models.CharField(
        '坐标系',
        max_length=32,
        choices=ROI3DCoordinateSystem.choices,
        default=ROI3DCoordinateSystem.ROBOT,
        help_text='ROI坐标所在的坐标系'
    )
    
    # 3D边界框坐标（单位：mm）
    x_min = models.DecimalField(
        'X最小值',
        max_digits=10,
        decimal_places=3,
        help_text='X轴最小值（mm）'
    )
    x_max = models.DecimalField(
        'X最大值',
        max_digits=10,
        decimal_places=3,
        help_text='X轴最大值（mm）'
    )
    y_min = models.DecimalField(
        'Y最小值',
        max_digits=10,
        decimal_places=3,
        help_text='Y轴最小值（mm）'
    )
    y_max = models.DecimalField(
        'Y最大值',
        max_digits=10,
        decimal_places=3,
        help_text='Y轴最大值（mm）'
    )
    z_min = models.DecimalField(
        'Z最小值',
        max_digits=10,
        decimal_places=3,
        help_text='Z轴最小值（mm）'
    )
    z_max = models.DecimalField(
        'Z最大值',
        max_digits=10,
        decimal_places=3,
        help_text='Z轴最大值（mm）'
    )
    
    # 优先级和权重
    priority = models.IntegerField(
        '优先级',
        default=100,
        help_text='数字越小优先级越高，同层同类型ROI按优先级使用'
    )
    weight = models.DecimalField(
        '权重',
        max_digits=5,
        decimal_places=2,
        default=1.0,
        help_text='计算偏移时的权重（0.0-1.0）'
    )
    
    # 算法参数
    algorithm_params = models.JSONField(
        '算法参数',
        default=dict,
        blank=True,
        help_text='特定于ROI类型的算法参数，例如：平面拟合阈值、边缘检测参数等'
    )
    
    # 状态
    enabled = models.BooleanField(
        '启用',
        default=True,
        help_text='是否启用此ROI'
    )
    
    # 描述和备注
    description = models.TextField(
        '描述',
        blank=True,
        help_text='ROI的详细说明'
    )
    
    class Meta:
        db_table = 'vision_rack_location_roi_3d_enhanced'
        verbose_name = '3D ROI配方'
        verbose_name_plural = verbose_name
        ordering = ['recipe', 'position_no', 'layer_no', 'roi_type', 'priority']
        indexes = [
            models.Index(fields=['recipe', 'position_no', 'layer_no', 'enabled']),
            models.Index(fields=['recipe', 'layer_no', 'roi_type', 'enabled']),
            models.Index(fields=['roi_type', 'enabled']),
        ]
        constraints = [
            # X坐标约束
            models.CheckConstraint(
                condition=models.Q(x_min__lt=models.F('x_max')),
                name='enhanced_roi_x_min_lt_x_max',
            ),
            # Y坐标约束
            models.CheckConstraint(
                condition=models.Q(y_min__lt=models.F('y_max')),
                name='enhanced_roi_y_min_lt_y_max',
            ),
            # Z坐标约束
            models.CheckConstraint(
                condition=models.Q(z_min__lt=models.F('z_max')),
                name='enhanced_roi_z_min_lt_z_max',
            ),
            # 权重范围约束
            models.CheckConstraint(
                condition=models.Q(weight__gte=0.0, weight__lte=1.0),
                name='enhanced_roi_weight_range',
            ),
        ]
    
    def __str__(self):
        return f"{self.recipe.recipe_name} - {self.roi_name} ({self.get_roi_type_display()})"
    
    def clean(self):
        """验证ROI配置"""
        super().clean()
        errors = {}
        
        # 验证坐标范围
        if self.x_min is not None and self.x_max is not None:
            if self.x_min >= self.x_max:
                errors['x_min'] = 'X最小值必须小于X最大值'
        
        if self.y_min is not None and self.y_max is not None:
            if self.y_min >= self.y_max:
                errors['y_min'] = 'Y最小值必须小于Y最大值'
        
        if self.z_min is not None and self.z_max is not None:
            if self.z_min >= self.z_max:
                errors['z_min'] = 'Z最小值必须小于Z最大值'
        
        # 验证权重
        if self.weight is not None:
            if not (0.0 <= float(self.weight) <= 1.0):
                errors['weight'] = '权重必须在0.0到1.0之间'
        
        # 验证层号与配方一致性
        if self.recipe_id and self.layer_no:
            if self.layer_no > self.recipe.layer_count:
                errors['layer_no'] = f'层号不能大于配方的总层数（{self.recipe.layer_count}）'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_dimensions(self):
        """获取ROI的尺寸"""
        return {
            'width': float(self.x_max - self.x_min),
            'depth': float(self.y_max - self.y_min),
            'height': float(self.z_max - self.z_min),
        }
    
    def get_center(self):
        """获取ROI的中心点"""
        return {
            'x': float((self.x_min + self.x_max) / 2),
            'y': float((self.y_min + self.y_max) / 2),
            'z': float((self.z_min + self.z_max) / 2),
        }
    
    def get_volume(self):
        """获取ROI的体积（mm³）"""
        dims = self.get_dimensions()
        return dims['width'] * dims['depth'] * dims['height']
    
    def contains_point(self, x, y, z):
        """判断点是否在ROI内"""
        return (
            float(self.x_min) <= x <= float(self.x_max) and
            float(self.y_min) <= y <= float(self.y_max) and
            float(self.z_min) <= z <= float(self.z_max)
        )
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'roi_name': self.roi_name,
            'roi_type': self.roi_type,
            'roi_type_display': self.get_roi_type_display(),
            'position_no': self.position_no,
            'layer_no': self.layer_no,
            'coordinate_system': self.coordinate_system,
            'x_min': float(self.x_min),
            'x_max': float(self.x_max),
            'y_min': float(self.y_min),
            'y_max': float(self.y_max),
            'z_min': float(self.z_min),
            'z_max': float(self.z_max),
            'priority': self.priority,
            'weight': float(self.weight),
            'algorithm_params': self.algorithm_params,
            'enabled': self.enabled,
            'description': self.description,
            'dimensions': self.get_dimensions(),
            'center': self.get_center(),
            'volume': self.get_volume(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class ROI3DTemplate(TimeStampedModel):
    """
    3D ROI模板
    
    预定义的ROI配置模板，方便快速创建标准ROI配置
    """
    
    template_name = models.CharField(
        '模板名称',
        max_length=128,
        unique=True,
        help_text='例如：标准3层料架模板、5层高料架模板'
    )
    rack_type = models.CharField(
        '料架类型',
        max_length=64,
        db_index=True,
        help_text='适用的料架类型'
    )
    layer_count = models.PositiveIntegerField(
        '层数',
        default=3,
        help_text='模板的层数'
    )
    
    # 模板配置（JSON格式存储多层ROI配置）
    roi_configs = models.JSONField(
        'ROI配置',
        default=list,
        help_text='包含所有层的ROI配置列表'
    )
    
    # 默认算法参数
    default_algorithm_params = models.JSONField(
        '默认算法参数',
        default=dict,
        blank=True,
        help_text='模板的默认算法参数'
    )
    
    is_active = models.BooleanField(
        '激活',
        default=True,
        help_text='是否激活此模板'
    )
    description = models.TextField(
        '描述',
        blank=True,
        help_text='模板的详细说明'
    )
    
    class Meta:
        db_table = 'vision_roi_3d_template'
        verbose_name = '3D ROI模板'
        verbose_name_plural = verbose_name
        ordering = ['rack_type', 'layer_count', '-created_at']
    
    def __str__(self):
        return f"{self.template_name} ({self.rack_type}, {self.layer_count}层)"
    
    def apply_to_recipe(self, recipe):
        """
        将模板应用到指定的配方
        
        Args:
            recipe: RackLocationRecipe实例
            
        Returns:
            创建的ROI列表
        """
        created_rois = []
        
        for roi_config in self.roi_configs:
            roi = RackLocationROI3DEnhanced.objects.create(
                recipe=recipe,
                roi_name=roi_config.get('roi_name', ''),
                roi_type=roi_config.get('roi_type', ROI3DType.MAIN),
                position_no=recipe.position_no,
                layer_no=roi_config.get('layer_no', 1),
                coordinate_system=roi_config.get('coordinate_system', ROI3DCoordinateSystem.ROBOT),
                x_min=roi_config.get('x_min', 0),
                x_max=roi_config.get('x_max', 100),
                y_min=roi_config.get('y_min', 0),
                y_max=roi_config.get('y_max', 100),
                z_min=roi_config.get('z_min', 0),
                z_max=roi_config.get('z_max', 100),
                priority=roi_config.get('priority', 100),
                weight=roi_config.get('weight', 1.0),
                algorithm_params=roi_config.get('algorithm_params', self.default_algorithm_params),
                enabled=roi_config.get('enabled', True),
                description=roi_config.get('description', ''),
            )
            created_rois.append(roi)
        
        return created_rois
