from django.db import models

from apps.core.constants import EventSource, Stage, WorkflowState
from apps.core.models import TimeStampedModel


class WorkflowInstance(TimeStampedModel):
    product = models.OneToOneField('production.Product', on_delete=models.CASCADE)
    current_stage = models.CharField(max_length=64, choices=Stage.choices, blank=True)
    current_state = models.CharField(max_length=64, choices=WorkflowState.choices, default=WorkflowState.CREATED)
    is_locked = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    def __str__(self):
        return f'{self.product_id}:{self.current_state}'


class WorkflowEvent(TimeStampedModel):
    workflow = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=64)
    from_state = models.CharField(max_length=64, blank=True)
    to_state = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=32, choices=EventSource.choices, default=EventSource.SYSTEM)
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=True)
    message = models.TextField(blank=True)


class StationPhase(models.TextChoices):
    WAIT_PRODUCT = 'WAIT_PRODUCT', '等待产品条码'
    WAIT_MARK_RESET = 'WAIT_MARK_RESET', '等待打标触发复位'
    WAIT_RACK = 'WAIT_RACK', '等待料框到位'
    WAIT_RACK_RESET = 'WAIT_RACK_RESET', '等待料框触发复位'
    WAIT_POSITION = 'WAIT_POSITION', '等待定位触发'
    WAIT_POSITION_RESET = 'WAIT_POSITION_RESET', '等待定位触发复位'
    WAIT_RECIPE_VERIFY = 'WAIT_RECIPE_VERIFY', '等待配方校验触发'
    WAIT_RECIPE_RESET = 'WAIT_RECIPE_RESET', '等待配方校验触发复位'
    WAIT_FOAM = 'WAIT_FOAM', '等待泡棉检测触发'
    WAIT_FOAM_RESET = 'WAIT_FOAM_RESET', '等待泡棉检测触发复位'
    WAIT_BOXING = 'WAIT_BOXING', '等待装箱完成触发'
    WAIT_BOXING_RESET = 'WAIT_BOXING_RESET', '等待装箱触发复位'
    COMPLETED = 'COMPLETED', '装箱已满'
    LOCKED = 'LOCKED', '工位锁定'


class StationCycle(TimeStampedModel):
    """One DB100-controlled rack loading cycle.

    Handshake phases are persisted so a worker restart cannot execute the same
    PLC trigger twice while the input remains high.
    """

    workflow = models.OneToOneField(
        WorkflowInstance, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='station_cycle',
    )
    phase = models.CharField(
        max_length=32, choices=StationPhase.choices,
        default=StationPhase.WAIT_PRODUCT, db_index=True,
    )
    resume_phase = models.CharField(
        max_length=32, choices=StationPhase.choices, blank=True,
        help_text='报警解除后回到的安全握手阶段',
    )
    planned_quantity = models.PositiveIntegerField(default=0)
    loaded_quantity = models.PositiveIntegerField(default=0)
    positioning_matrix = models.JSONField(default=list, blank=True)
    measured_layer_height = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
    )
    measured_layer_spacing = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
    )
    recipe_verified = models.BooleanField(null=True, blank=True)
    foam_passed = models.BooleanField(null=True, blank=True)
    mes_upload_success = models.BooleanField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)
    last_error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def product(self):
        return self.workflow.product if self.workflow_id else None

    def __str__(self):
        code = self.product.product_code if self.product else 'WAITING'
        return f'{code}:{self.phase}'
