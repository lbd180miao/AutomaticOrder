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
        raise ValueError('请按料架层数重新框选铆钉并保存模板')
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
            coords = np.asarray(measurement.get('xyz_mm'), dtype=float)
            if coords.shape != (3,) or not np.isfinite(coords).all():
                error = '三维取点未通过：' + measurement['status']
        pixel = [hits[0]['u'], hits[0]['v']] if hits else None
        if pixel and any(p and np.linalg.norm(np.asarray(pixel)-p) < 4 for p in pixels):
            error = '与其他编号识别到同一铆钉，请检查 ROI'
        pixels.append(pixel)
        if error:
            errors.append(f'{index} 号铆钉：{error}')
        points.append({'name': f'P{index}', 'success': not error,
                       'xyz': measurement.get('xyz_mm') if measurement and not error else None,
                       'pixel': pixel, 'score': hits[0].get('score') if hits else None,
                       'valid_count': (measurement or {}).get('valid_count'),
                       'sample_count': (measurement or {}).get('sample_count'),
                       'status': error or (measurement or {}).get('status', 'NO_DETECTION')})
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
    from django.utils import timezone
    result = measure(cloud, image, config, metadata)
    if not result['success']:
        raise ValueError(result['errorMessage'])
    return {'version': VERSION, 'algorithm': 'rivet', 'config': copy.deepcopy(config),
            'taught_at': timezone.now().isoformat(), 'reference_point': 'P3',
            'coordinate_system': 'camera', 'unit': 'mm',
            'shape': list(cloud.shape), 'sensor_id': sensor_id(metadata),
            'measurement': result, 'relative_vectors': result['relative_vectors']}


def _recipe_summary(recipe):
    """One representation for the library, readiness checks and PLC snapshots."""
    from .rack_cloud_roi import config_status
    saved = recipe.roi_config or {}
    config = saved.get('cloud_center_config') or {}
    reference = saved.get('cloud_center_reference') or {}
    measurement = reference.get('measurement') or {}
    issues = []
    targets = required_targets(config) if config.get('algorithm') == 'rivet' else ()
    roi_ready = bool(targets) and config_status(config)['is_complete']
    if not roi_ready:
        issues.append('请在 3D 工作台完成铆钉 ROI')
    expected = [target.split('_')[0] for target in targets]
    points = measurement.get('points') or []
    vectors = np.asarray(reference.get('relative_vectors') or [], dtype=float)
    valid_points = (measurement.get('success') is True and measurement.get('coordinateSystem') == 'camera'
                    and measurement.get('unit') == 'mm' and [p.get('name') for p in points] == expected
                    and all(p.get('success') and np.asarray(p.get('xyz')).shape == (3,)
                            and np.isfinite(np.asarray(p['xyz'], float)).all() for p in points))
    template_ready = (bool(targets) and reference.get('version') == VERSION and reference.get('algorithm') == 'rivet'
                      and reference.get('config') == config and valid_points
                      and vectors.shape == (len(targets)-1, 3) and np.isfinite(vectors).all())
    if template_ready:
        xyz = np.asarray([p['xyz'] for p in points], float)
        template_ready = bool(np.allclose(vectors, xyz[:-1]-xyz[-1], atol=1e-6))
    if not template_ready:
        issues.append('铆钉模板缺失或与 ROI 不一致，请重新示教')
    if config.get('rack_layers', getattr(recipe, 'layer_count', config.get('rack_layers', 3))) != getattr(recipe, 'layer_count', config.get('rack_layers', 3)):
        issues.append('配方层数与铆钉模板层数不一致')
    return {'algorithm': 'rivet', 'version': reference.get('version'), 'roi_complete': roi_ready,
            'template_ready': bool(template_ready), 'ready': not issues, 'issues': issues,
            'rack_layers': config.get('rack_layers', getattr(recipe, 'layer_count', config.get('rack_layers', 3))),
            'rack_layout': config.get('rack_layout', 'standard'), 'reference_point': 'P3',
            'image_size': config.get('imageSize'), 'rois': config.get('rois') or [],
            'points': points, 'relative_vectors': reference.get('relative_vectors') or [],
            'taught_at': reference.get('taught_at'), 'sensor_id': reference.get('sensor_id'),
            'robot_transform_context': measurement.get('robot_transform_context')}


def match_template(cloud, metadata, reference, image):
    if not reference or reference.get('version') != VERSION:
        raise ValueError('请先保存铆钉标准模板；旧点云模板不能用于铆钉补偿')
    if list(cloud.shape) != reference['shape']:
        raise ValueError('当前点云尺寸与铆钉模板不一致')
    if reference.get('sensor_id') and sensor_id(metadata) != reference['sensor_id']:
        raise ValueError('当前相机与铆钉模板不一致')
    result = measure(cloud, image, reference['config'], metadata)
    if result['success']:
        result['relative_delta_camera_mm'] = (np.asarray(result['relative_vectors']) -
            np.asarray(reference['relative_vectors'])).tolist()
    return result


def recipe_summary(recipe):
    try:
        return _recipe_summary(recipe)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {'algorithm': 'rivet', 'roi_complete': False, 'template_ready': False,
                'ready': False, 'issues': ['铆钉配方数据格式无效，请重新框选并保存标准模板'],
                'points': [], 'rois': [], 'relative_vectors': []}


def sync_recipe_layers(recipe):
    """Changing rack metadata must not leave a template silently usable."""
    if recipe.layer_count not in (2, 3):
        raise ValueError('料架层数必须为 2 或 3')
    if not 1 <= recipe.layer_no <= recipe.layer_count:
        raise ValueError('检测层号必须在料架层数范围内')
    saved = copy.deepcopy(recipe.roi_config or {})
    config = saved.get('cloud_center_config') or {}
    if config.get('algorithm') == 'rivet' and config.get('rack_layers', 3) != recipe.layer_count:
        config['rack_layers'] = recipe.layer_count
        if recipe.layer_count == 3:
            config.pop('rack_layout', None)
        saved['cloud_center_config'] = config
        recipe.roi_config = saved
