"""Read-only comparison on a saved production image (no recipe writes)."""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
import cv2
import numpy as np
from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.foam_inspector import _inspect_layer_sides, _resolve_side_roi_config

recipe = VisionRecipe.objects.get(pk=11)
cfg = build_foam_inspection_config(recipe)
image = cv2.imread('2d_SDK/pic/562_original.png')
outputs = {}
panels = []
for mode in ('fixed-threshold', 'shadow-graphcut-v1'):
    sides = _inspect_layer_sides(image, _resolve_side_roi_config(cfg, recipe.pos),
                                 dict(cfg, foam_segmentation=mode))
    preview = image.copy()
    outputs[mode] = {}
    for side, result in sides.items():
        x, y, xx, yy = result['roi']
        region = preview[y:yy, x:xx]
        selected = result['mask'] > 0
        region[selected] = (region[selected] * .55 + np.array([0, 0, 255]) * .45).astype('uint8')
        outputs[mode][side] = {k: result[k] for k in ('detected_pixels', 'coverage_ratio', 'offset_x_px', 'offset_y_px')}
    panel = cv2.resize(preview, (960, 640))
    cv2.putText(panel, mode, (15, 35), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 255, 255), 2)
    panels.append(panel)
cv2.imwrite('audit/foam_shadow_comparison.jpg', np.concatenate(panels, axis=1))
Path('audit/foam_shadow_recovery.json').write_text(json.dumps(outputs, indent=2))
print(json.dumps(outputs, indent=2))
