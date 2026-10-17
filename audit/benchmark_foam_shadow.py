import os, sys, inspect, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
import cv2
import numpy as np
from django.conf import settings
from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms import foam_inspector as f
r = VisionRecipe.objects.get(pk=11)
image = cv2.imread(str(Path(settings.MEDIA_ROOT) / r.standard_template_config['source_image_path']))
cfg = build_foam_inspection_config(r)
rois = f._resolve_side_roi_config(cfg, r.pos)
original = f._shadow_layer_mask
source = inspect.getsource(original)
outputs = {}
for size, iterations in ((512, 3),):
    namespace = dict(original.__globals__)
    exec(source.replace('1024 /', f'{size} /').replace(')), 5, cv2.GC_INIT', f')), {iterations}, cv2.GC_INIT'), namespace)
    f._shadow_layer_mask = namespace['_shadow_layer_mask']
    started = time.perf_counter()
    sides = f._inspect_layer_sides(image, rois, cfg)
    key = f'{size}-{iterations}'
    outputs[key] = {'seconds': time.perf_counter() - started, 'sides': {
        side: {key: data[key] for key in ('detected_pixels', 'coverage_ratio', 'iou', 'offset_x_px', 'offset_y_px')}
        for side, data in sides.items()}}
    print(key, outputs[key], flush=True)
    panel = image.copy()
    for data in sides.values():
        x,y,xx,yy = data['roi']
        region = panel[y:yy,x:xx]
        selected = data['mask'] > 0
        region[selected] = (region[selected]*.55 + np.array([0,0,255])*.45).astype(np.uint8)
    cv2.imwrite(f'audit/foam_speed_{key}.jpg', cv2.resize(panel,(1200,800)))
f._shadow_layer_mask = original
Path('audit/foam_shadow_preview_benchmark.json').write_text(json.dumps(outputs, indent=2), encoding='utf-8')
