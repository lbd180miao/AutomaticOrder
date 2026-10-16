import requests,sqlite3,json,time
from pathlib import Path
c=sqlite3.connect('file:db.sqlite3?mode=ro',uri=True)
t=json.loads(c.execute('select standard_template_config from vision_visionrecipe where id=11').fetchone()[0]);p=Path('media')/t['source_image_path']
s=requests.Session();s.trust_env=False
base='http://127.0.0.1:8082';r=s.get(base+'/vision/foam-inspector/',timeout=15);r.raise_for_status()
csrf=s.cookies.get('csrftoken');start=time.perf_counter()
with p.open('rb') as f:
 r=s.post(base+'/vision/api/foam/upload-inspect/',headers={'X-CSRFToken':csrf,'Referer':base+'/vision/foam-inspector/'},data={'recipe_id':'11','position_index':'0','use_recipe':'true'},files={'image':('standard-self-check.png',f,'image/png')},timeout=30)
r.raise_for_status();d=r.json();assert d.get('success'),d
v=d['result'];summary={k:v.get(k) for k in ['id','is_passed','coverage_ratio','offset_x_px','offset_y_px','defect_type']};summary['http_ms']=round((time.perf_counter()-start)*1000,1)
print(json.dumps(summary));Path('audit/foam_unified_live_self_check.json').write_text(json.dumps(summary,indent=2));assert v['is_passed'] and v['coverage_ratio']==1 and v['offset_x_px']==0 and v['offset_y_px']==0
