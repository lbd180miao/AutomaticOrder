"""Three spatial ROIs and two independent member-axis frames (camera mm)."""
from itertools import product
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

VERSION = 'RACK_DUAL_AXIS_3D_V1'
MIN_AXIS_VARIANCE_RATIO = 1.5
NAMES = ('plane1', 'plane2', 'plane3')
EDGES = [(i, j) for i in range(8) for j in range(i + 1, 8) if (i ^ j) in (1, 2, 4)]


def valid_points(cloud):
    points = np.asarray(cloud, dtype=float).reshape(-1, 3)
    return points[np.isfinite(points).all(axis=1) & (np.abs(points[:, 2]) > 1e-9)]


def bounds(box):
    lo = np.array([box[f'{a}min'] for a in 'XYZ'], dtype=float)
    hi = np.array([box[f'{a}max'] for a in 'XYZ'], dtype=float)
    if not np.isfinite([lo, hi]).all() or np.any(lo >= hi):
        raise ValueError('AABB 必须为有限数值，且每个轴 min < max')
    return lo, hi


def corners(box):
    lo, hi = bounds(box)
    return np.array(list(product(*zip(lo, hi))))


def teach_boxes(cloud, rois, margin=0):
    cloud = np.asarray(cloud)
    if cloud.ndim != 3 or cloud.shape[2] != 3:
        raise ValueError('示教需要同帧 H×W×3 组织化点云')
    margin = float(margin)
    if not np.isfinite(margin) or not 0 <= margin <= 500:
        raise ValueError('安全余量必须在 0～500 mm 之间')
    height, width = cloud.shape[:2]
    boxes = {}
    for name in NAMES:
        roi = (rois or {}).get(name)
        if not isinstance(roi, dict):
            raise ValueError('请完整框选 Π1、Π2、Π3')
        x, y, w, h = (float(roi[k]) for k in ('x', 'y', 'w', 'h'))
        if not np.isfinite([x, y, w, h]).all() or w <= 0 or h <= 0:
            raise ValueError(f'{name}: 像素框无效')
        x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
        x1, y1 = min(width, int(np.ceil(x+w))), min(height, int(np.ceil(y+h)))
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f'{name}: 像素框超出图像')
        points = valid_points(cloud[y0:y1, x0:x1])
        if len(points) < 50:
            raise ValueError(f'{name}: 有效点少于 50，请重新框选')
        lo, hi = points.min(0) - margin, points.max(0) + margin
        # A perfectly planar patch still needs a nonzero volume.
        hi = np.maximum(hi, lo + 1e-6)
        boxes[name] = {f'{a}{end}': float(v[i]) for i, a in enumerate('XYZ') for end, v in [('min', lo), ('max', hi)]}
    return boxes


def extract(cloud, boxes):
    points = valid_points(cloud)
    result = {}
    for name in NAMES:
        lo, hi = bounds(boxes[name])
        selected = points[((points >= lo) & (points <= hi)).all(1)]
        if len(selected) < 50:
            raise ValueError(f'{name}: 空间 ROI 内有效点少于 50，请检查包围盒或相机位置')
        result[name] = selected
    return result


def fit_axis(points, voxel_mm=0):
    points = np.asarray(points, dtype=float)
    original_count = len(points)
    if voxel_mm > 0:
        _, indices = np.unique(np.floor(points / voxel_mm), axis=0, return_index=True)
        points = points[np.sort(indices)]
    if len(points) < 50:
        raise ValueError('下采样后有效点少于 50')
    # Statistical outlier removal before total least-squares line fitting.
    distances = cKDTree(points).query(points, k=min(17, len(points)))[0][:, 1:].mean(1)
    points = points[distances <= distances.mean() + 2.5 * distances.std()]
    if len(points) < 30:
        raise ValueError('降噪后有效点不足')
    center = points.mean(0)
    values, vectors = np.linalg.eigh(np.cov(points - center, rowvar=False))
    if values[-1] <= 1e-8:
        raise ValueError('点云无有效空间跨度，无法拟合轴线')
    ratio = float(values[-1] / max(values[-2], 1e-8))
    warnings = ([f'主轴方差比 {ratio:.3f} 低于阈值 {MIN_AXIS_VARIANCE_RATIO:g}，已继续计算，轴线方向可能不稳定']
                if ratio < MIN_AXIS_VARIANCE_RATIO else [])
    direction = vectors[:, -1]
    if direction[np.argmax(np.abs(direction))] < 0:
        direction = -direction
    residual = np.linalg.norm(np.cross(points-center, direction), axis=1)
    return {'point': center.tolist(), 'direction': direction.tolist(),
            'axis_variance_ratio': ratio, 'quality_warnings': warnings,
            'input_points': original_count, 'inlier_points': len(points),
            'rms_mm': float(np.sqrt(np.mean(residual**2))),
            'linearity': float(1-values[-2]/values[-1])}


def pair_frame(beam, pillar, reference=None):
    p, q = np.array(beam['point']), np.array(pillar['point'])
    u, v = np.array(beam['direction']), np.array(pillar['direction'])
    if reference:
        ref = np.array(reference['frame'])[:3, :3]
        if u @ ref[:, 0] < 0: u = -u
        if v @ ref[:, 1] < 0: v = -v
    dot = float(np.clip(u @ v, -1, 1))
    if abs(dot) > 0.98:
        raise ValueError('横梁与立柱轴线近似平行，无法构建独立位姿')
    t, s = np.linalg.lstsq(np.column_stack((u, -v)), q-p, rcond=None)[0]
    a, b = p+t*u, q+s*v
    origin = (a+b)/2
    y = v - dot*u
    y /= np.linalg.norm(y)
    frame = np.eye(4)
    frame[:3, :3] = np.column_stack((u, y, np.cross(u, y)))
    frame[:3, 3] = origin
    gap = float(np.linalg.norm(a-b))
    return {'frame': frame.tolist(), 'origin': origin.tolist(),
            'closest_points': [a.tolist(), b.tolist()], 'gap_mm': gap,
            'relationship': 'intersecting' if gap < 1e-3 else 'skew',
            'angle_deg': float(np.degrees(np.arccos(abs(dot))))}


def fit_region(points, voxel_mm, name, frame_label):
    label = {'plane1': 'Π1（蓝框）', 'plane2': 'Π2（橙框）', 'plane3': 'Π3（粉框）'}[name]
    try:
        axis = fit_axis(points, voxel_mm)
        axis['quality_warnings'] = [f'{frame_label} · {label}：{message}' for message in axis['quality_warnings']]
        return axis
    except ValueError as exc:
        action = ('请在标准帧上检查该区域，确认后重新保存标准；仅修改当前帧不会修复旧标准。'
                  if frame_label.startswith('标准帧') else '请检查当前帧该区域，保留同一构件的连续长段，避开背景和交叉处；深度缺失时请重新采集。')
        raise ValueError(f'{frame_label} · {label}：{exc}。{action}') from exc


def fit_pair(beam, pillar, reference, key, frame_label):
    try:
        pair = pair_frame(beam, pillar, reference)
        pair['quality_warnings'] = list(dict.fromkeys(beam.get('quality_warnings', []) + pillar.get('quality_warnings', [])))
        return pair
    except ValueError as exc:
        members = 'Π1–Π2' if key == 'A' else 'Π3–Π2'
        raise ValueError(f'{frame_label} · {key} 组（{members}）：{exc}；请检查这两个 ROI 是否选中了不同构件。') from exc


def compute(cloud, config, standard=None):
    frame_label = '当前帧' if standard else '标准帧（示教预览）'
    try:
        regions = extract(cloud, config['spatial_rois'])
    except ValueError as exc:
        message = str(exc)
        for index, name in enumerate(NAMES, 1):
            message = message.replace(name, f'Π{index}')
        raise ValueError(f'{frame_label} · {message}') from exc
    voxel = float(config.get('voxel_mm', 0))
    if not np.isfinite(voxel) or not 0 <= voxel <= 50:
        raise ValueError('下采样体素必须在 0～50 mm 之间')
    axes = {name: fit_region(points, voxel, name, frame_label) for name, points in regions.items()}
    groups = {}
    for key, beam in [('A', 'plane1'), ('B', 'plane3')]:
        ref = (standard or {}).get('groups', {}).get(key)
        pair = fit_pair(axes[beam], axes['plane2'], ref, key, frame_label)
        if ref:
            current, taught = np.array(pair['frame']), np.array(ref['frame'])
            delta = current @ np.linalg.inv(taught)
            shift = current[:3, 3] - taught[:3, 3]
            angles = Rotation.from_matrix(delta[:3, :3]).as_euler('xyz', degrees=True)
            pair.update(delta_T=delta.tolist(), translation_mm=dict(zip('xyz', shift.tolist())),
                        rotation_deg=dict(zip(('rx', 'ry', 'rz'), angles.tolist())),
                        angle_delta_deg=pair['angle_deg']-ref['angle_deg'],
                        gap_delta_mm=pair['gap_mm']-ref['gap_mm'])
        else:
            pair.update(delta_T=None, translation_mm=None, rotation_deg=None)
        groups[key] = pair
    warnings = list(dict.fromkeys(message for collection in (groups, (standard or {}).get('groups', {}))
                                  for group in collection.values() for message in group.get('quality_warnings', [])))
    return {'algorithm_version': VERSION, 'axes': axes, 'groups': groups,
            'quality_warnings': warnings, 'warning_message': '；'.join(warnings),
            'has_standard': bool(standard and all(k in standard.get('groups', {}) for k in ('A', 'B'))),
            'layer_spacing_mm': float(np.linalg.norm(np.array(groups['A']['origin'])-groups['B']['origin']))}


def projection_model(cloud):
    """Calibrate display-only perspective mapping from same-frame XYZ/pixels.

    No guessed intrinsics: fitted camera mapping must reproduce the pixel grid.
    """
    if cloud.ndim != 3:
        return None
    yy, xx = np.indices(cloud.shape[:2])
    pts = cloud.reshape(-1, 3)
    pixels = np.column_stack((xx.ravel(), yy.ravel()))
    good = np.isfinite(pts).all(1) & (np.abs(pts[:, 2]) > 1e-9)
    pts, pixels = pts[good], pixels[good]
    step = max(1, len(pts)//12000)
    pts, pixels = pts[::step], pixels[::step]
    if len(pts) < 30: return None
    design = np.column_stack((pts[:, 0]/pts[:, 2], pts[:, 1]/pts[:, 2], np.ones(len(pts))))
    model, _, rank, _ = np.linalg.lstsq(design, pixels, rcond=None)
    if rank < 3 or np.sqrt(np.mean((design @ model-pixels)**2)) > 3:
        return None
    return model


def project(points, model):
    points = np.asarray(points)
    if model is None or np.any(points[:, 2] <= 1e-9): return None
    return (np.column_stack((points[:, 0]/points[:, 2], points[:, 1]/points[:, 2], np.ones(len(points)))) @ model).tolist()


def preview(cloud, config, result=None):
    points = valid_points(cloud)
    model = projection_model(np.asarray(cloud))
    return {'points': points[::max(1, len(points)//6000)].tolist(), 'edges': EDGES,
            'boxes': {name: {'vertices': corners(box).tolist(), 'pixels': project(corners(box), model)}
                      for name, box in config['spatial_rois'].items()},
            'spacing_pixels': project([result['groups'][k]['origin'] for k in ('A', 'B')], model) if result else None,
            'projection_warning': '' if model is not None else '无法从当前点云恢复投影参数，仅显示 3D 包围盒'}
