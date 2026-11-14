"""Standalone registration experiment. All computation uses millimetres; no app imports."""
from dataclasses import asdict, dataclass
from pathlib import Path
import copy
import time

import numpy as np
import open3d as o3d


@dataclass
class Settings:
    voxel_mm: float = 2.0
    distance_mm: float = 5.0
    min_coverage: float = 0.65
    max_rmse_mm: float = 2.0
    global_search: bool = False
    filter_target: bool = True

    def validate(self):
        values = np.array([self.voxel_mm, self.distance_mm, self.min_coverage, self.max_rmse_mm])
        if not np.isfinite(values).all() or min(self.voxel_mm, self.distance_mm, self.max_rmse_mm) <= 0:
            raise ValueError('体素、匹配距离、残差上限必须是正数')
        if not 0 < self.min_coverage <= 1:
            raise ValueError('覆盖率阈值必须在 0 到 100% 之间')


def cloud_of(points):
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=float)))


def convert_npy_to_ply(source, destination, *, meters_to_mm=False):
    """Format conversion only: retain valid XYZ samples, including duplicates."""
    source, destination = Path(source), Path(destination)
    if source.suffix.lower() != '.npy' or destination.suffix.lower() != '.ply':
        raise ValueError('请选择 NPY 输入文件和 PLY 输出文件')
    if source.resolve() == destination.resolve():
        raise ValueError('不能覆盖原始 NPY 文件')
    array = np.load(source, allow_pickle=False, mmap_mode='r')
    if array.ndim not in (2, 3) or array.shape[-1] != 3:
        raise ValueError('点云 NPY 必须是 N×3 或 H×W×3；请选择 pointcloud.npy，不要选择标定矩阵或索引文件')
    if array.dtype.kind not in 'fiu':
        raise ValueError('NPY 必须包含实数 XYZ 坐标')
    points = np.asarray(array, dtype=np.float64).reshape(-1, 3)
    valid = np.isfinite(points).all(axis=1) & np.any(points != 0, axis=1)
    kept = points[valid]
    if not len(kept):
        raise ValueError('没有有效点：点云全部为零或包含无效坐标')
    if meters_to_mm:
        kept = kept * 1000.0
    if not np.isfinite(kept).all():
        raise ValueError('坐标转换后溢出，请检查输入单位和数值')
    if not o3d.io.write_point_cloud(str(destination), cloud_of(kept), write_ascii=False):
        raise OSError('PLY 写入失败，请检查保存目录和文件权限')
    return {'output_path': str(destination.resolve()), 'points': len(kept),
            'removed_invalid_points': len(points)-len(kept),
            'coordinate_conversion': '米 → 毫米（×1000）' if meters_to_mm else '保持原坐标数值'}


def load_cloud(path, unit='mm'):
    path = Path(path)
    if unit not in ('mm', 'm'):
        raise ValueError('请选择 mm 或 m')
    suffix = path.suffix.lower()
    if suffix == '.npy':
        a = np.load(path, allow_pickle=False, mmap_mode='r')
        if a.ndim not in (2, 3) or a.shape[-1] != 3:
            raise ValueError('NPY 必须是 N×3 或 H×W×3')
        points = a.reshape(-1, 3)
    elif suffix in ('.txt', '.asc', '.csv', '.xyz'):
        points = np.loadtxt(path, delimiter=',' if suffix == '.csv' else None, usecols=(0, 1, 2), ndmin=2)
    elif suffix in ('.ply', '.pcd', '.pts', '.xyzn', '.xyzrgb'):
        points = np.asarray(o3d.io.read_point_cloud(str(path)).points)
    else:
        raise ValueError('不支持此格式；请从 CloudCompare 导出 PLY 或 PCD')
    before = len(points)
    points = points[np.isfinite(points).all(axis=1)]
    # Organized camera maps often encode missing measurements as (0, 0, 0).
    if suffix == '.npy':
        points = points[np.any(points != 0, axis=1)]
    points = np.unique(points, axis=0)
    if len(points) < 100:
        raise ValueError('有效点不足 100 个，无法可靠测试配准')
    points = points * (1000.0 if unit == 'm' else 1.0)
    if np.max(np.ptp(points, axis=0)) <= 0:
        raise ValueError('点云没有有效空间尺寸')
    return cloud_of(points), {'path': str(path.resolve()), 'input_unit': unit,
                              'points': len(points), 'removed_invalid_or_duplicate': before-len(points),
                              'size_mm': np.ptp(points, axis=0).tolist()}


def sampled(cloud, voxel, clean=False):
    result = cloud.voxel_down_sample(voxel)
    if clean and len(result.points) > 30:
        result, _ = result.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.5)
    if len(result.points) < 30:
        raise ValueError('下采样后点数不足，请减小体素尺寸或检查点云单位')
    if len(result.points) > 600000:
        raise ValueError('下采样后超过 60 万点，请增大体素或先在 CloudCompare 裁剪背景')
    return result


def register(template, scene, settings, progress=lambda _: None, *, seed=7,
             initial_transform=None, search_scene=None):
    settings.validate()
    start = time.perf_counter()
    reg = o3d.pipelines.registration
    v, distance = settings.voxel_mm, settings.distance_mm
    progress('准备均匀采样点云…')
    source = sampled(template, v)
    target = sampled(scene, v, settings.filter_target)
    transform = np.eye(4) if initial_transform is None else np.array(initial_transform, dtype=float)
    if settings.global_search and initial_transform is None:
        progress('全局搜索：计算几何特征…')
        coarse = max(v * 4, distance * 2)
        s = sampled(source, coarse)
        t = sampled(target if search_scene is None else search_scene, coarse)
        features = []
        for cloud in (s, t):
            cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=coarse*2, max_nn=40))
            features.append(reg.compute_fpfh_feature(cloud, o3d.geometry.KDTreeSearchParamHybrid(radius=coarse*5, max_nn=100)))
        progress('全局搜索：RANSAC 候选匹配…')
        o3d.utility.random.seed(seed)
        fit = reg.registration_ransac_based_on_feature_matching(
            s, t, *features, True, coarse*1.5,
            reg.TransformationEstimationPointToPoint(False), 3,
            [reg.CorrespondenceCheckerBasedOnEdgeLength(0.9),
             reg.CorrespondenceCheckerBasedOnDistance(coarse*1.5)],
            reg.RANSACConvergenceCriteria(100000, 0.999))
        if len(fit.correspondence_set) < 10:
            raise ValueError('全局搜索未找到可靠初值；请裁剪背景或调整体素后重试')
        transform = fit.transformation
    for i, factor in enumerate((4, 2, 1)):
        progress(f'局部精配准：第 {i+1}/3 级…')
        s, t = source.voxel_down_sample(v*factor), target.voxel_down_sample(v*factor)
        fit = reg.registration_icp(s, t, max(distance, v*factor*2), transform,
                                  reg.TransformationEstimationPointToPoint(),
                                  reg.ICPConvergenceCriteria(max_iteration=80))
        transform = fit.transformation
    progress('鲁棒表面精配准与质量评估…')
    target.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=max(v*4, distance*2), max_nn=40))
    fit = reg.registration_icp(source, target, distance, transform,
                              reg.TransformationEstimationPointToPlane(reg.HuberLoss(k=settings.max_rmse_mm)),
                              reg.ICPConvergenceCriteria(max_iteration=60))
    transform = fit.transformation
    fit = reg.evaluate_registration(source, target, distance, transform)
    moved = copy.deepcopy(source).transform(transform)
    errors = np.asarray(moved.compute_point_cloud_distance(target))
    pairs = np.asarray(fit.correspondence_set)
    ratio = 0.0
    if len(pairs) >= 30:
        p = np.asarray(moved.points)[pairs[:, 0]]
        p = p - p.mean(axis=0)
        n = np.asarray(target.normals)[pairs[:, 1]]
        scale = max(float(np.linalg.norm(np.std(p, axis=0))), 1e-9)
        jacobian = np.c_[n, np.cross(p/scale, n)]
        eigen = np.linalg.eigvalsh(jacobian.T @ jacobian / len(p))
        ratio = float(max(eigen[0], 0)/max(eigen[-1], 1e-12))
    reasons = []
    if fit.fitness < settings.min_coverage:
        reasons.append('模板覆盖率不足')
    if not len(pairs):
        reasons.append('无有效对应点')
    elif fit.inlier_rmse > settings.max_rmse_mm:
        reasons.append('匹配残差超限')
    if ratio < 1e-4:
        reasons.append('几何约束较弱，存在滑动或旋转歧义')
    center = np.asarray(template.get_center())
    current_center = transform[:3, :3] @ center + transform[:3, 3]
    result = {
        'status': '需复核' if reasons else '指标通过，待目视确认',
        'quality_passed': not reasons, 'reasons': reasons,
        'score_definition': '100 × 模板采样点中距测试点云不超过匹配距离的比例；不是正确概率',
        'coverage_percent': float(fit.fitness*100),
        'rmse_mm': float(fit.inlier_rmse) if len(pairs) else None,
        'all_template_p95_mm': float(np.percentile(errors, 95)),
        'constraint_ratio': ratio, 'matched_points': len(pairs),
        'template_evaluation_points': len(source.points), 'scene_evaluation_points': len(target.points),
        'template_center_in_scene_mm': current_center.tolist(),
        'center_delta_mm': (current_center-center).tolist(),
        'rotation_angle_deg': float(np.degrees(np.arccos(np.clip((np.trace(transform[:3, :3])-1)/2, -1, 1)))),
        'transform_template_to_scene_mm': transform.tolist(), 'settings': asdict(settings),
        'elapsed_seconds': time.perf_counter()-start,
        'warning': '重复结构可能出现高分错配；该独立实验不连接 PLC，也不代表生产算法验证通过。',
    }
    return result, moved, errors


def same_pose(first, second, center, translation_mm, rotation_deg=3.0):
    a, b = (np.asarray(r['transform_template_to_scene_mm']) for r in (first, second))
    shift = np.linalg.norm(a[:3, :3]@center+a[:3, 3] - (b[:3, :3]@center+b[:3, 3]))
    angle = np.degrees(np.arccos(np.clip((np.trace(a[:3, :3]@b[:3, :3].T)-1)/2, -1, 1)))
    return shift < translation_mm and angle < rotation_deg


def register_candidates(template, scene, settings, count=5, attempts=15, progress=lambda _: None):
    """Multi-start hypotheses, NOT a guaranteed count of physical objects.

    Mask accepted locations only during global initialization. All refinement,
    scores and error colors always use the same full scene and settings.
    """
    settings.validate()
    if not 1 <= count <= 10 or not count <= attempts <= 60:
        raise ValueError('保留数量需为 1–10，搜索次数需在保留数量与 60 之间')
    started = time.perf_counter()
    results, failures = [], []
    search = sampled(scene, settings.voxel_mm, settings.filter_target)
    center = np.asarray(template.get_center())
    merge_mm = max(settings.voxel_mm*2, settings.distance_mm)
    rng = np.random.default_rng(7)
    for index in range(attempts):
        prefix = f'候选搜索 {index+1}/{attempts}，已发现 {len(results)} 个：'
        progress(prefix)
        initial = None
        if not settings.global_search:
            initial = np.eye(4)
            if index:
                rotation = o3d.geometry.get_rotation_matrix_from_xyz(rng.uniform(-0.12, 0.12, 3))
                initial[:3, :3] = rotation
                initial[:3, 3] = center-rotation@center + rng.uniform(-1, 1, 3)*max(20, settings.distance_mm*4)
        try:
            candidate = register(template, scene, settings,
                                 lambda message: progress(prefix+message), seed=7+index,
                                 initial_transform=initial, search_scene=search)
        except (ValueError, RuntimeError) as exc:
            failures.append({'attempt': index+1, 'reason': str(exc)})
            search = sampled(scene, settings.voxel_mm, settings.filter_target)
            continue
        result, moved, _ = candidate
        if result['matched_points'] < 10:
            failures.append({'attempt': index+1, 'reason': '有效对应点不足 10，不构成候选'})
            continue
        result['search_attempt'] = index+1
        duplicate = next((i for i, item in enumerate(results)
                          if same_pose(item[0], result, center, merge_mm)), None)
        def rank(item):
            r = item[0]
            return (-r['coverage_percent'], r['rmse_mm'] if r['rmse_mm'] is not None else float('inf'))
        if duplicate is None:
            results.append(candidate)
        elif rank(candidate) < rank(results[duplicate]):
            results[duplicate] = candidate
        results.sort(key=rank)
        results = results[:count]
        # Seek other instances without altering the scene used for scoring.
        if settings.global_search and result['coverage_percent'] >= settings.min_coverage*100:
            distances = np.asarray(search.compute_point_cloud_distance(moved))
            remaining = np.flatnonzero(distances > max(settings.distance_mm*2, settings.voxel_mm*3))
            if len(remaining) >= 100:
                search = search.select_by_index(remaining)
            else:
                search = sampled(scene, settings.voxel_mm, settings.filter_target)
    for i, (result, _, _) in enumerate(results):
        result['candidate_id'] = i+1
        result['algorithm'] = 'algorithm_1_fpfh_icp' if settings.global_search else 'algorithm_1_local_icp'
    summary = {'requested_count': count, 'returned_count': len(results), 'attempts': attempts,
               'failed_attempts': failures, 'elapsed_seconds': time.perf_counter()-started,
               'merge_translation_mm': merge_mm, 'merge_rotation_deg': 3.0,
               'ranking': 'coverage_desc_then_rmse_asc',
               'note': '候选是不同位姿假设，不保证对应不同实体，也不保证找到所有匹配；未通过质量阈值的候选保留供人工筛选。'}
    return results, summary


def ppf_oriented_points(cloud, voxel, limit, clean=False):
    """Camera-frame normals; bounded spatial sampling for quadratic PPF training."""
    result = sampled(cloud, voxel, clean)
    actual_voxel = voxel
    while len(result.points) > limit:
        actual_voxel *= 1.25
        result = cloud.voxel_down_sample(actual_voxel)
        if clean:
            result, _ = result.remove_statistical_outlier(20, 2.5)
    if len(result.points) < 30:
        raise ValueError('PPF 表面点不足，请检查模板或采样尺度')
    result.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=actual_voxel*4, max_nn=40))
    result.orient_normals_towards_camera_location(np.zeros(3))
    normals = np.asarray(result.normals)
    lengths = np.linalg.norm(normals, axis=1)
    valid = np.isfinite(normals).all(axis=1) & (lengths > 0.5)
    values = np.c_[np.asarray(result.points)[valid], normals[valid]/lengths[valid, None]]
    if len(values) < 30:
        raise ValueError('PPF 有效法线不足')
    return np.ascontiguousarray(values, dtype=np.float32), actual_voxel


def register_ppf_candidates(template, scene, settings, count=5, attempts=15, progress=lambda _: None):
    """PPF pose voting followed by the same full-scene ICP and scoring as algorithm 1."""
    import json
    import subprocess
    import sys
    import tempfile
    import os
    settings.validate()
    if not 1 <= count <= 10 or not count <= attempts <= 60:
        raise ValueError('保留数量需为 1–10，精修候选上限需在保留数量与 60 之间')
    runtime = Path(__file__).with_name('.ppf_runtime')
    if not (runtime/'cv2').is_dir():
        raise ValueError('算法 2 缺少独立 PPF 依赖，请运行同目录 install_ppf.bat')
    start = time.perf_counter()
    progress('算法 2：计算表面法线和 PPF 采样点…')
    diameter = float(np.linalg.norm(template.get_max_bound()-template.get_min_bound()))
    voxel = max(settings.voxel_mm, diameter*0.015)
    model, model_voxel = ppf_oriented_points(template, voxel, 1500)
    target, target_voxel = ppf_oriented_points(scene, voxel, 5000, settings.filter_target)
    progress(f'算法 2：PPF 建模与投票（模板 {len(model)} 点，场景 {len(target)} 点）…')
    with tempfile.TemporaryDirectory(prefix='cloud_ppf_') as directory:
        folder = Path(directory)
        np.save(folder/'model.npy', model)
        np.save(folder/'scene.npy', target)
        try:
            process = subprocess.run([sys.executable, '-u', '-X', 'faulthandler',
                                      str(Path(__file__).with_name('ppf_worker.py')), directory],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace',
                                     timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('PPF 搜索超过 180 秒，已停止；请裁剪测试背景或缩小模板后重试') from exc
        if process.returncode:
            raise RuntimeError(f'PPF 子进程失败 ({process.returncode})：'+process.stderr[-1600:])
        poses = json.loads((folder/'poses.json').read_text(encoding='utf-8'))
    results, failures = [], []
    center = np.asarray(template.get_center())
    merge_mm = max(settings.voxel_mm*2, settings.distance_mm)
    def rank(candidate):
        r = candidate[0]
        return (-r['coverage_percent'], r['rmse_mm'] if r['rmse_mm'] is not None else float('inf'))
    for index, pose in enumerate(poses[:attempts]):
        prefix = f'算法 2：精修候选 {index+1}/{min(len(poses), attempts)}：'
        try:
            candidate = register(template, scene, settings, lambda text: progress(prefix+text),
                                 initial_transform=np.asarray(pose['transform']))
        except (ValueError, RuntimeError) as exc:
            failures.append({'attempt': index+1, 'reason': str(exc)})
            continue
        result = candidate[0]
        if result['matched_points'] < 10:
            failures.append({'attempt': index+1, 'reason': '有效对应点不足 10'})
            continue
        result.update(algorithm='algorithm_2_ppf_icp', ppf_votes=pose['votes'], search_attempt=index+1)
        duplicate = next((i for i, item in enumerate(results)
                          if same_pose(item[0], result, center, merge_mm)), None)
        if duplicate is None:
            results.append(candidate)
        elif rank(candidate) < rank(results[duplicate]):
            results[duplicate] = candidate
        results.sort(key=rank)
        results = results[:count]
    for index, (result, _, _) in enumerate(results):
        result['candidate_id'] = index+1
    return results, {
        'algorithm': 'algorithm_2_ppf_icp', 'requested_count': count, 'returned_count': len(results),
        'attempts': min(len(poses), attempts), 'ppf_pose_count': len(poses), 'refine_limit': attempts,
        'failed_attempts': failures, 'elapsed_seconds': time.perf_counter()-start,
        'model_points': len(model), 'scene_points': len(target),
        'model_voxel_mm': model_voxel, 'scene_voxel_mm': target_voxel,
        'normal_orientation': 'towards_camera_origin', 'ppf_model_sampling': 0.04,
        'ppf_distance_step': 0.05, 'ppf_angle_bins': 30, 'ppf_scene_sampling': 0.2,
        'ppf_scene_distance': 0.04, 'merge_translation_mm': merge_mm, 'merge_rotation_deg': 3.0,
        'ranking': 'coverage_desc_then_rmse_asc',
        'note': 'PPF 投票数不是正确概率。法线朝相机原点定向；模板和场景应保留原相机坐标，适合单视角相近拍摄方向。'}
