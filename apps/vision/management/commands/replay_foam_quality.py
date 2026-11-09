"""Read-only recipe replay; never creates production results or touches PLC."""
import json
import time
from pathlib import Path

import cv2
import numpy as np
from django.core.management.base import BaseCommand, CommandError

from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.foam_inspector import (
    _inspect_calibrated_sides, _resolve_side_roi_config,
)
from apps.vision.algorithms.foam_quality import quality_config


class Command(BaseCommand):
    help = 'Compare legacy and separated foam decisions on saved images without database writes.'

    def add_arguments(self, parser):
        parser.add_argument('--recipe', required=True, type=int)
        parser.add_argument('--images', nargs='+', required=True)
        parser.add_argument('--limits', required=True, help='JSON file containing validated trial integrity limits')
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        try:
            recipe = VisionRecipe.objects.get(pk=options['recipe'], recipe_type='FOAM_2D')
            cfg = build_foam_inspection_config(recipe)
            if not cfg.get('layer_search_roi') or not cfg.get('standard_template_ready'):
                raise ValueError('Replay requires a layer ROI and a compatible standard template')
            limits = json.loads(Path(options['limits']).read_text(encoding='utf-8-sig'))
            if not isinstance(limits, dict):
                raise ValueError('limits must be an object')
            allowed = {'min_area_ratio', 'max_area_ratio', 'max_missing_ratio',
                       'max_excess_ratio', 'max_local_missing_ratio'}
            if set(limits) - allowed:
                raise ValueError('limits contains unsupported keys')
            trial = quality_config(dict(limits, decision_mode='separated-v2'))
            output = Path(options['output'])
            if output.exists():
                raise ValueError('Output already exists; choose a new report path')
        except (VisionRecipe.DoesNotExist, ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc

        rows = []
        for image_path in options['images']:
            row = {'image': str(image_path)}
            try:
                image = cv2.imdecode(np.frombuffer(Path(image_path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError('Image could not be decoded')
                template = recipe.standard_template_config or {}
                expected_shape = (int(template.get('source_image_height') or recipe.image_height),
                                  int(template.get('source_image_width') or recipe.image_width))
                if image.shape[:2] != expected_shape:
                    raise ValueError('Image dimensions differ from the taught recipe')
                for label, settings in (('baseline', dict(cfg, decision_mode='legacy')),
                                        ('trial', dict(cfg, **trial))):
                    # Baseline is the original overlap rule without new integrity gates.
                    if label == 'baseline':
                        for key in allowed:
                            settings.pop(key, None)
                    started = time.perf_counter()
                    result, _, _, sides = _inspect_calibrated_sides(
                        image, _resolve_side_roi_config(settings, recipe.pos), recipe.pos, settings)
                    result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 2)
                    result['sides'] = {s: {k: v for k, v in d.items()
                                          if k not in ('mask', 'standard_mask')}
                                       for s, d in sides.items()}
                    row[label] = result
                row['verdict_changed'] = row['baseline']['is_passed'] != row['trial']['is_passed']
            except (ValueError, OSError, cv2.error) as exc:
                row['error'] = str(exc)
            rows.append(row)
        report = {
            'recipe_id': recipe.pk, 'template_version': recipe.standard_template_version,
            'segmentation': cfg['foam_segmentation'], 'material_type': cfg['material_type'],
            'trial_limits': trial, 'images': rows,
            'note': 'No ground-truth labels supplied; this report does not measure accuracy.',
        }
        try:
            with output.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Replayed {len(rows)} images; {sum("error" in r for r in rows)} errors. Report: {output}')
