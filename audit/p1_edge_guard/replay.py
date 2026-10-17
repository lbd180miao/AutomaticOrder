"""Run from repository root: .venv/Scripts/python.exe audit/p1_edge_guard/replay.py"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.vision.rack_camera_points import camera_pointmap_measurement
from apps.vision.algorithms.rack_dual_point import validate_intersection_support, LocalizationError
folder = Path(__file__).resolve().parent
frame = ROOT / '3d_SDK/pic/2026-10-15_POS1_L1_081253'
config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
result = camera_pointmap_measurement(cv2.imread(str(frame / 'image2d.png')),
    np.load(frame / 'pointcloud.npy'), config,
    json.loads((frame / 'metadata.json').read_text(encoding='utf-8')))
assert result['success'] is False and result['errorCode'] == 'EXCESSIVE_EXTRAPOLATION', result
assert not result.get('points')
before = json.loads((folder / 'before.json').read_text(encoding='utf-8'))
checks = []
for i in range(2):
    try:
        validate_intersection_support(before['pixels'][i], before['lines'][2*i:2*i+2], config['lineQuality'])
    except LocalizationError as error:
        assert error.code == 'EXCESSIVE_EXTRAPOLATION'
        checks.append({'point': f'P{i+1}', 'code': error.code, 'message': str(error)})
assert len(checks) == 2
result['original_line_support_checks'] = checks
(folder / 'after.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('PASS: original frame rejected; both original intersections exceed support limits.')

adjusted = json.loads((folder / 'adjusted_config.json').read_text(encoding='utf-8'))
outputs = []
for algorithm in ('Projection', 'CaliperFit'):
    adjusted['algorithm'] = algorithm
    output = camera_pointmap_measurement(cv2.imread(str(frame / 'image2d.png')),
        np.load(frame / 'pointcloud.npy'), adjusted,
        json.loads((frame / 'metadata.json').read_text(encoding='utf-8')))
    assert output['success'], output
    outputs.append(output)
assert np.max(np.linalg.norm(np.array(outputs[0]['pixels'])-outputs[1]['pixels'], axis=1)) < 1
(folder / 'adjusted_result.json').write_text(json.dumps(outputs[0], indent=2), encoding='utf-8')
(folder / 'adjusted_caliper_result.json').write_text(json.dumps(outputs[1], indent=2), encoding='utf-8')
print('PASS: adjusted ROIs pass both algorithms with less than 1px disagreement.')
