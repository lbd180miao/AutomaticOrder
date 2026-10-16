"""Four pixel ROIs -> two beam-surface references. No camera, DB or PLC I/O.

This opt-in algorithm requires an explicit frame/calibration contract. In
particular, equal image/cloud dimensions are never treated as registration.
All thresholds belong to the caller's validated configuration, not safety
defaults. Legacy three-plane ROI dictionaries are left untouched.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone

import cv2
import numpy as np

from .robust_rack_geometry import robust_plane

VERSION = 'rack_dual_point_v2'
TARGETS = ('P1_horizontal', 'P1_vertical', 'P2_horizontal', 'P2_vertical')
logger = logging.getLogger(__name__)


class LocalizationError(ValueError):
    def __init__(self, code, stage, message):
        super().__init__(message)
        self.code, self.stage = code, stage


def require(condition, code, stage, message):
    if not condition:
        raise LocalizationError(code, stage, message)


def number(value, name, minimum=0, strictly=True):
    result = float(value)
    require(np.isfinite(result) and (result > minimum if strictly else result >= minimum),
            'INVALID_CONFIG', 'configuration', f'{name} 数值无效')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def measurement_digest(config):
    return digest({k: v for k, v in config.items()
                   if k not in ('compareAlgorithms', 'maxAlgorithmDifferencePx')})


def image_roi(raw, shape):
    x, y = float(raw['x']), float(raw['y'])
    w, h = float(raw.get('width', raw.get('w'))), float(raw.get('height', raw.get('h')))
    require(np.isfinite([x, y, w, h]).all() and w >= 3 and h >= 3,
            'INVALID_ROI', '2d', 'ROI 必须为有限数值且宽高至少 3 像素')
    x0, y0, x1, y1 = math.floor(x), math.floor(y), math.ceil(x+w), math.ceil(y+h)
    require(x0 >= 0 and y0 >= 0 and x1 <= shape[1] and y1 <= shape[0],
            'ROI_OUT_OF_BOUNDS', '2d', 'ROI 超出原图，禁止静默裁剪')
    return x0, y0, x1, y1


def canvas_to_image(raw, *, scale_x, scale_y, offset_x=0, offset_y=0,
                    crop_x=0, crop_y=0):
    """Inverse of canvas = (original - crop) * scale + offset."""
    sx, sy = number(scale_x, 'scale_x'), number(scale_y, 'scale_y')
    return {**raw, 'x': (raw['x']-offset_x)/sx+crop_x,
            'y': (raw['y']-offset_y)/sy+crop_y,
            'width': raw.get('width', raw.get('w'))/sx,
            'height': raw.get('height', raw.get('h'))/sy}


def subpixel_peak(profile, index):
    require(0 < index < len(profile)-1, 'EDGE_AT_BOUNDARY', '2d', '峰值位于搜索边界')
    left, mid, right = map(float, profile[index-1:index+2])
    denominator = left - 2*mid + right
    return float(index + (np.clip(.5*(left-right)/denominator, -.5, .5)
                          if denominator < -1e-12 else 0))


def fit_line(points, quality, total):
    p = np.asarray(points, dtype=float).reshape(-1, 2)
    minimum = max(3, int(quality['min_points']))
    threshold = number(quality['ransac_px'], 'ransac_px')
    require(len(p) >= minimum, 'INSUFFICIENT_EDGES', '2d', '有效边缘点不足')
    rng = np.random.default_rng(42)
    best, score = None, (-1, -np.inf)
    for _ in range(int(number(quality['iterations'], 'iterations'))):
        a, b = p[rng.choice(len(p), 2, replace=False)]
        d = b-a
        if np.linalg.norm(d) < 1e-9:
            continue
        normal = np.array([-d[1], d[0]])/np.linalg.norm(d)
        errors = np.abs((p-a) @ normal)
        mask = errors <= threshold
        candidate = (int(mask.sum()), -float(np.minimum(errors, threshold).sum()))
        if candidate > score:
            best, score = mask, candidate
    require(best is not None and best.sum() >= minimum, 'LINE_FIT_FAILED', '2d', '直线内点不足')
    for _ in range(3):
        center = p[best].mean(axis=0)
        _, singular, vectors = np.linalg.svd(p[best]-center, full_matrices=False)
        require(singular[0] > 1e-8, 'LINE_FIT_FAILED', '2d', '直线点退化')
        normal = vectors[-1]
        errors = np.abs((p-center) @ normal)
        best = errors <= threshold
        require(best.sum() >= minimum, 'LINE_FIT_FAILED', '2d', '精拟合内点不足')
    ratio = float(best.mean())
    residual = float(np.sqrt(np.mean(errors[best]**2)))
    require(len(p)/total >= number(quality['min_valid_ratio'], 'min_valid_ratio')
            and ratio >= number(quality['min_inlier_ratio'], 'min_inlier_ratio')
            and residual <= number(quality['max_residual_px'], 'max_residual_px'),
            'LINE_QUALITY', '2d', '直线内点比例或残差不合格')
    direction = np.array([normal[1], -normal[0]])
    angle = float(np.degrees(np.arctan2(direction[1], direction[0])) % 180)
    return {'success': True, 'line_abc': [*normal.tolist(), float(-normal @ center)],
            'edge_points': p.tolist(), 'inlier_points': p[best].tolist(),
            'total_calipers': total, 'valid_calipers': len(p), 'valid_count': len(p),
            'inlier_count': int(best.sum()), 'inlier_ratio': ratio,
            'fit_residual': residual, 'residual': residual, 'line_angle': angle,
            'angle': angle, 'confidence': ratio*float(best.sum()/total), 'error_code': ''}


def _peak(gradient, expected, half_width, polarity, threshold):
    response = gradient if polarity == 'dark_to_light' else -gradient
    indices = np.arange(1, len(response)-1)
    candidates = indices[(response[1:-1] >= response[:-2]) &
                         (response[1:-1] > response[2:]) &
                         (response[1:-1] >= threshold)]
    candidates = candidates[np.abs(candidates-expected) <= half_width]
    if not len(candidates):
        return None
    # Stable edge identity: select near the taught search position, not global max.
    index = int(candidates[np.argmin(np.abs(candidates-expected))])
    return subpixel_peak(response, index)


def sample_profile(patch, along, width, slope, prior):
    """One sampler for both layouts: average along tangent, search along normal."""
    rows = np.arange(patch.shape[0], dtype=np.float32)[:, None]
    tangent = (np.arange(width, dtype=np.float32)-(width-1)/2)[None, :]
    map_x = along-slope*(rows-prior)+tangent
    map_y = rows+slope*tangent
    samples = cv2.remap(patch, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR)
    valid = ((map_x >= 0) & (map_x <= patch.shape[1]-1) &
             (map_y >= 0) & (map_y <= patch.shape[0]-1)).all(axis=1)
    return samples.mean(axis=1), valid


def measure_profile(profile, valid, prior, roi):
    """Shared gradient, polarity, subpixel and two-edge identity kernel."""
    gradient = np.gradient(profile)
    support = valid.copy()
    support[1:] &= valid[:-1]
    support[:-1] &= valid[1:]
    # NaN prevents a truncated search boundary from becoming a false peak.
    gradient[~support] = np.nan
    half = number(roi['searchHalfWidth'], 'searchHalfWidth')
    threshold = number(roi['gradientThreshold'], 'gradientThreshold')
    if roi['edgeMode'] == 'single':
        return _peak(gradient, prior, half, roi['edgePolarity'], threshold)
    width = number(roi['expectedWidth'], 'expectedWidth')
    first = _peak(gradient, prior-width/2, half, roi['edgePolarity'], threshold)
    other = 'light_to_dark' if roi['edgePolarity'] == 'dark_to_light' else 'dark_to_light'
    second = _peak(gradient, prior+width/2, half, other, threshold)
    if first is None or second is None or second <= first or abs(second-first-width) > number(roi['widthTolerance'], 'widthTolerance'):
        return None
    return (first+second)/2


def detect_line(image, roi, algorithm, quality):
    """Track taught single edges inside their ROI without changing the recipe."""
    try:
        return _detect_line_local(image, roi, algorithm, quality)
    except LocalizationError as original:
        if (roi.get('edgeSelection') != 'taught' or roi.get('edgeMode') != 'single'
                or original.code not in ('INSUFFICIENT_EDGES', 'LINE_FIT_FAILED', 'LINE_QUALITY')):
            raise
        x0, y0, x1, y1 = image_roi(roi, image.shape)
        horizontal = roi.get('imageDirection',
            'horizontal' if roi['target'].endswith('horizontal') else 'vertical') == 'horizontal'
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        patch = gray[y0:y1, x0:x1].astype(np.float32)
        if not horizontal:
            patch = patch.T
        profile = np.median(np.gradient(cv2.GaussianBlur(patch, (3, 3), 0), axis=0), axis=1)
        response = profile if roi['edgePolarity'] == 'dark_to_light' else -profile
        peaks = [i for i in range(3, len(response)-3)
                 if response[i] >= response[i-1] and response[i] > response[i+1]
                 and response[i] >= roi['gradientThreshold']]
        candidates = []
        origin = y0 if horizontal else x0
        along = (x0+x1-1)/2 if horizontal else (y0+y1-1)/2
        for peak in peaks:
            trial = {**roi, 'expectedPosition': float(origin+peak)}
            try:
                line = _detect_line_local(image, trial, algorithm, quality)
            except LocalizationError:
                continue
            a, b, c = line['line_abc']
            position = float((-a*along-c)/b if horizontal else (-b*along-c)/a)
            if any(abs(position-p) < 2 for p, _ in candidates):
                continue
            candidates.append((position, line))
        if not candidates:
            raise LocalizationError(original.code, original.stage,
                f'{original}；已搜索整个 ROI，未找到满足原极性、阈值和直线质量的边缘') from original
        require(len(candidates) == 1, 'AMBIGUOUS_EDGE', '2d',
                f"{roi['target']}：ROI 内有 {len(candidates)} 条合格同极性边缘，无法唯一匹配示教边缘，请缩小 ROI")
        position, line = candidates[0]
        return {**line, 'reacquired': True,
                'edge_shift_px': position-float(roi['expectedPosition'])}


def _detect_line_local(image, roi, algorithm, quality):
    x0, y0, x1, y1 = image_roi(roi, image.shape)
    direction = roi.get('imageDirection', 'horizontal' if roi['target'].endswith('horizontal') else 'vertical')
    require(direction in ('horizontal', 'vertical'), 'INVALID_CONFIG', '2d', '图像边缘方向无效')
    horizontal = direction == 'horizontal'
    require(roi['edgePolarity'] in ('dark_to_light', 'light_to_dark'),
            'INVALID_CONFIG', 'configuration', '必须指定边缘极性')
    side = roi['edgeSide']
    mode = roi['edgeMode']
    require(mode in ('single', 'center') and side in
            (('upper', 'lower', 'center') if horizontal else ('left', 'right', 'center'))
            and (side == 'center') == (mode == 'center'),
            'INVALID_CONFIG', 'configuration', '单边身份或双边中心配置不一致')
    algorithm = roi.get('algorithm', algorithm)
    require(algorithm in ('Projection', 'CaliperFit'), 'INVALID_ALGORITHM', '2d', '未知二维算法')
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    patch = gray[y0:y1, x0:x1].astype(np.float32)
    if not horizontal:
        patch = patch.T
    patch = cv2.GaussianBlur(patch, (3, 3), 0)
    count = int(number(roi['caliperCount'], 'caliperCount'))
    require(3 <= count <= patch.shape[1], 'INVALID_CONFIG', 'configuration', '卡尺数量无效')
    origin = y0 if horizontal else x0
    expected = number(roi['expectedPosition'], 'expectedPosition', minimum=-1e9)-origin
    points = []
    for index in range(count):
        lo, hi = int(index*patch.shape[1]/count), int((index+1)*patch.shape[1]/count)
        along = (lo+hi-1)/2
        slope = float(roi.get('expectedSlope', 0))
        require(np.isfinite(slope), 'INVALID_CONFIG', '2d', '先验斜率无效')
        prior = expected + slope*(along-(patch.shape[1]-1)/2)
        # Only the measurement footprint differs; no second edge kernel.
        width = hi-lo if algorithm == 'Projection' else int(number(roi['caliperWidth'], 'caliperWidth'))
        require(width <= patch.shape[1], 'INVALID_CONFIG', '2d', '卡尺宽度超过 ROI')
        profile, valid = sample_profile(patch, along, width, slope, prior)
        edge = measure_profile(profile, valid, prior, roi)
        if edge is not None:
            measured_along = along-slope*(edge-prior)
            points.append([x0+measured_along, y0+edge] if horizontal else [x0+edge, y0+measured_along])
    try:
        result = fit_line(points, quality, count)
    except LocalizationError as exc:
        raise LocalizationError(exc.code, exc.stage,
            f"{roi['target']}：{exc}（有效点 {len(points)}/{count}，至少 {quality['min_points']}；"
            f"图像方向 {direction}，极性 {roi['edgePolarity']}，梯度阈值 {roi['gradientThreshold']:.2f}）") from exc
    direction_error = min(result['angle'], 180-result['angle']) if horizontal else abs(result['angle']-90)
    require(direction_error <= number(quality['max_tilt_deg'], 'max_tilt_deg'),
            'LINE_TILT', '2d', f"{roi['target']} 倾斜超限")
    return {**result, 'target': roi['target'], 'algorithm': algorithm, 'roi': [x0, y0, x1, y1]}


def intersection(first, second, bounds, min_sine):
    a, b = np.asarray(first, float), np.asarray(second, float)
    determinant = np.linalg.det(np.stack([a[:2], b[:2]]))
    sine = abs(determinant)/(np.linalg.norm(a[:2])*np.linalg.norm(b[:2]))
    require(np.isfinite(sine) and sine >= number(min_sine, 'min_intersection_sine'),
            'PARALLEL_LINES', '2d', '两直线近似平行')
    point = np.linalg.solve(np.stack([a[:2], b[:2]]), -np.array([a[2], b[2]]))
    require(bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3],
            'INTERSECTION_OUT_OF_BOUNDS', '2d', '交点超出允许范围')
    return point.tolist()


def locate_2d(image, config):
    require(config.get('imageSize') == [image.shape[1], image.shape[0]],
            'IMAGE_SIZE_MISMATCH', 'input', 'ROI 配置分辨率与原图不同，请重新示教')
    rois = config['rois']
    require(len(rois) == 4 and {r['target'] for r in rois} == set(TARGETS),
            'FOUR_ROIS_REQUIRED', 'configuration', '需要 P1/P2 各一横一竖四个 ROI')
    by_target = {r['target']: r for r in rois}
    lines = [detect_line(image, by_target[name], config['algorithm'], config['lineQuality']) for name in TARGETS]
    pixels = []
    for i, name in enumerate(('P1', 'P2')):
        bounds = config['intersectionBounds'][name]
        require(len(bounds) == 4 and np.isfinite(bounds).all() and
                0 <= bounds[0] < bounds[2] < image.shape[1] and
                0 <= bounds[1] < bounds[3] < image.shape[0],
                'INVALID_CONFIG', 'configuration', '交点范围必须在原图内')
        pixels.append(intersection(lines[2*i]['line_abc'], lines[2*i+1]['line_abc'],
                                   bounds, config['minIntersectionSine']))
    return {'lines': lines, 'pixels': pixels}


def compare_2d_debug(image, config, primary):
    """Same-sensor debug information, never an independent acceptance gate."""
    try:
        alternate = {**config, 'rois': [dict(r, algorithm='CaliperFit' if r.get('algorithm', config['algorithm']) == 'Projection'
                                           else 'Projection') for r in config['rois']]}
        other = locate_2d(image, alternate)
        differences = np.linalg.norm(np.asarray(primary['pixels'])-other['pixels'], axis=1)
        threshold = config.get('maxAlgorithmDifferencePx')
        within = None if threshold is None else bool(np.all(differences <= number(threshold, 'maxAlgorithmDifferencePx')))
        return {'debug_only': True, 'available': True, 'pixels': other['pixels'],
                'difference_px': differences.tolist(), 'threshold_px': threshold, 'within_debug_limit': within,
                'warning': '两算法使用同源灰度；一致不代表正确' if within is not False else '双算法差异超过调试阈值，请复核'}
    except (ValueError, TypeError, KeyError, OverflowError, cv2.error) as exc:
        return {'debug_only': True, 'available': False, 'warning': f'备用算法调试失败: {exc}',
                'errorCode': getattr(exc, 'code', 'INVALID_DEBUG_CONFIG')}


def rigid_matrix(raw, name):
    matrix = np.asarray(raw, float)
    require(matrix.shape == (4, 4) and np.isfinite(matrix).all() and
            np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8) and
            np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6) and
            abs(np.linalg.det(matrix[:3, :3])-1) < 1e-6,
            'INVALID_TRANSFORM', 'calibration', f'{name} 不是有效刚体矩阵')
    return matrix


def frame_contract(metadata, hand_eye, robot_pose, *, camera_only=False):
    c = metadata.get('dual_point_contract')
    require(isinstance(c, dict) and bool(c), 'MISSING_FRAME_CONTRACT', 'input',
            '缺少采集、配准与标定契约 dual_point_contract')
    for field in ('frame_id', 'sensor_id', 'sensor_config_version', 'calibration_version') + (() if camera_only else ('robot_frame',)):
        require(bool(c.get(field)), 'MISSING_FRAME_CONTRACT', 'input', f'缺少 {field}')
    stamp = datetime.fromisoformat(c['captured_at'])
    require(stamp.tzinfo is not None, 'MISSING_FRAME_CONTRACT', 'input', '采集时间必须带时区')
    require(c['image_frame_id'] == c['cloud_frame_id'] == c['frame_id'],
            'FRAME_MISMATCH', 'input', '图像与点云不属于同一采集帧')
    require(c['unit'] in ('mm', 'm') and (camera_only or c['matrix_unit'] == 'mm'),
            'UNIT_MISMATCH', 'calibration', '点云单位必须为 mm/m，矩阵平移必须为 mm')
    require(c['mapping_verified'] is True and bool(c['mapping_evidence']),
            'UNVERIFIED_MAPPING', 'input', '缺少 SDK/标定像素配准验证记录')
    if camera_only:
        require(c['cloud_frame'] == 'camera', 'COORDINATE_MISMATCH', 'input', '需要相机坐标系点云')
        signature = digest({k: c[k] for k in ('sensor_id', 'sensor_config_version',
            'calibration_version', 'cloud_frame', 'camera_model', 'mapping_mode', 'mapping_evidence')})
        return c, None, signature
    require(c['calibration_verified'] is True, 'UNVERIFIED_CALIBRATION', 'calibration', '标定尚未验证')
    mode = c['transform_mode']
    if mode == 'eye_in_hand':
        require(c['pose_frame_id'] == c['frame_id'] and c['pose_synchronized'] is True,
                'POSE_FRAME_MISMATCH', 'calibration', '机器人位姿与采集帧不同步')
        require(c['hand_eye_direction'] == 'T_flange_camera' and c['pose_direction'] == 'T_base_flange',
                'TRANSFORM_DIRECTION', 'calibration', '矩阵方向未确认')
        # Same direction/order as CoordinateTransformService.camera_to_robot_base.
        base_camera = rigid_matrix(robot_pose, 'T_base_flange') @ rigid_matrix(hand_eye, 'T_flange_camera')
    elif mode == 'fixed_camera':
        require(c['hand_eye_direction'] == 'T_base_camera', 'TRANSFORM_DIRECTION', 'calibration', '固定相机外参方向错误')
        base_camera = rigid_matrix(hand_eye, 'T_base_camera')
    elif mode == 'robot_base':
        base_camera = rigid_matrix(c['T_base_camera'], 'T_base_camera')
    else:
        raise LocalizationError('TRANSFORM_DIRECTION', 'calibration', '未知相机安装/点云坐标定义')
    expected_frame = 'robot_base' if mode == 'robot_base' else 'camera'
    require(c['cloud_frame'] == expected_frame, 'COORDINATE_MISMATCH', 'calibration', '点云坐标系与变换模式不一致')
    # Deliberately exclude per-frame pose; moving the camera must remain supported.
    signature = digest({k: c[k] for k in ('sensor_id', 'sensor_config_version', 'calibration_version',
                                         'robot_frame', 'transform_mode', 'cloud_frame', 'camera_model',
                                         'mapping_mode', 'mapping_evidence') } | {
        'extrinsic': (base_camera if mode != 'eye_in_hand' else rigid_matrix(hand_eye, 'hand_eye')).tolist()})
    return c, base_camera, signature


def mapped_cloud(cloud, shape, contract, pixel_index_map=None):
    data = np.asarray(cloud, dtype=float)
    mode = contract['mapping_mode']
    if mode == 'organized_registered':
        require(data.shape == (*shape[:2], 3), 'CLOUD_SHAPE', 'input', '已配准组织化点云尺寸不符')
        return data
    require(mode == 'pixel_index_map' and data.ndim == 2 and data.shape[1] == 3,
            'UNSUPPORTED_MAPPING', 'input', '无组织点云需要 SDK 像素到点索引表')
    indices = np.asarray(pixel_index_map)
    require(indices.shape == tuple(shape[:2]) and np.issubdtype(indices.dtype, np.integer)
            and np.all((indices >= -1) & (indices < len(data))),
            'INVALID_MAPPING', 'input', '索引表形状/索引无效；-1 表示无深度')
    result = np.full((*shape[:2], 3), np.nan)
    valid = indices >= 0
    result[valid] = data[indices[valid]]
    return result


def camera_ray(pixel, model):
    require(model['type'] in ('pinhole', 'opencv'), 'CAMERA_MODEL', '3d', '不支持的成像模型')
    k = np.asarray(model['K'], float)
    require(k.shape == (3, 3) and np.isfinite(k).all() and k[0, 0] > 0 and k[1, 1] > 0
            and np.allclose(k[2], [0, 0, 1]) and abs(k[1, 0]) < 1e-9,
            'CAMERA_MODEL', '3d', '相机内参无效')
    if model['type'] == 'opencv':
        require(abs(k[0, 1]) < 1e-9, 'CAMERA_MODEL', '3d', 'OpenCV 模型不支持非零 skew')
        d = np.asarray(model['distortion'], float)
        require(d.size in (4, 5, 8, 12, 14) and np.isfinite(d).all(), 'CAMERA_MODEL', '3d', '畸变系数无效')
        xy = cv2.undistortPoints(np.array(pixel, float).reshape(1, 1, 2), k, d).reshape(2)
        return np.array([*xy, 1.])
    require(model['rectified'] is True, 'CAMERA_MODEL', '3d', '针孔模型需确认图像已校正')
    return np.linalg.solve(k, [*pixel, 1.])


def recover_point(cloud_camera, pixel, line, roi, geometry, model):
    require(geometry['model'] == 'beam_plane_ray', 'UNSUPPORTED_GEOMETRY', '3d', '曲面/窄边不可强行拟合平面')
    x0, y0, x1, y1 = image_roi(roi, cloud_camera.shape)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    a, b, c = line['line_abc']
    require(abs(b) > 1e-6, 'BEAM_ORIENTATION', '3d', '横杆方向异常')
    distances = yy - (-a*xx-c)/b
    lo, hi = map(float, geometry['surfaceBandPx'])
    require(np.isfinite([lo, hi]).all() and lo < hi and
            ((roi['edgeSide'] == 'upper' and lo > 0) or
             (roi['edgeSide'] == 'lower' and hi < 0) or roi['edgeSide'] == 'center'),
            'SURFACE_SELECTION', '3d', '必须配置对应横杆内部的表面采样带')
    mask = (distances >= lo) & (distances <= hi)
    exclusion = number(geometry['intersectionExclusionPx'], 'intersectionExclusionPx')
    mask &= (xx-pixel[0])**2 + (yy-pixel[1])**2 >= exclusion**2
    points = cloud_camera[y0:y1, x0:x1][mask]
    zmin, zmax = map(float, geometry['depthRangeMm'])
    require(np.isfinite([zmin, zmax]).all() and 0 < zmin < zmax, 'INVALID_CONFIG', '3d', '目标深度区间无效')
    points = points[np.isfinite(points).all(axis=1) & (points[:, 2] >= zmin) & (points[:, 2] <= zmax)]
    if 'boundsMm' in geometry:
        bounds = np.asarray(geometry['boundsMm'], float)
        require(bounds.shape == (2, 3) and np.isfinite(bounds).all() and np.all(bounds[0] < bounds[1]),
                'INVALID_CONFIG', '3d', '空间范围无效')
        points = points[np.all((points >= bounds[0]) & (points <= bounds[1]), axis=1)]
    minimum = max(3, int(number(geometry['min_points'], 'min_points')))
    require(len(points) >= minimum, 'INSUFFICIENT_DEPTH', '3d', '目标横杆有效点不足')
    try:
        plane, inliers = robust_plane(points, threshold_mm=number(geometry['ransac_mm'], 'ransac_mm'),
                                      min_points=minimum, iterations=int(number(geometry['iterations'], 'iterations')))
    except ValueError as exc:
        raise LocalizationError('GEOMETRY_FIT_FAILED', '3d', str(exc)) from exc
    require(plane['inlier_ratio'] >= number(geometry['min_inlier_ratio'], 'min_inlier_ratio')
            and plane['rms_mm'] <= number(geometry['max_residual_mm'], 'max_residual_mm')
            and plane['eigenvalue_ratio'] <= number(geometry['max_eigenvalue_ratio'], 'max_eigenvalue_ratio'),
            'GEOMETRY_QUALITY', '3d', '横杆平面内点、残差或平整度不合格')
    normal = np.asarray(plane['normal'])
    ray = camera_ray(pixel, model)
    denominator = normal @ ray
    require(abs(denominator)/np.linalg.norm(ray) >= number(geometry['min_ray_cosine'], 'min_ray_cosine'),
            'RAY_PARALLEL', '3d', '成像射线与参考平面近似平行')
    point = ray*(-plane['offset']/denominator)
    require(np.isfinite(point).all() and zmin <= point[2] <= zmax,
            'DEPTH_RANGE', '3d', '恢复交点深度异常')
    require(np.min(np.linalg.norm(inliers-point, axis=1)) <= number(geometry['max_extrapolation_mm'], 'max_extrapolation_mm'),
            'EXTRAPOLATION_LIMIT', '3d', '交点距离实测横杆表面过远')
    return {'success': True, 'xyz': point.tolist(), 'x': float(point[0]), 'y': float(point[1]),
            'z': float(point[2]), 'valid_points': len(points), 'inlier_ratio': plane['inlier_ratio'],
            'geometry_residual': plane['rms_mm'], 'model_type': 'beam_plane_ray',
            'confidence': plane['inlier_ratio'], 'plane': plane, 'error_code': ''}


def locate(image, cloud, config, metadata, hand_eye=None, robot_pose=None, pixel_index_map=None, *, camera_only=False):
    """Never return compensation or success on partial P1/P2 failure."""
    result = {'success': False, 'compensation_valid': False, 'algorithm_version': VERSION}
    try:
        require(image is not None and image.ndim in (2, 3), 'IMAGE_MISSING', 'input', '缺少原始 2D 图像')
        result.update(locate_2d(image, config))
        if config.get('compareAlgorithms'):
            result['comparison'] = compare_2d_debug(image, config, result)
        contract, base_camera, signature = frame_contract(metadata, hand_eye, robot_pose, camera_only=camera_only)
        recorded_unit = metadata.get('camera', {}).get('pointcloud_unit', contract['unit'])
        require(recorded_unit == contract['unit'], 'UNIT_MISMATCH', 'input', '采集元数据与定位契约中的点云单位不一致')
        organized = mapped_cloud(cloud, image.shape, contract, pixel_index_map)
        organized = organized * (1000 if contract['unit'] == 'm' else 1)
        # Convert a SDK robot-base cloud back to camera for the ray model only.
        if contract['cloud_frame'] == 'robot_base':
            organized = (organized-base_camera[:3, 3]) @ base_camera[:3, :3]
        rois = {r['target']: r for r in config['rois']}
        points = []
        from ..vision_result_validator import VisionResultValidator
        validator = VisionResultValidator()
        for i, name in enumerate(('P1', 'P2')):
            recovered = recover_point(organized, result['pixels'][i], result['lines'][i*2],
                                      rois[name+'_horizontal'], config['geometry'][name], contract['camera_model'])
            recovered['consistency'] = validator.validate_beam(organized, result['lines'][i*2],
                rois[name+'_horizontal'], recovered, contract['camera_model'], config['geometry'][name].get('consistency'))
            point = {**recovered, 'name': name, 'pixel': result['pixels'][i]}
            if not camera_only:
                point['robot'] = (base_camera[:3, :3] @ recovered['xyz'] + base_camera[:3, 3]).tolist()
            points.append(point)
        result.update(success=True, points=points, unit='mm', coordinateSystem='camera' if camera_only else 'robot_base',
                      frame_id=contract['frame_id'], captured_at=contract['captured_at'],
                      config_digest=measurement_digest(config), calibration_digest=signature,
                      robot_frame=None if camera_only else contract['robot_frame'], errorCode='', errorMessage='', stage='complete')
    except LocalizationError as exc:
        result.update(errorCode=exc.code, errorMessage=str(exc), stage=exc.stage)
        if hasattr(exc, 'metrics'):
            result['validation_metrics'] = exc.metrics
    except (KeyError, TypeError, ValueError, OverflowError, np.linalg.LinAlgError, cv2.error) as exc:
        result.update(errorCode='INVALID_INPUT', errorMessage=f'输入/配置不完整或无效: {exc}', stage='input')
    if not result['success']:
        logger.info('双交点定位失败 [%s/%s]: %s', result['stage'], result['errorCode'], result['errorMessage'])
    return result


def teach_reference(result):
    require(result.get('success') is True and len(result.get('points', [])) == 2,
            'TEACH_FAILED', 'teach', '两个交点全部成功后才可示教')
    return {'algorithm_version': VERSION, 'taught_at': datetime.now(timezone.utc).isoformat(),
            'measurement': result}


def compensation(current, reference, config, *, now=None):
    """Keep measured motion and calibrated placement commands separate; no PLC I/O.

    plc_publish_allowed stays false until a site-specific handshake adapter is
    implemented and validated. Offline data must never enter that adapter.
    """
    output = {'success': False, 'compensation_valid': False, 'plc_publish_allowed': False}
    try:
        require(reference['algorithm_version'] == VERSION, 'VERSION_MISMATCH', 'compensation', '算法版本变化，请重新示教')
        taught = reference['measurement']
        require(current.get('success') is True and taught.get('success') is True,
                'LOCALIZATION_FAILED', 'compensation', '示教或当前帧定位失败')
        for field in ('algorithm_version', 'config_digest', 'calibration_digest', 'unit', 'coordinateSystem', 'robot_frame'):
            require(current[field] == taught[field], 'VERSION_MISMATCH', 'compensation', f'{field} 与示教不一致')
        require(current['config_digest'] == measurement_digest(config), 'VERSION_MISMATCH', 'compensation', '当前配置与测量结果不一致')
        require(current['frame_id'] != taught['frame_id'], 'REUSED_TEACH_FRAME', 'compensation', '生产帧与示教帧相同')
        require(len(current['points']) == len(taught['points']) == 2,
                'INCOMPLETE_RESULT', 'compensation', '缺少完整双交点')
        for measurement in (current, taught):
            require([p['name'] for p in measurement['points']] == ['P1', 'P2']
                    and all(p.get('success') is True for p in measurement['points']),
                    'INCOMPLETE_RESULT', 'compensation', '双交点身份或成功状态不完整')
            require(all(p.get('consistency', {}).get('success') is True for p in measurement['points']),
                    'CONSISTENCY_EVIDENCE_MISSING', 'compensation', '缺少双点独立 2D–3D 一致性检查')
        a = np.asarray([p['robot'] for p in current['points']], float)
        b = np.asarray([p['robot'] for p in taught['points']], float)
        require(a.shape == b.shape == (2, 3) and np.isfinite(a).all() and np.isfinite(b).all(),
                'INVALID_RESULT', 'compensation', 'XYZ 包含无效数值')
        offsets = a-b
        limits = np.asarray(config['maxOffsetMm'], float)
        require(limits.shape == (2, 3) and np.isfinite(limits).all() and np.all(limits > 0),
                'INVALID_CONFIG', 'compensation', '必须配置两组各轴工艺限值')
        require(np.all(np.abs(offsets) <= limits), 'OFFSET_LIMIT', 'compensation', '补偿超出工艺限值')
        placement, transfer = placement_offsets(offsets, config.get('placementTransfer'))
        if now is not None:
            stamp = datetime.fromisoformat(current['captured_at'])
            require(stamp.tzinfo is not None, 'RESULT_EXPIRED', 'compensation', '采集时间必须带时区')
            age = (now-stamp).total_seconds()
            require(0 <= age <= number(config['maxResultAgeSeconds'], 'maxResultAgeSeconds'),
                    'RESULT_EXPIRED', 'compensation', '结果已过期或时间在未来')
        # Only define layer 3 zero after both compensated layers have passed.
        output.update(success=True, compensation_valid=True, offsets=offsets.tolist(),
                      measured_six_values=offsets.reshape(-1).tolist(), placement_offsets=placement.tolist(),
                      placement_coordinate_system=transfer['outputFrame'], transfer_calibration_version=transfer['calibrationVersion'],
                      layer_offsets={'1': placement[0].tolist(), '2': placement[1].tolist(), '3': [0., 0., 0.]},
                      pixel_offsets=(np.asarray(current['pixels'])-taught['pixels']).tolist(),
                      six_values=placement.reshape(-1).tolist(), errorCode='', errorMessage='', stage='complete')
    except LocalizationError as exc:
        output.update(errorCode=exc.code, errorMessage=str(exc), stage=exc.stage)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        output.update(errorCode='INVALID_INPUT', errorMessage=str(exc), stage='compensation')
    return output


def placement_offsets(measured, transfer):
    require(isinstance(transfer, dict) and transfer.get('verified') is True
            and bool(transfer.get('calibrationVersion')) and bool(transfer.get('evidence')),
            'TRANSFER_UNCALIBRATED', 'compensation', '请先标定分层传递比及轴向符号映射')
    require(transfer.get('inputFrame') == 'robot_base' and bool(transfer.get('outputFrame')),
            'TRANSFER_FRAME', 'compensation', '传递映射输入必须为机器人基坐标系，输出坐标系须明确')
    mapped = []
    for index in range(2):
        layer = transfer['layers'][str(index+1)]
        k = number(layer['k_layer'], 'k_layer', strictly=False)
        axes = np.asarray(layer['axisMap'], float)
        require(axes.shape == (3, 3) and np.isin(axes, [-1, 0, 1]).all()
                and np.all(np.abs(axes).sum(0) == 1) and np.all(np.abs(axes).sum(1) == 1),
                'TRANSFER_AXIS_MAP', 'compensation', '轴向映射必须为带符号的轴排列矩阵')
        limit = np.asarray(layer['maxPlacementOffsetMm'], float)
        require(limit.shape == (3,) and np.isfinite(limit).all() and np.all(limit > 0),
                'INVALID_CONFIG', 'compensation', '缺少放置面各轴补偿限值')
        delta = k*(axes @ measured[index])
        require(np.isfinite(delta).all() and np.all(np.abs(delta) <= limit),
                'PLACEMENT_OFFSET_LIMIT', 'compensation', '映射后的放置面补偿超限')
        mapped.append(delta)
    return np.asarray(mapped), transfer
