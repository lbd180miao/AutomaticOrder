"""Diagnostic records only; never delete production/MES or recipe data."""
import logging
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import PLCListenerLog, PLCLogWindow

CATEGORIES = {'foam_trigger': '2d', 'position_trigger': '3d',
              'rack_trigger': 'rack', 'mark_trigger': 'mes', 'boxing_trigger': 'mes'}


def cleanup():
    now = timezone.now()
    with transaction.atomic():
        window, _ = PLCLogWindow.objects.get_or_create(pk=1, defaults={'started_at': now})
        if window.started_at + timedelta(days=2) <= now:
            # Conditional update prevents two readers clearing a newly started window.
            if PLCLogWindow.objects.filter(pk=1, started_at=window.started_at).update(started_at=now):
                PLCListenerLog.objects.all().delete()


def record(category, message):
    try:
        cleanup()
        PLCListenerLog.objects.create(category=category, message=str(message)[:8000])
    except Exception:
        logging.getLogger(__name__).exception('保存 PLC 监听记录失败')
