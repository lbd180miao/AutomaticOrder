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
