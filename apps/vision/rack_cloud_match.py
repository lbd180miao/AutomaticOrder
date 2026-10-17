"""Experimental local rigid point-cloud registration; never publishes PLC output."""
import numpy as np
from .algorithms.rack_dual_point import image_roi, TARGETS

VERSION = 'cloud_match_v1'
LIMITS = {'voxel_mm': 2., 'correspondence_mm': 5., 'min_fitness': .65,
          'max_rmse_mm': 2., 'max_shift_mm': 80., 'max_rotation_deg': 15.}


def pointmap(cloud, metadata):
    unit = metadata.get('camera', {}).get('pointcloud_unit')
    if unit not in ('mm', 'm'):
        raise ValueError('点云匹配需要明确的点云单位 mm 或 m')
    if metadata.get('source') != 'rvc_camera' and metadata.get('dual_point_contract', {}).get('cloud_frame') != 'camera':
        raise ValueError('点云匹配需要相机坐标系点云')
    data = np.asarray(cloud, dtype=float)
    if data.ndim != 3 or data.shape[2] != 3:
        raise ValueError('区域选择需要 H×W×3 组织化点云')
    return data * (1000 if unit == 'm' else 1)


def valid(points):
    points = np.asarray(points).reshape(-1, 3)
    return points[np.isfinite(points).all(axis=1) & (points[:, 2] > 0)]


def downsample(points, voxel=2., max_points=20000):
    import open3d as o3d
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud = cloud.voxel_down_sample(voxel)
    if len(cloud.points) > 30:
        cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.5)
    if max_points is not None and len(cloud.points) > max_points:
        cloud = cloud.select_by_index(np.linspace(0, len(cloud.points)-1, max_points, dtype=int))
    return cloud


def sensor_id(metadata):
    camera = metadata.get('camera', {})
    return camera.get('serial_number') or camera.get('sn') or metadata.get('dual_point_contract', {}).get('sensor_id')


def add_display_pixels(result, cloud, metadata):
    """Fit and validate the organized map projection for display only."""
    data = pointmap(cloud, metadata)
    step = max(1, min(data.shape[:2]) // 90)
    yy, xx = np.mgrid[:data.shape[0]:step, :data.shape[1]:step]
    sampled = data[::step, ::step].reshape(-1, 3)
    valid_mask = np.isfinite(sampled).all(1) & (sampled[:, 2] > 0)
    xyz = sampled[valid_mask]
    uv = np.c_[xx.ravel(), yy.ravel()][valid_mask]
    result['pixels'] = [None] * len(result['points'])
    if len(xyz) >= 100:
        design = np.c_[xyz[:, :2] / xyz[:, 2, None], np.ones(len(xyz))]
        fit, _, rank, _ = np.linalg.lstsq(design[::2], uv[::2], rcond=None)
        error = np.percentile(np.linalg.norm(design[1::2] @ fit - uv[1::2], axis=1), 95)
        if rank == 3 and error <= 5:
            for index, point in enumerate(result['points']):
                p = np.asarray(point['xyz'], float)
                if not np.isfinite(p).all() or p[2] <= 0:
                    continue
                pixel = np.r_[p[:2] / p[2], 1.] @ fit
                if 0 <= pixel[0] < data.shape[1] and 0 <= pixel[1] < data.shape[0]:
                    result['pixels'][index] = pixel.tolist()
    if any(pixel is None for pixel in result['pixels']):
        result.setdefault('warnings', []).append('部分参考点无法可靠投影到图像或位于画面外，请查看 XYZ 坐标。')
    return result


def build_template(cloud, config, metadata):
    data = pointmap(cloud, metadata)
    if config.get('imageSize') != [data.shape[1], data.shape[0]]:
        raise ValueError('ROI 分辨率与点云不同')
    rois = config.get('rois', [])
    if len(rois) != 4 or {r['target'] for r in rois} != set(TARGETS):
        raise ValueError('请完成四个区域，分别覆盖 P1/P2 附近的稳定结构')
    mask = np.zeros(data.shape[:2], bool)
    anchors = []
    for name in ('P1', 'P2'):
        group = np.zeros_like(mask)
        for roi in rois:
            if roi['target'].startswith(name+'_'):
                x0, y0, x1, y1 = image_roi(roi, data.shape)
                group[y0:y1, x0:x1] = True
        points = valid(data[group])
        if len(points) < 100:
            raise ValueError(f'{name} 区域有效点不足 100，请选择有深度的稳定结构')
        anchors.append({'name': name, 'success': True, 'xyz': np.median(points, axis=0).tolist()})
        mask |= group
    sampled = downsample(valid(data[mask]))
    points = np.asarray(sampled.points)
    if len(points) < 100:
        raise ValueError('下采样后有效点不足 100')
    eigen = np.linalg.eigvalsh(np.cov(points.T))
    if eigen[1] < 4:
        raise ValueError('模板接近单一直线，请包含横杆、立柱和连接处')
    measurement = {'success': True, 'coordinateSystem': 'camera', 'unit': 'mm', 'points': anchors,
                   'algorithm_version': VERSION, 'measurement_only': True, 'plc_publish_allowed': False}
    return {'version': VERSION, 'points': points.tolist(), 'shape': list(data.shape),
            'sensor_id': sensor_id(metadata), 'config': config, 'limits': dict(LIMITS),
            'measurement': measurement}


def match_template(cloud, metadata, template):
    import open3d as o3d
    if not template or template.get('version') != VERSION:
        raise ValueError('请先在标准位置保存点云模板，再加载待测帧计算')
    data = pointmap(cloud, metadata)
    if list(data.shape) != template['shape']:
        raise ValueError('当前点云分辨率与标准模板不同')
    saved_sensor, current_sensor = template.get('sensor_id'), sensor_id(metadata)
    if saved_sensor and current_sensor != saved_sensor:
        raise ValueError('当前点云相机与标准模板不一致或缺少相机标识')
    source_points = np.asarray(template['points'], float)
    limits = template['limits']
    target_points = valid(data)
    margin = limits['max_shift_mm'] + np.linalg.norm(np.ptp(source_points, axis=0)) * np.sin(np.deg2rad(limits['max_rotation_deg']))
    inside = ((target_points >= source_points.min(axis=0)-margin) &
              (target_points <= source_points.max(axis=0)+margin)).all(axis=1)
    # The search volume is larger than the template. Capping both at 20k
    # makes the target artificially sparse and inflates nearest-point residuals.
    # Keep spatially uniform target density, including for final evaluation.
    target = downsample(target_points[inside], min(1., limits['voxel_mm']), max_points=None)
    if len(target.points) < 100:
        raise ValueError('模板搜索范围内有效点不足 100')
    source = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(source_points))
    transform = np.eye(4)
    for voxel, distance in ((8., 40.), (4., 15.), (2., limits['correspondence_mm']),
                            (1., limits['correspondence_mm'])):
        fit = o3d.pipelines.registration.registration_icp(
            source.voxel_down_sample(voxel), target.voxel_down_sample(voxel), distance, transform,
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60))
        transform = fit.transformation
    # Refine the exact saved template used by the quality gate, rather than
    # only its separately voxelized approximation.
    fit = o3d.pipelines.registration.registration_icp(
        source, target, limits['correspondence_mm'], transform,
        o3d.pipelines.registration.TransformationEstimationPointToPoint(),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60))
    transform = fit.transformation
    # Robust surface refinement reduces the pull of occluded edges and depth
    # outliers. Quality is still evaluated with Euclidean point distances.
    target.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=10., max_nn=30))
    fit = o3d.pipelines.registration.registration_icp(
        source, target, limits['correspondence_mm'], transform,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(
            o3d.pipelines.registration.HuberLoss(k=limits['max_rmse_mm'])),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=40))
    transform = fit.transformation
    fit = o3d.pipelines.registration.evaluate_registration(source, target, limits['correspondence_mm'], transform)
    moved = source_points @ transform[:3, :3].T + transform[:3, 3]
    shift = float(np.linalg.norm(moved.mean(axis=0)-source_points.mean(axis=0)))
    angle = float(np.degrees(np.arccos(np.clip((np.trace(transform[:3, :3])-1)/2, -1, 1))))
    # Point-to-plane information detects unconstrained sliding on flat/linear surfaces.
    pairs = np.asarray(fit.correspondence_set)
    condition = 0.
    if len(pairs) >= 100:
        normals = np.asarray(target.normals)[pairs[:, 1]]
        centered = moved[pairs[:, 0]]-moved.mean(axis=0)
        scale = max(float(np.linalg.norm(np.std(centered, axis=0))), 1.)
        jacobian = np.c_[normals, np.cross(centered/scale, normals)]
        eigen = np.linalg.eigvalsh(jacobian.T @ jacobian / len(jacobian))
        condition = float(max(eigen[0], 0)/max(eigen[-1], 1e-12))
    failures = []
    for failed, reason in (
        (fit.fitness < limits['min_fitness'], '模板覆盖率不足，请检查遮挡、ROI 和拍照位置'),
        (fit.inlier_rmse > limits['max_rmse_mm'], '匹配残差超限，请检查深度噪声、结构变化或重复结构误匹配'),
        (shift > limits['max_shift_mm'], '中心位移超限，请回到模板附近拍照'),
        (angle > limits['max_rotation_deg'], '旋转角度超限，请检查相机和工件姿态'),
        (condition < 1e-4, '结构约束不足，请选择包含不同朝向表面和连接处的区域'),
    ):
        if failed:
            failures.append(reason)
    passed = not failures
    diagnostics = {'fitness': fit.fitness, 'rmse_mm': fit.inlier_rmse, 'shift_mm': shift,
                   'rotation_deg': angle, 'constraint_ratio': condition, 'matched_points': len(pairs),
                   'source_points': len(source.points), 'target_points': len(target.points),
                   'quality_passed': passed, 'failure_reasons': failures,
                   'limits': limits, 'transform': transform.tolist()}
    anchors = np.asarray([p['xyz'] for p in template['measurement']['points']])
    current = anchors @ transform[:3, :3].T + transform[:3, 3]
    summary = (f'模板覆盖率 {fit.fitness:.1%}；残差 {fit.inlier_rmse:.3f}mm；'
               f'中心位移 {shift:.3f}mm；旋转 {angle:.3f}°；约束比 {condition:.6f}')
    return {'success': passed, 'coordinateSystem': 'camera', 'unit': 'mm', 'algorithm_version': VERSION,
            'measurement_only': True, 'plc_publish_allowed': False, 'registration': diagnostics,
            'points': [{'name': name, 'success': passed, 'xyz': xyz.tolist()} for name, xyz in zip(('P1', 'P2'), current)],
            'warnings': [summary, '实验模式：P1/P2 为模板区域参考点的刚体变换推算；重复结构仍需人工核对。'],
            'errorCode': '' if passed else 'REGISTRATION_QUALITY', 'stage': '3d',
            'errorMessage': '' if passed else summary+'；'+'；'.join(failures)+'；候选变换仅供查看。'}
