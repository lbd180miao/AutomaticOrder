import os,sys,ast,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings')
import django;django.setup()
import cv2,numpy as np
from apps.vision.algorithms import foam_inspector as f
from apps.vision.models import VisionRecipe
from apps.vision.recipe_utils import build_foam_inspection_config
oldsrc=ast.parse(Path('audit/foam_inspector_before_component_optimization.py').read_text(encoding='utf-8'))
fn=next(n for n in oldsrc.body if isinstance(n,ast.FunctionDef) and n.name=='_inspect_layer_sides')
ns=dict(vars(f));exec(compile(ast.Module(body=[fn],type_ignores=[]),'<old>','exec'),ns)
recipe=VisionRecipe.objects.get(pk=11);cfg=build_foam_inspection_config(recipe)
p=max(Path('2d_SDK/pic/.camera_cache').glob('*.bmp'),key=lambda p:p.stat().st_mtime)
im=cv2.imread(str(p));side=f._resolve_side_roi_config(cfg,recipe.pos)
results={};outputs={}
for name,func in [('optimized',f._inspect_layer_sides),('baseline',ns['_inspect_layer_sides'])]:
 t=time.perf_counter();outputs[name]=func(im,side,cfg);results[name+'_ms']=round((time.perf_counter()-t)*1000,2);print(name,results[name+'_ms'],flush=True)
for side in ('left','right'):
 for key,value in outputs['baseline'][side].items():
  other=outputs['optimized'][side][key]
  if isinstance(value,np.ndarray): assert np.array_equal(value,other),(side,key)
  else: assert value==other,(side,key,value,other)
results['all_side_metrics_and_masks_identical']=True
Path('audit/foam_component_optimization_benchmark.json').write_text(json.dumps(results,indent=2))
print(results,flush=True)
