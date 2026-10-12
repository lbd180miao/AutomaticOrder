"""Read-only replay; run: python manage.py shell -c \"exec(open('audit/replay_rack_stability.py',encoding='utf-8-sig').read())\"."""
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from apps.vision.models import RackLocationResult
from apps.vision.rack_location import RackLocationService
from apps.vision import rack_spatial as spatial

root=Path(__file__).resolve().parent if '__file__' in globals() else Path('audit')
# manage.py shell sets __file__ differently; these artifacts are repository-relative.
root=Path('audit')
before=json.loads((root/'rack_stability_before.json').read_text(encoding='utf-8'))
service=RackLocationService(); rows=[]; seen=set()
for old in before:
    record=RackLocationResult.objects.get(pk=old['id'])
    cloud=service._load_workbench_pointcloud(record.raw_data_path)
    digest=hashlib.sha256(cloud.tobytes()).hexdigest()
    if digest != old['sha256']:
        raise ValueError(f"Record {record.pk}: cloud changed since baseline")
    duplicate=digest in seen; seen.add(digest)
    parts=service._crop_local_template_clouds(cloud,old['rois'])
    start=perf_counter()
    planes={n:spatial.fit_region(p,n,'replay') for n,p in zip(spatial.NAMES,parts)}
    groups={key:spatial.fit_pair(planes[name],planes['plane2'],None,key,'replay')
            for key,name in [('A','plane1'),('B','plane3')]}
    rows.append({'id':record.pk,'sha256':digest,'duplicate_cloud':duplicate,
                 'median_depth_mm':old['median_z'],'elapsed_ms':(perf_counter()-start)*1000,
                 'before_groups':old['groups'],'after_groups':groups,'planes':planes})

series=[]
for ids in [[361,362,363,364,365],[388,389,390,391,392]]:
    selected=[r for r in rows if r['id'] in ids and not r['duplicate_cloud']]
    result={'ids':ids,'distinct_captures':len(selected),'groups':{}}
    for group in ('A','B'):
        comparison={}
        for version in ('before','after'):
            points=np.array([r[f'{version}_groups'][group]['origin'] for r in selected])
            comparison[version]={'xyz_peak_to_peak_mm':np.ptp(points,axis=0).tolist(),
               'max_pair_distance_mm':float(np.linalg.norm(points[:,None,:]-points[None,:,:],axis=2).max()),
               'position_std_norm_mm':float(np.linalg.norm(points.std(axis=0,ddof=1)))}
        result['groups'][group]=comparison
    series.append(result)
report={'method':'Same raw cloud and per-record ROI, independent frame fitting, no temporal smoothing; observed spread, not ground-truth accuracy.',
        'fit_version':'robust_irls_plane_v2','threshold_mm':5,
        'limitations':['No labelled stationary 2m repeat-capture sequence was available.',
                      'Plane intersections leave along-line position unconstrained; the origin is an ROI-centroid projection.',
                      'Duplicate point clouds are excluded from repeated-capture counts.',
                      'Cross-distance robot conversion requires correct saved camera poses for both frames.'],
        'series':series,'records':rows}
(root/'rack_stability_after.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'series':series,'distinct_clouds':len(seen),'replayed_records':len(rows),
                  'median_fit_ms':float(np.median([r['elapsed_ms'] for r in rows]))},ensure_ascii=False,indent=2))
