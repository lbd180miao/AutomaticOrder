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
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    operator_note = models.TextField(blank=True)

    def __str__(self):
        return self.alarm_code
