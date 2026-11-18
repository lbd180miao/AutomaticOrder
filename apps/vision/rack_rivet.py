"""Three rivets, fixed P3 reference, two independent crossbar displacements."""
import copy
import cv2
import numpy as np

from .algorithms.rivet_vendor.localize_rivets import detect_image, measure_with_fallback
from .rack_cloud_match import pointmap, sensor_id
from .rack_cloud_roi import image_roi, required_targets

VERSION = 'rivet_relative_v1'
TARGETS = ('P1_rivet', 'P2_rivet', 'P3_rivet')


def inspect_roi(cloud, image, config, metadata, target):
    data = pointmap(cloud, metadata)
    if image.shape[:2] != data.shape[:2] or config.get('imageSize') != [image.shape[1], image.shape[0]]:
        raise ValueError('原图、点云和框选尺寸不一致')
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    boxes = [r for r in config['rois'] if r.get('target') == target]
    if len(boxes) != 1:
        raise ValueError('请框选一个区域')
    x, y, right, bottom = image_roi(boxes[0], gray.shape)
    hits, _ = detect_image(gray, (x, y, right-x, bottom-y), config.get('min_radius', 4), config.get('max_radius', 13))
    rows = [{'pixel': [hit['u'], hit['v']], 'score': hit.get('score'),
             'radius_px': hit.get('radius_px'), 'measurement': measure_with_fallback(data, hit)} for hit in hits]
    return {'success': bool(rows), 'pixels': [row['pixel'] for row in rows], 'rivets': rows,
            'errorMessage': '' if rows else '框内未识别到铆钉'}


def measure(cloud, image, config, metadata, *, preview_target=None):
    data = pointmap(cloud, metadata)
    if image is None or image.shape[:2] != data.shape[:2]:
        raise ValueError('铆钉定位需要同帧、逐像素对齐的二维原图和有序点云')
    if config.get('algorithm') != 'rivet' or config.get('imageSize') != [data.shape[1], data.shape[0]]:
        raise ValueError('请重新框选三个铆钉并保存铆钉模板')
    rois = config.get('rois', [])
    targets = required_targets(config)
    if preview_target in targets:
        targets = (preview_target,)
        rois = [r for r in rois if r.get("target") == preview_target]
    if len(rois) != len(targets) or {r['target'] for r in rois} != set(targets):
        raise ValueError('请分别框选所选料架的横杆和固定参照铆钉')
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    points, pixels, errors, detections = [], [], [], []
    for target in targets:
        index = TARGETS.index(target) + 1
        roi = next(r for r in rois if r['target'] == target)
        x0, y0, x1, y1 = image_roi(roi, gray.shape)
        hits, counts = detect_image(gray, (x0, y0, x1-x0, y1-y0),
                                    config.get('min_radius', 4), config.get('max_radius', 13))
        hits = sorted(hits, key=lambda h: h['ranking_score'], reverse=True)
        measurement = None
        error = ''
        if not hits:
            error = '未识别到铆钉'
        elif len(hits) > 1 and hits[1]['ranking_score'] > hits[0]['ranking_score'] * .85:
            error = '存在多个相近候选，请缩小 ROI'
        else:
            measurement = measure_with_fallback(data, hits[0])
            if measurement.get('xyz_mm') is None:
                error = '三维取点未通过：' + measurement['status']
        pixel = [hits[0]['u'], hits[0]['v']] if hits else None
        if pixel and any(p and np.linalg.norm(np.asarray(pixel)-p) < 4 for p in pixels):
            error = '与其他编号识别到同一铆钉，请检查 ROI'
        pixels.append(pixel)
        if error:
            errors.append(f'{index} 号铆钉：{error}')
        points.append({'name': f'P{index}', 'success': not error,
                       'xyz': measurement.get('xyz_mm') if measurement and not error else None})
        detections.append({'name': f'P{index}', 'candidates': hits, 'counts': counts,
                           'measurement': measurement, 'error': error})
    result = {'success': not errors, 'coordinateSystem': 'camera', 'unit': 'mm',
              'algorithm_version': VERSION, 'points': points, 'pixels': pixels,
              'detections': detections, 'errorCode': 'RIVET_INVALID' if errors else '',
              'errorMessage': '；'.join(errors),
              'registration': {'quality_passed': not errors, 'failure_reasons': errors}}
    if not errors and preview_target is None:
        xyz = np.asarray([p['xyz'] for p in points], float)
        result['relative_vectors'] = (xyz[:-1] - xyz[-1]).tolist()
    return result


def build_template(cloud, config, metadata, image):
    result = measure(cloud, image, config, metadata)
    if not result['success']:
        raise ValueError(result['errorMessage'])
    return {'version': VERSION, 'algorithm': 'rivet', 'config': copy.deepcopy(config),
            'shape': list(cloud.shape), 'sensor_id': sensor_id(metadata),
            'measurement': result, 'relative_vectors': result['relative_vectors']}


def match_template(cloud, metadata, reference, image):
    if not reference or reference.get('version') != VERSION:
        raise ValueError('请先保存三铆钉标准模板；旧点云模板不能用于铆钉补偿')
    if list(cloud.shape) != reference['shape']:
        raise ValueError('当前点云尺寸与铆钉模板不一致')
    if reference.get('sensor_id') and sensor_id(metadata) != reference['sensor_id']:
        raise ValueError('当前相机与铆钉模板不一致')
    result = measure(cloud, image, reference['config'], metadata)
    if result['success']:
        result['relative_delta_camera_mm'] = (np.asarray(result['relative_vectors']) -
            np.asarray(reference['relative_vectors'])).tolist()
    return result
