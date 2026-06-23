from django.db import models

from apps.core.constants import RackSide, ResultStatus, VisionImageType, VisionTaskType
from apps.core.models import TimeStampedModel


class VisionTask(TimeStampedModel):
    task_type = models.CharField(max_length=64, choices=VisionTaskType.choices)
    product = models.ForeignKey('production.Product', null=True, blank=True, on_delete=models.SET_NULL)
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=ResultStatus.choices, default=ResultStatus.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f'{self.task_type}:{self.status}'


class RackLocationRecipe(TimeStampedModel):
    """3D 深度相机料架定位配方。

    该模型只服务 3D 料架定位，不与 2D 泡棉检测 VisionRecipe 混用。
    现场按“配方位置 + 料架层号”循环拍照，每次照片只计算当前点位补偿。
    """

    recipe_name = models.CharField(max_length=128, unique=True)
    rack_type = models.CharField(max_length=64, blank=True)
    rack_side = models.CharField(
        max_length=16,
        choices=RackSide.choices,
        default=RackSide.BOTH,
        help_text='保留兼容字段；现场不区分左右时使用 BOTH。',
    )
    position_no = models.PositiveIntegerField(default=1, db_index=True)
    layer_count = models.PositiveIntegerField(default=3)
    layer_no = models.PositiveIntegerField(default=1, db_index=True)
    camera_device = models.ForeignKey(
        'devices.Device',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rack_location_recipes',
    )
    camera_config = models.ForeignKey(
        'dm_camera.DMCameraConfig',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rack_location_recipes',
    )
    capture_pose_name = models.CharField(max_length=128, blank=True)
    standard_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    standard_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    standard_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    standard_rz = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    roi_config = models.JSONField(default=dict, blank=True)
    reference_feature_config = models.JSONField(default=dict, blank=True)
    hand_eye_config = models.JSONField(default=dict, blank=True)
    max_offset_x = models.DecimalField(max_digits=10, decimal_places=3, default=10)
    max_offset_y = models.DecimalField(max_digits=10, decimal_places=3, default=10)
    max_offset_z = models.DecimalField(max_digits=10, decimal_places=3, default=10)
    max_offset_rz = models.DecimalField(max_digits=10, decimal_places=3, default=5)
    confidence_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.7000)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['position_no', 'layer_no', '-updated_at']
        indexes = [
            models.Index(fields=['position_no', 'layer_no', 'enabled']),
        ]

    def __str__(self):
        return f'{self.recipe_name}(POS {self.position_no}, L{self.layer_no})'

    def applies_to(self, *, position_no, layer_no):
        return (
            self.enabled
            and int(self.position_no) == int(position_no)
            and int(self.layer_no) == int(layer_no)
        )


class RackLocationResult(TimeStampedModel):
    vision_task = models.ForeignKey(VisionTask, on_delete=models.CASCADE, related_name='rack_results')
    recipe = models.ForeignKey(
        RackLocationRecipe,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='results',
    )
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    side = models.CharField(max_length=16, choices=RackSide.choices)
    position_no = models.PositiveIntegerField(default=1, db_index=True)
    layer_no = models.PositiveIntegerField(default=1, db_index=True)
    offset_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    offset_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    offset_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    offset_rz = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    actual_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    actual_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    actual_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    measured_layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    measured_layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    recipe_layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    recipe_layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    is_recipe_matched = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    raw_data_path = models.CharField(max_length=512, blank=True)
    result_image_path = models.CharField(max_length=512, blank=True)
    plc_write_status = models.CharField(max_length=32, default='SKIPPED')
    plc_error_message = models.TextField(blank=True)
    result_data = models.JSONField(default=dict, blank=True)


class FoamInspectionResult(TimeStampedModel):
    vision_task = models.ForeignKey(VisionTask, on_delete=models.CASCADE, related_name='foam_results')
    product = models.ForeignKey('production.Product', null=True, blank=True, on_delete=models.SET_NULL)
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    position_index = models.PositiveIntegerField(default=0)
    is_present = models.BooleanField(default=False)
    is_aligned = models.BooleanField(default=False)
    has_lifted_edge = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    is_passed = models.BooleanField(default=False)
    
    # 新增详细检测数据字段
    offset_x_px = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='X轴偏移（像素）')
    offset_y_px = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Y轴偏移（像素）')
    coverage_ratio = models.DecimalField(max_digits=5, decimal_places=4, default=0, help_text='泡棉覆盖率')
    defect_type = models.CharField(max_length=32, default='NONE', help_text='缺陷类型')
    
    result_data = models.JSONField(default=dict, blank=True)


class VisionImage(TimeStampedModel):
    vision_task = models.ForeignKey(VisionTask, on_delete=models.CASCADE, related_name='images')
    image_type = models.CharField(max_length=32, choices=VisionImageType.choices)
    file = models.FileField(upload_to='vision/%Y/%m/%d/')
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    captured_at = models.DateTimeField(null=True, blank=True)


class CalibrationProfile(TimeStampedModel):
    name = models.CharField(max_length=128)
    device_code = models.CharField(max_length=64)
    version = models.CharField(max_length=32)
    transform_data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)


class VisionRecipe(TimeStampedModel):
    RECIPE_TYPE_CHOICES = (
        ('FOAM_2D', '泡棉检测配方'),
        ('RACK_3D', '料架定位配方'),
    )

    recipe_type = models.CharField(max_length=32, choices=RECIPE_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    product_code = models.CharField(max_length=100, blank=True, null=True)
    rack_type = models.CharField(max_length=100, blank=True, null=True)
    camera_side = models.CharField(max_length=20, blank=True, null=True, default='both')
    pos = models.IntegerField(default=0)
    image_width = models.IntegerField(default=1280)
    image_height = models.IntegerField(default=720)
    roi_config = models.JSONField(default=dict, blank=True)
    threshold_config = models.JSONField(default=dict, blank=True)
    algorithm_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    remark = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['recipe_type', 'pos', '-updated_at']

    def __str__(self):
        return f'{self.name}({self.recipe_type}, POS {self.pos})'
