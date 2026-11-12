"""Keep today's production history and the most recent earlier production day.

Only explicitly owned history files are removed. Recipes/calibrations are never deleted.
Run after Django initialization, before the server accepts work.
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (VisionTask, VisionImage, RackLocationResult,
                     VisionRecipe, RackLocationRecipe, CalibrationProfile)

logger = logging.getLogger(__name__)
HISTORY_TYPES = ('FOAM_INSPECTION', 'RACK_LOCATING')


def cleanup_history(today=None):
    today = today or timezone.localdate()
    tasks = VisionTask.objects.filter(task_type__in=HISTORY_TYPES)
    previous = tasks.filter(created_at__date__lt=today).order_by('-created_at').first()
    if previous is None:
        return 0
    cutoff = timezone.localdate(previous.created_at)
    expired = tasks.filter(created_at__date__lt=cutoff)
    media = Path(settings.MEDIA_ROOT).resolve()
    foam_root = (Path(settings.BASE_DIR) / '2d_SDK' / 'pic').resolve()
    # Configuration may refer to a captured frame used as a standard template.
    protected_config = json.dumps([
        list(model.objects.values()) for model in
        (VisionRecipe, RackLocationRecipe, CalibrationProfile)
    ], default=str, ensure_ascii=False).replace('\\', '/')
    removed = 0
    for task in expired.iterator():
        paths = set()
        for name in task.images.values_list('file', flat=True):
            paths.add(str(name))
        for result in task.rack_results.all():
            for name in (result.raw_data_path, result.result_image_path):
                if name:
                    paths.add(name)
                    raw = Path(name)
                    if raw.suffix == '.npy':
                        paths.add(str(raw.with_suffix('.units.json')))
                        paths.add(str(raw.with_name(raw.stem + '_image2d.png')))
        try:
            for name in paths:
                path = (media / name).resolve()
                allowed = any(path.is_relative_to(media / folder) for folder in
                              ('vision/history', 'vision/captures', 'vision/rack_workbench'))
                if not allowed or not path.is_relative_to(media):
                    continue
                relative = path.relative_to(media).as_posix()
                family = relative
                if relative.endswith('_image2d.png'):
                    family = relative[:-12] + '.npy'
                elif relative.endswith('.units.json'):
                    family = relative[:-11] + '.npy'
                if relative in protected_config or family in protected_config:
                    continue
                if RackLocationResult.objects.exclude(vision_task=task).filter(Q(raw_data_path=family) | Q(raw_data_path=family.replace('/', '\\'))).exists():
                    continue
                if VisionImage.objects.exclude(vision_task=task).filter(file=name).exists():
                    continue
                if RackLocationResult.objects.exclude(vision_task=task).filter(raw_data_path=name).exists():
                    continue
                path.unlink(missing_ok=True)
            for result_id in task.foam_results.values_list('pk', flat=True):
                for suffix in ('.json', '_original.png', '_result.png'):
                    path = (foam_root / f'{result_id}{suffix}').resolve()
                    if path.name in protected_config or path.as_posix() in protected_config:
                        continue
                    if path.is_relative_to(foam_root):
                        path.unlink(missing_ok=True)
            with transaction.atomic():
                task.delete()
            removed += 1
        except OSError:
            # Retain the DB record so the next startup can retry failed file removal.
            logger.exception('Unable to remove expired vision task %s', task.pk)
    logger.info('Vision history cleanup: cutoff=%s, removed=%s', cutoff, removed)
    return removed


def run_startup_cleanup():
    if not getattr(settings, 'VISION_HISTORY_AUTO_CLEANUP', False):
        return 0
    try:
        return cleanup_history()
    except Exception:
        logger.exception('Vision history startup cleanup failed; will retry at next startup')
        return 0
