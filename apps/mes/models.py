from django.db import models

from apps.core.constants import MesAction
from apps.core.models import TimeStampedModel


class MesRecord(TimeStampedModel):
    action = models.CharField(max_length=64, choices=MesAction.choices)
    product = models.ForeignKey('production.Product', null=True, blank=True, on_delete=models.SET_NULL)
    rack = models.ForeignKey('production.Rack', null=True, blank=True, on_delete=models.SET_NULL)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f'{self.action}:{self.success}'
