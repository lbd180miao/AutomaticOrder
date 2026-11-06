from django.db import models

from apps.core.constants import MesAction
from apps.core.models import TimeStampedModel


class PkgTypeMapping(TimeStampedModel):
    class RackType(models.TextChoices):
        TWO = '两层', '两层'
        THREE = '三层', '三层'
        FIVE = '五层', '五层'

    pkg_type_code = models.CharField('PkgTypeCode', max_length=128, unique=True)
    rack_type = models.CharField('标准料架类型', max_length=16, choices=RackType.choices)
    enabled = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = 'MES 包装编码映射'
        verbose_name_plural = verbose_name
        ordering = ['pkg_type_code']
        constraints = [models.CheckConstraint(
            condition=models.Q(rack_type__in=['两层', '三层', '五层']),
            name='mes_pkg_standard_rack_type',
        )]

    def __str__(self):
        return f'{self.pkg_type_code} → {self.rack_type}'


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
