from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.constants import MesAction
from apps.core.models import TimeStampedModel


class PkgTypeMapping(TimeStampedModel):
    class RackType(models.TextChoices):
        TWO = '两层', '两层'
        THREE = '三层', '三层'
        FIVE = '五层', '五层'

    pkg_type_code = models.CharField('PkgTypeCode', max_length=128, unique=True)
    rack_type = models.CharField('标准料架类型', max_length=16)
    plc_value = models.SmallIntegerField('PLC 写入值', null=True, blank=True,
        validators=[MinValueValidator(-32768), MaxValueValidator(32767)])
    enabled = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = 'MES 包装编码映射'
        verbose_name_plural = verbose_name
        ordering = ['pkg_type_code']


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


class LocalBinding(TimeStampedModel):
    """Manually maintained MES exception records; never trigger hardware or uploads."""
    rack_code = models.CharField(max_length=64, unique=True)
    product_codes = models.JSONField(default=list, blank=True)
    bin_code = models.CharField(max_length=128, blank=True)
