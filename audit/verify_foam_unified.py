import os,sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings')
import django;django.setup()
import cv2
from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.standard_mask_manager import StandardMaskManager
from apps.vision.algorithms.foam_inspector import _inspect_layer_sides,_resolve_side_roi_config
r=VisionRecipe.objects.get(pk=11);cfg=build_foam_inspection_config(r)
p=Path('media')/r.standard_template_config['source_image_path'];image=cv2.imread(str(p))
t=time.perf_counter();ex=StandardMaskManager()._extract_layer_set(image,r,cfg)
cfg.update(standard_mask_space='layer-v3',standard_masks={k:v['mask'] for k,v in ex.items()})
outputs={}
for name,img in [('self',image),('shifted',cv2.warpAffine(image, __import__('numpy').float32([[1,0,60],[0,1,0]]),(image.shape[1],image.shape[0])))]:
 start=time.perf_counter();s=_inspect_layer_sides(img,_resolve_side_roi_config(cfg,r.pos),cfg)
 outputs[name]={'ms':round((time.perf_counter()-start)*1000,1),'sides':{k:{x:v[x] for x in ['coverage_ratio','offset_x_px','offset_y_px','is_aligned','is_present']} for k,v in s.items()}}
print(json.dumps(outputs),flush=True)
Path('audit/foam_unified_self_check.json').write_text(json.dumps(outputs,indent=2))
