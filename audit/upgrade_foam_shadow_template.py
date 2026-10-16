"""Back up recipe 11 and migrate its existing qualified sample atomically."""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
import cv2
import numpy as np
from django.conf import settings
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from apps.vision.models import VisionRecipe
from apps.vision.views import _save_foam_standard_template
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.foam_inspector import _inspect_layer_sides, _resolve_side_roi_config

with transaction.atomic():
    recipe = VisionRecipe.objects.select_for_update().get(pk=11)
    if recipe.algorithm_config.get('foam_segmentation') == 'shadow-graphcut-v1':
        raise RuntimeError('Already migrated; refusing to replace the backup')
    backup = dict(VisionRecipe.objects.filter(pk=11).values().get())
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = Path(f'audit/recipe11_before_shadow_{stamp}.json')
    backup_path.write_text(json.dumps(backup, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2), encoding='utf-8')
    source = Path(settings.MEDIA_ROOT) / recipe.standard_template_config['source_image_path']
    image = cv2.imread(str(source))
    if image is None:
        raise RuntimeError('Saved qualified sample missing')
    cfg = build_foam_inspection_config(recipe)
    rois = _resolve_side_roi_config(cfg, recipe.pos)
    before = _inspect_layer_sides(image, rois, cfg)
    recipe.algorithm_config = dict(recipe.algorithm_config, foam_segmentation='shadow-graphcut-v1')
    recipe.save(update_fields=['algorithm_config'])
    template = _save_foam_standard_template(recipe, image, {
        'type': 'shadow_segmentation_upgrade', 'previous_version': backup['standard_template_version'],
        'source_image': str(source), 'backup': str(backup_path),
    })
    recipe.refresh_from_db()
    cfg = build_foam_inspection_config(recipe)
    after = _inspect_layer_sides(image, rois, cfg)
    missing = _inspect_layer_sides(np.zeros_like(image), rois, cfg)
    shifted_image = cv2.warpAffine(image, np.float32([[1, 0, 100], [0, 1, 0]]), (image.shape[1], image.shape[0]))
    shifted = _inspect_layer_sides(shifted_image, rois, cfg)
    summary = {}
    for side in ('left', 'right'):
        assert after[side]['coverage_ratio'] == 1.0
        assert abs(after[side]['offset_x_px']) < .01 and abs(after[side]['offset_y_px']) < .01
        assert not missing[side]['is_present']
        assert not shifted[side]['is_aligned'], 'Shifted sample incorrectly accepted'
        summary[side] = {'before_pixels': before[side]['detected_pixels'],
                         'after_pixels': after[side]['detected_pixels'],
                         'coverage_ratio': after[side]['coverage_ratio'],
                         'shift_x_px': shifted[side]['offset_x_px'],
                         'missing_rejected': True, 'shift_rejected': True}
    for key, value in backup['threshold_config'].items():
        if key not in ('standardMaskPaths', 'requireStandardTemplate'):
            assert recipe.threshold_config[key] == value
    panels = []
    for title, results in [('Before', before), ('After', after)]:
        panel = image.copy()
        for data in results.values():
            x, y, xx, yy = data['roi']
            region = panel[y:yy, x:xx]
            selected = data['mask'] > 0
            region[selected] = (region[selected] * .55 + np.array([0, 0, 255]) * .45).astype(np.uint8)
        panel = cv2.resize(panel, (960, 640))
        cv2.putText(panel, title, (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        panels.append(panel)
    cv2.imwrite('audit/foam_shadow_upgrade_comparison.jpg', np.concatenate(panels, axis=1))
    report = {'backup': str(backup_path), 'version': template['version'], 'sides': summary}
    Path('audit/foam_shadow_upgrade_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
