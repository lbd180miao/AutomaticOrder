import os,sys,json,cv2,numpy as np,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings')
import django;django.setup()
from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.foam_inspector import _inspect_layer_sides,_resolve_side_roi_config
r=VisionRecipe.objects.get(pk=11);cfg=build_foam_inspection_config(r);im=cv2.imread(str(Path('media')/r.standard_template_config['source_image_path']))
for threshold in (60,80):
 s=_inspect_layer_sides(im,_resolve_side_roi_config(cfg,r.pos),dict(cfg,foam_min_v=threshold));out=im.copy()
 for v in s.values():
  x,y,xx,yy=v['roi'];region=out[y:yy,x:xx];sel=v['mask']>0;region[sel]=(region[sel]*.55+np.array([0,0,255])*.45).astype(np.uint8)
 cv2.imwrite('audit/shadow_threshold_'+str(threshold)+'.jpg',cv2.resize(out,(1280,853)))
 print(threshold,{k:v['detected_pixels'] for k,v in s.items()},flush=True)
