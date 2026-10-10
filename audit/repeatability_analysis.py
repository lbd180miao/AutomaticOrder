"""Read-only replay of recipe 8 captures against one fixed standard."""
import json
from pathlib import Path
import numpy as np
from django.conf import settings
from apps.vision.models import RackLocationResult
from apps.vision.rack_location import RackLocationService
from apps.vision import rack_spatial as spatial

service = RackLocationService()
records = {r.pk: r for r in RackLocationResult.objects.filter(pk__in=range(361, 366))}
ref = records[364]
rois = ref.result_data['local_template_rois']
reference_cloud = service._load_workbench_pointcloud(ref.raw_data_path)
context = records[365].result_data['transform_context']
transform = np.array(records[365].result_data['robot_groups']['B']['T_base_camera'])

def fit(cloud):
    parts = service._crop_local_template_clouds(cloud, rois)
    axes = {name: spatial.fit_axis(part) for name, part in zip(spatial.NAMES, parts)}
    return axes

axes_ref = fit(reference_cloud)
groups_ref = {k: spatial.pair_frame(axes_ref[n], axes_ref['plane2'])
              for k, n in [('A','plane1'), ('B','plane3')]}
report = {'fixed_standard':364, 'records':[]}
for pk, record in records.items():
    cloud = service._load_workbench_pointcloud(record.raw_data_path)
    axes = fit(cloud)
    item = {'id':pk, 'rois_same': record.result_data['local_template_rois'] == rois,
            'context_same': record.result_data['transform_context'] == context,
            'regions':{}, 'groups':{}}
    for name, roi in rois.items():
        x,y,w,h = [int(roi[k]) for k in ('x','y','w','h')]
        a,b = reference_cloud[y:y+h,x:x+w], cloud[y:y+h,x:x+w]
        valid_a = np.isfinite(a).all(2) & (a[:,:,2]>0)
        valid_b = np.isfinite(b).all(2) & (b[:,:,2]>0)
        difference = b[valid_a & valid_b] - a[valid_a & valid_b]
        item['regions'][name] = {'axis':axes[name],
            'valid_count':int(valid_b.sum()), 'common_count':len(difference),
            'median_xyz_change':np.median(difference,axis=0).tolist(),
            'p95_abs_depth_change':float(np.percentile(abs(difference[:,2]),95)),
            'direction_change_deg':float(np.degrees(np.arccos(np.clip(abs(np.dot(axes[name]['direction'],axes_ref[name]['direction'])),0,1))))}
    for key,name in [('A','plane1'),('B','plane3')]:
        reference = groups_ref[key]
        current = spatial.pair_frame(axes[name],axes['plane2'],reference)
        delta = np.array(current['frame']) @ np.linalg.inv(reference['frame'])
        base = service._robot_compensation_payload({'matrix':delta.tolist()},context)
        shift = transform[:3,:3] @ (np.array(current['origin'])-reference['origin'])
        lever = np.array([base['pose6d'][k] for k in ('x','y','z')])-shift
        item['groups'][key] = {'matrix_pose':base['pose6d'], 'feature_displacement_base_mm':shift.tolist(),
                              'rotation_lever_term_mm':lever.tolist(), 'origin_camera':current['origin'],
                              'gap_mm':current['gap_mm']}
    report['records'].append(item)
# Same input must reproduce the exact fitted result without RNG drift.
report['same_cloud_deterministic'] = fit(reference_cloud) == axes_ref
out=Path(settings.BASE_DIR)/'audit/repeatability_364.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
for row in report['records']:
    print(row['id'], 'same ROI/context',row['rois_same'],row['context_same'])
    for key,g in row['groups'].items():
        print(key,'matrix translation',np.round([g['matrix_pose'][k] for k in ('x','y','z')],3),
              'feature movement',np.round(g['feature_displacement_base_mm'],3),
              'rotation term',np.round(g['rotation_lever_term_mm'],3))
    print('regions',[(n,r['valid_count'],round(r['direction_change_deg'],4),round(r['p95_abs_depth_change'],3)) for n,r in row['regions'].items()])
print('deterministic',report['same_cloud_deterministic'])
