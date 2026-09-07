from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

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
    class LoadingDirection(models.TextChoices):
        BOTTOM_UP_LEFT_RIGHT = 'BOTTOM_UP_LEFT_RIGHT', '从下到上、从左到右'
        BOTTOM_UP_RIGHT_LEFT = 'BOTTOM_UP_RIGHT_LEFT', '从下到上、从右到左'
        TOP_DOWN_LEFT_RIGHT = 'TOP_DOWN_LEFT_RIGHT', '从上到下、从左到右'
        TOP_DOWN_RIGHT_LEFT = 'TOP_DOWN_RIGHT_LEFT', '从上到下、从右到左'

    class FullCondition(models.TextChoices):
        QUANTITY_REACHED = 'QUANTITY_REACHED', '达到总装箱数量'
        PLC_OR_QUANTITY = 'PLC_OR_QUANTITY', 'PLC满框信号或达到数量'

    recipe_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    product_code = models.CharField(max_length=128, blank=True, db_index=True)
    rack_type = models.CharField(max_length=64)
    station_position_count = models.PositiveIntegerField(default=2)
    layer_count = models.PositiveIntegerField(default=0)
    quantity_per_layer = models.PositiveIntegerField(default=0)
    total_quantity = models.PositiveIntegerField(default=0)
    layer_height = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    layer_spacing = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_x = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_y = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    tolerance_z = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    loading_direction = models.CharField(
        max_length=32,
        choices=LoadingDirection.choices,
        default=LoadingDirection.BOTTOM_UP_LEFT_RIGHT,
    )
    full_condition = models.CharField(
        max_length=32,
        choices=FullCondition.choices,
        default=FullCondition.QUANTITY_REACHED,
    )
    version = models.PositiveIntegerField(default=1)
    mes_updated_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.recipe_code


class RackRecipeVisionMapping(TimeStampedModel):
    """Connect a MES rack recipe position/layer to an existing 3D recipe.

    This is deliberately additive: existing RackRecipe and RackLocationRecipe
    rows are never rewritten when mappings are introduced.
    """

    rack_recipe = models.ForeignKey(
        RackRecipe,
        on_delete=models.CASCADE,
        related_name='vision_mappings',
    )
    station_position_no = models.PositiveIntegerField(default=1)
    layer_no = models.PositiveIntegerField(default=1)
    rack_location_recipe = models.ForeignKey(
        'vision.RackLocationRecipe',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='rack_recipe_mappings',
    )
    robot_target_code = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['rack_recipe_id', 'station_position_no', 'layer_no']
        constraints = [
            models.UniqueConstraint(
                fields=['rack_recipe', 'station_position_no', 'layer_no'],
                name='unique_rack_recipe_position_layer_mapping',
            ),
        ]

    def clean(self):
        errors = {}
        if self.rack_recipe_id:
            if not 1 <= self.station_position_no <= self.rack_recipe.station_position_count:
                errors['station_position_no'] = '工位位置必须在料架配方的位置数量范围内'
            if not 1 <= self.layer_no <= self.rack_recipe.layer_count:
                errors['layer_no'] = '层号必须在料架配方的层数范围内'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.rack_recipe.recipe_code}:P{self.station_position_no}-L{self.layer_no}'


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
    bound_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='绑定时间')
    current_state = models.CharField(max_length=64, choices=WorkflowState.choices, default=WorkflowState.CREATED)
    mark_status = models.CharField(max_length=32, choices=MarkStatus.choices, default=MarkStatus.PENDING)
    mes_upload_status = models.CharField(max_length=32, choices=MesUploadStatus.choices, default=MesUploadStatus.PENDING)

    # 残次品 / 缺陷品追溯与替换字段
    is_defective = models.BooleanField(default=False, verbose_name='是否残次品')
    defect_reason = models.CharField(max_length=128, blank=True, verbose_name='残次原因')
    defect_at = models.DateTimeField(null=True, blank=True, verbose_name='标记残次时间')
    replaced_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='replaced_from', verbose_name='替换的新合格品'
    )

    def save(self, *args, **kwargs):
        """Keep the binding timestamp tied only to rack relationship changes."""
        update_fields = kwargs.get('update_fields')
        rack_is_being_saved = self._state.adding or update_fields is None or 'rack' in update_fields
        if rack_is_being_saved:
            previous_rack_id = None
            if not self._state.adding:
                previous_rack_id = type(self).objects.filter(pk=self.pk).values_list('rack_id', flat=True).first()

            if self.rack_id is None:
                next_bound_at = None
            elif self._state.adding:
                next_bound_at = self.bound_at or timezone.now()
            elif previous_rack_id != self.rack_id:
                next_bound_at = timezone.now()
            else:
                next_bound_at = self.bound_at

            if next_bound_at != self.bound_at:
                self.bound_at = next_bound_at
                if update_fields is not None:
                    kwargs['update_fields'] = set(update_fields) | {'bound_at'}

        return super().save(*args, **kwargs)

    def __str__(self):
        return self.product_code
