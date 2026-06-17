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


class RackLocationResult(TimeStampedModel):
    vision_task = models.ForeignKey(VisionTask, on_delete=models.CASCADE, related_name='rack_results')
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    side = models.CharField(max_length=16, choices=RackSide.choices)
    offset_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    offset_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    offset_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    measured_layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    measured_layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    recipe_layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    recipe_layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    is_recipe_matched = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
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
