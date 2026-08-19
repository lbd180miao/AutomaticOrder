from django.db import models

from apps.core.constants import AlarmLevel, AlarmSource, AlarmStatus
from apps.core.models import TimeStampedModel


class Alarm(TimeStampedModel):
    alarm_code = models.CharField(max_length=64, unique=True)
    level = models.CharField(max_length=32, choices=AlarmLevel.choices, default=AlarmLevel.ERROR)
    source = models.CharField(max_length=64, choices=AlarmSource.choices)
    message = models.TextField()
    product = models.ForeignKey('production.Product', null=True, blank=True, on_delete=models.SET_NULL)
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    workflow = models.ForeignKey('workflow.WorkflowInstance', null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=AlarmStatus.choices, default=AlarmStatus.OPEN)
    locked_workstation = models.BooleanField(default=False)
    error_code = models.CharField(max_length=64, blank=True, db_index=True)
    scene = models.CharField(max_length=64, blank=True)
    phase = models.CharField(max_length=64, blank=True)
    context = models.JSONField(default=dict, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)
    last_occurred_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    operator_note = models.TextField(blank=True)

    def __str__(self):
        return self.alarm_code


class AlarmAction(TimeStampedModel):
    class Action(models.TextChoices):
        ACKNOWLEDGE = 'ACKNOWLEDGE', '确认报警'
        CLOSE = 'CLOSE', '关闭报警'

    alarm = models.ForeignKey(Alarm, on_delete=models.CASCADE, related_name='actions')
    action = models.CharField(max_length=32, choices=Action.choices)
    operator = models.CharField(max_length=128, blank=True)
    note = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
