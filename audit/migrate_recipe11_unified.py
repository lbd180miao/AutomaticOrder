import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings')
import django;django.setup()
import cv2
from django.db import transaction
from apps.vision.models import VisionRecipe
from apps.vision.views import _save_foam_standard_template
from apps.vision.recipe_utils import build_foam_inspection_config
from apps.vision.algorithms.foam_inspector import _inspect_layer_sides,_resolve_side_roi_config
with transaction.atomic():
 r=VisionRecipe.objects.select_for_update().get(pk=11)
 backup={k:getattr(r,k) for k in ['id','name','threshold_config','standard_template_config','standard_template_version']}
 backup['standard_template_built_at']=r.standard_template_built_at.isoformat() if r.standard_template_built_at else None
 path=Path('audit/recipe11_before_unified_template.json')
 if path.exists(): raise RuntimeError('Backup already exists; do not overwrite')
 path.write_text(json.dumps(backup,ensure_ascii=False,indent=2),encoding='utf-8')
 source=Path('media')/r.standard_template_config['source_image_path']
 image=cv2.imread(str(source))
 if image is None:raise RuntimeError('Missing source')
 template=_save_foam_standard_template(r,image,{'type':'unified_algorithm_migration','previous_version':backup['standard_template_version'],'source_image':str(source)})
 r.refresh_from_db();cfg=build_foam_inspection_config(r)
 sides=_inspect_layer_sides(image,_resolve_side_roi_config(cfg,r.pos),cfg)
 result={k:{key:v[key] for key in ['coverage_ratio','offset_x_px','offset_y_px','is_aligned']} for k,v in sides.items()}
 for v in result.values():assert v['coverage_ratio']==1 and v['offset_x_px']==0 and v['offset_y_px']==0 and v['is_aligned']
 for key,value in backup['threshold_config'].items():
  if key not in ['standardMaskPaths','requireStandardTemplate']:assert r.threshold_config[key]==value
 Path('audit/recipe11_unified_template_result.json').write_text(json.dumps({'version':template['version'],'sides':result},indent=2))
 print(json.dumps(result),flush=True)
