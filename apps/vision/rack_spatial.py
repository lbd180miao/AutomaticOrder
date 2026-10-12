"""Three spatial ROIs and two independent member-axis frames (camera mm) - PLANE FITTING VERSION."""
from itertools import product
import numpy as np
from scipy.spatial.transform import Rotation

VERSION = 'RACK_DUAL_PLANE_3D_V2'
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


def fit_plane_ransac(points, label='', expected_normal=None):
    """Bounded RANSAC search followed by robust all-point refinement."""
    from .algorithms.robust_rack_geometry import robust_plane
    try:
        plane, _ = robust_plane(points, expected_normal=expected_normal)
        return plane
    except ValueError as exc:
        raise ValueError(f'{label}: {exc}') from exc


def compute_plane_intersection(plane1, plane2):
    """
    计算两平面的交线。

    平面1: n1·P + d1 = 0
    平面2: n2·P + d2 = 0
    交线: P(t) = point + t * direction

    Returns:
        dict: {'point': 交线上一点, 'direction': 交线方向}
    """
    n1 = np.array(plane1['normal'])
    n2 = np.array(plane2['normal'])
    d1 = plane1['offset']
    d2 = plane2['offset']

    # 交线方向 = n1 × n2
    direction = np.cross(n1, n2)
    direction_norm = np.linalg.norm(direction)

    if direction_norm < 1e-6:
        raise ValueError('两平面近似平行，无法计算交线')

    direction = direction / direction_norm

    # Solve around the measured surface, not the camera origin. This keeps the
    # system small at 1.5–2 m and avoids switching a fixed zero-coordinate axis.
    anchor = (np.asarray(plane1['centroid'], dtype=float)
              + np.asarray(plane2['centroid'], dtype=float)) / 2
    A = np.array([n1, n2, direction])
    b = np.array([-d1-n1@anchor, -d2-n2@anchor, 0.0])
    try:
        point = anchor + np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f'平面交线求解失败：{exc}') from exc

    return {
        'point': point.tolist(),
        'direction': direction.tolist()
    }


def pair_frame_from_planes(beam_plane, pillar_plane, reference=None):
    """
    从两个平面的交线构建坐标系。

    Args:
        beam_plane: 横梁平面（Π1 或 Π3）
        pillar_plane: 立柱平面（Π2）
        reference: 参考坐标系（用于保持方向一致）

    Returns:
        dict: {
            'frame': 4x4变换矩阵,
            'origin': 坐标系原点（交线上取质心投影点）,
            'intersection_line': 交线参数
        }
    """
    # 计算交线
    try:
        intersection = compute_plane_intersection(beam_plane, pillar_plane)
    except ValueError as e:
        raise ValueError(f'平面交线计算失败：{e}')

    # 交线方向作为 X 轴
    x_axis = np.array(intersection['direction'])
    x_axis = x_axis / np.linalg.norm(x_axis)

    # 立柱平面法向量作为 Y 轴基准
    n_pillar = np.array(pillar_plane['normal'])
    n_pillar = n_pillar / np.linalg.norm(n_pillar)

    # Y 轴：n_pillar 投影到垂直于 X 轴的方向
    y_axis = n_pillar - np.dot(n_pillar, x_axis) * x_axis
    y_axis_norm = np.linalg.norm(y_axis)

    if y_axis_norm < 1e-6:
        raise ValueError('立柱平面法向量与交线方向平行，无法构建坐标系')

    y_axis = y_axis / y_axis_norm

    # Z 轴 = X × Y（右手系）
    z_axis = np.cross(x_axis, y_axis)
    z_axis = z_axis / np.linalg.norm(z_axis)

    # 如果有参考坐标系，确保方向一致
    if reference:
        ref = np.array(reference['frame'])[:3, :3]
        if np.dot(x_axis, ref[:, 0]) < 0:
            x_axis = -x_axis
            z_axis = -z_axis  # 保持右手系
        if np.dot(y_axis, ref[:, 1]) < 0:
            y_axis = -y_axis
            z_axis = np.cross(x_axis, y_axis)
            z_axis = z_axis / np.linalg.norm(z_axis)

    # 原点：两平面质心的中点，投影到交线上
    c1 = np.array(beam_plane['centroid'])
    c2 = np.array(pillar_plane['centroid'])
    centroid_mid = (c1 + c2) / 2

    # 投影到交线
    line_point = np.array(intersection['point'])
    vec_to_mid = centroid_mid - line_point
    proj_length = np.dot(vec_to_mid, x_axis)
    origin = line_point + proj_length * x_axis

    # 构建变换矩阵
    frame = np.eye(4)
    frame[:3, :3] = np.column_stack([x_axis, y_axis, z_axis])
    frame[:3, 3] = origin

    # 验证正交性
    det = np.linalg.det(frame[:3, :3])
    if abs(det - 1.0) > 0.01:
        raise ValueError(f'坐标系行列式异常：{det:.6f}，非正交归一化')

    # 计算两平面夹角
    angle_deg = float(np.degrees(np.arccos(np.clip(abs(np.dot(
        np.array(beam_plane['normal']),
        np.array(pillar_plane['normal'])
    )), 0, 1))))
    amplification = 1.0 / max(np.sin(np.deg2rad(angle_deg)), 1e-12)
    warnings = beam_plane.get('quality_warnings', []) + pillar_plane.get('quality_warnings', [])
    if amplification > 4:
        warnings.append(f'两平面夹角仅 {angle_deg:.2f}°，交线误差放大约 {amplification:.1f} 倍；请框选不同朝向的表面')

    return {
        'frame': frame.tolist(),
        'origin': origin.tolist(),
        'intersection_line': intersection,
        'angle_deg': angle_deg,
        'intersection_amplification': float(amplification),
        'intersection_reliable': bool(amplification <= 4),
        'origin_definition': 'roi_centroid_projection_on_plane_intersection',
        'along_line_position_observable': False,
        'fit_version': beam_plane.get('fit_version'),
        'plane_models': {'beam': beam_plane, 'pillar': pillar_plane},
        'quality_warnings': warnings,
    }


def fit_region(points, name, frame_label, reference_plane=None):
    """拟合单个区域的平面"""
    label = {'plane1': 'Π1（顶部横梁）', 'plane2': 'Π2（左侧立柱）', 'plane3': 'Π3（底部横梁）'}[name]
    try:
        plane = fit_plane_ransac(points, label, (reference_plane or {}).get('normal'))
        plane['quality_warnings'] = [f'{frame_label} · {label}：{msg}' for msg in plane['quality_warnings']]
        return plane
    except ValueError as exc:
        action = ('请在标准帧上检查该区域，确认后重新保存标准；仅修改当前帧不会修复旧标准。'
                  if frame_label.startswith('标准帧') else '请检查当前帧该区域，确保选中了单一平面构件；深度缺失时请重新采集。')
        raise ValueError(f'{frame_label} · {label}：{exc}。{action}') from exc


def fit_pair(beam_plane, pillar_plane, reference, key, frame_label):
    """从两个平面构建坐标系"""
    try:
        pair = pair_frame_from_planes(beam_plane, pillar_plane, reference)
        pair['quality_warnings'] = list(dict.fromkeys(pair['quality_warnings']))
        return pair
    except ValueError as exc:
        members = 'Π1–Π2' if key == 'A' else 'Π3–Π2'
        raise ValueError(f'{frame_label} · {key} 组（{members}）：{exc}；请检查这两个 ROI 是否选中了不同的平面构件。') from exc


def compute(cloud, config, standard=None):
    """
    主计算流程：拟合三个平面，计算两组独立坐标系。

    A 组：Π1（顶部横梁）∩ Π2（左侧立柱）
    B 组：Π3（底部横梁）∩ Π2（左侧立柱）
    """
    frame_label = '当前帧' if standard else '标准帧（示教预览）'

    try:
        regions = extract(cloud, config['spatial_rois'])
    except ValueError as exc:
        message = str(exc)
        for index, name in enumerate(NAMES, 1):
            message = message.replace(name, f'Π{index}')
        raise ValueError(f'{frame_label} · {message}') from exc

    # 拟合三个平面
    planes = {name: fit_region(points, name, frame_label, (standard or {}).get('planes', {}).get(name))
              for name, points in regions.items()}

    # 构建两组坐标系
    groups = {}
    for key, beam_name in [('A', 'plane1'), ('B', 'plane3')]:
        ref = (standard or {}).get('groups', {}).get(key)
        pair = fit_pair(planes[beam_name], planes['plane2'], ref, key, frame_label)

        if ref:
            # 计算相对标准帧的偏差
            current = np.array(pair['frame'])
            taught = np.array(ref['frame'])
            delta = current @ np.linalg.inv(taught)

            # 分解平移和旋转
            shift = current[:3, 3] - taught[:3, 3]
            angles = Rotation.from_matrix(delta[:3, :3]).as_euler('xyz', degrees=True)

            pair.update({
                'delta_T': delta.tolist(),
                'translation_mm': dict(zip('xyz', shift.tolist())),
                'rotation_deg': dict(zip(('rx', 'ry', 'rz'), angles.tolist())),
                'angle_delta_deg': pair['angle_deg'] - ref['angle_deg']
            })
        else:
            pair.update({
                'delta_T': None,
                'translation_mm': None,
                'rotation_deg': None
            })

        groups[key] = pair

    # 汇总警告
    warnings = list(dict.fromkeys(
        msg for collection in (planes, groups, (standard or {}).get('groups', {}))
        for item in collection.values()
        for msg in item.get('quality_warnings', [])
    ))

    # 计算层距（两组坐标系原点之间的距离）
    origin_a = np.array(groups['A']['origin'])
    origin_b = np.array(groups['B']['origin'])
    layer_spacing = float(np.linalg.norm(origin_a - origin_b))

    return {
        'algorithm_version': VERSION,
        'planes': planes,  # 保存平面参数用于诊断
        'groups': groups,
        'quality_warnings': warnings,
        'warning_message': '；'.join(warnings),
        'has_standard': bool(standard and all(k in standard.get('groups', {}) for k in ('A', 'B'))),
        'layer_spacing_mm': layer_spacing
    }


def projection_model(cloud):
    """从点云标定投影模型（仅用于可视化）"""
    if cloud.ndim != 3:
        return None
    yy, xx = np.indices(cloud.shape[:2])
    pts = cloud.reshape(-1, 3)
    pixels = np.column_stack((xx.ravel(), yy.ravel()))
    good = np.isfinite(pts).all(1) & (np.abs(pts[:, 2]) > 1e-9)
    pts, pixels = pts[good], pixels[good]
    step = max(1, len(pts) // 12000)
    pts, pixels = pts[::step], pixels[::step]
    if len(pts) < 30:
        return None
    design = np.column_stack((pts[:, 0] / pts[:, 2], pts[:, 1] / pts[:, 2], np.ones(len(pts))))
    model, _, rank, _ = np.linalg.lstsq(design, pixels, rcond=None)
    if rank < 3 or np.sqrt(np.mean((design @ model - pixels) ** 2)) > 3:
        return None
    return model


def project(points, model):
    """将3D点投影到2D像素（仅用于可视化）"""
    points = np.asarray(points)
    if model is None or np.any(points[:, 2] <= 1e-9):
        return None
    design = np.column_stack((points[:, 0] / points[:, 2], points[:, 1] / points[:, 2], np.ones(len(points))))
    return (design @ model).tolist()


def preview(cloud, config, result=None):
    """生成前端可视化数据"""
    points = valid_points(cloud)
    model = projection_model(np.asarray(cloud))
    return {
        'points': points[::max(1, len(points) // 6000)].tolist(),
        'edges': EDGES,
        'boxes': {
            name: {
                'vertices': corners(box).tolist(),
                'pixels': project(corners(box), model)
            }
            for name, box in config['spatial_rois'].items()
        },
        'spacing_pixels': project([result['groups'][k]['origin'] for k in ('A', 'B')], model) if result else None,
        'projection_warning': '' if model is not None else '无法从当前点云恢复投影参数，仅显示 3D 包围盒'
    }
