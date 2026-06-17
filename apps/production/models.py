from django.db import models

from apps.core.constants import MarkStatus, MesUploadStatus, WorkflowState
from apps.core.models import TimeStampedModel


class ProductionBatch(TimeStampedModel):
    batch_no = models.CharField(max_length=64, unique=True)
    product_type = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default='OPEN')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    remark = models.TextField(blank=True)

    def __str__(self):
        return self.batch_no


class RackRecipe(TimeStampedModel):
    recipe_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    rack_type = models.CharField(max_length=64)
    layer_count = models.PositiveIntegerField(default=0)
    quantity_per_layer = models.PositiveIntegerField(default=0)
    total_quantity = models.PositiveIntegerField(default=0)
    layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.recipe_code


class Rack(TimeStampedModel):
    rack_code = models.CharField(max_length=64, unique=True)
    rack_type = models.CharField(max_length=64, blank=True)
    current_recipe = models.ForeignKey(RackRecipe, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, default='EMPTY')
    position_side = models.CharField(max_length=16, blank=True)

    def __str__(self):
        return self.rack_code


class Product(TimeStampedModel):
    product_code = models.CharField(max_length=128, unique=True)
    batch = models.ForeignKey(ProductionBatch, null=True, blank=True, on_delete=models.SET_NULL)
    rack = models.ForeignKey(Rack, null=True, blank=True, on_delete=models.SET_NULL)
    current_state = models.CharField(max_length=64, choices=WorkflowState.choices, default=WorkflowState.CREATED)
    mark_status = models.CharField(max_length=32, choices=MarkStatus.choices, default=MarkStatus.PENDING)
    mes_upload_status = models.CharField(max_length=32, choices=MesUploadStatus.choices, default=MesUploadStatus.PENDING)

    def __str__(self):
        return self.product_code
