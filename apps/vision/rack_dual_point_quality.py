"""Depth-first forensics and measured acceptance statistics; no field limits guessed."""
import numpy as np

from .algorithms.rack_dual_point import number, require
from .algorithms.robust_rack_geometry import robust_plane
from .vision_result_validator import crop_space


def _line3d(points, config):
    threshold = number(config['lineRansacMm'], 'lineRansacMm')
    minimum = max(3, int(number(config['min_points'], 'min_points')))
    require(len(points) >= minimum, 'INSUFFICIENT_DEPTH', 'forensics', '三维线拟合有效点不足')
    sample = points[np.linspace(0, len(points)-1, min(5000, len(points)), dtype=int)]
    rng = np.random.default_rng(42)
    best, score = None, -1
    for _ in range(int(number(config['iterations'], 'iterations'))):
        a, b = sample[rng.choice(len(sample), 2, replace=False)]
        delta = b-a
        if np.linalg.norm(delta) < 1e-8:
            continue
        direction = delta/np.linalg.norm(delta)
        error = np.linalg.norm(np.cross(sample-a, direction), axis=1)
        mask = error <= threshold
        if mask.sum() > score:
            best, score = (a, direction), int(mask.sum())
    require(best is not None, 'LINE3D_FAILED', 'forensics', '三维线退化')
    center, direction = best
    for _ in range(3):
        errors = np.linalg.norm(np.cross(points-center, direction), axis=1)
        mask = errors <= threshold
        require(mask.sum() >= minimum, 'LINE3D_FAILED', 'forensics', '三维线内点不足')
        center = points[mask].mean(0)
        _, _, vectors = np.linalg.svd(points[mask]-center, full_matrices=False)
        direction = vectors[0]
    errors = np.linalg.norm(np.cross(points-center, direction), axis=1)
    mask = errors <= threshold
    require(mask.sum() >= minimum, 'LINE3D_FAILED', 'forensics', '三维线精拟合内点不足')
    return {'point': center.tolist(), 'direction': direction.tolist(), 'inlier_count': int(mask.sum()),
            'inlier_ratio': float(mask.mean()), 'rms_mm': float(np.sqrt(np.mean(errors[mask]**2))),
            'span_mm': float(np.ptp((points[mask]-center) @ direction))}


def cloud_forensics(cloud, unit, regions=None):
    """Requires no image, grey edge, intrinsics or hand-eye calibration.

    Grid cells refer to array storage, NOT verified camera pixels. Geometry
    claims are local to user-specified 3D regions; scene-wide plane fit is not
    interpreted as evidence about a rack member.
    """
    data = np.asarray(cloud)
    require(data.ndim in (2, 3) and data.shape[-1] == 3 and data.size > 0,
            'CLOUD_SHAPE', 'forensics', '点云必须为 N×3 或 H×W×3')
    valid = np.isfinite(data).all(axis=-1) & np.any(data != 0, axis=-1)
    result = {'stage': 'before_2d', 'shape': list(data.shape), 'dtype': str(data.dtype),
              'total_points': int(valid.size), 'valid_points': int(valid.sum()),
              'valid_ratio': float(valid.mean()), 'invalid_ratio': float(1-valid.mean()),
              'production_ready': False, 'regions': {}, 'unit': unit,
              'note': '有效率不能单独区分黑色反光、遮挡、曝光或配准问题；需现场曝光/载荷对照实验'}
    if data.ndim == 3:
        ys, xs = np.array_split(np.arange(data.shape[0]), min(8, data.shape[0])), np.array_split(np.arange(data.shape[1]), min(8, data.shape[1]))
        result['array_tile_valid_ratio'] = [[float(valid[np.ix_(y, x)].mean()) for x in xs] for y in ys]
        result['tile_coordinates'] = 'array_indices_not_verified_image_registration'
    if unit not in ('mm', 'm'):
        return {**result, 'geometry_blocker': '单位未确认，仅输出原始有效率，未猜测毫米比例'}
    mm = np.asarray(data, float)*(1000 if unit == 'm' else 1)
    points = mm[valid]
    result['xyz_percentiles_mm'] = np.percentile(points, [1, 50, 99], axis=0).tolist() if len(points) else None
    if not regions:
        result['geometry_blocker'] = '尚未指定目标横杆三维取证区域；全场景统计不能证明横杆可测'
    for name, region in (regions or {}).items():
        p = crop_space(mm, region['boundsMm'], positive_depth=False)
        metrics = {'valid_points': len(p), 'bounds_mm': region['boundsMm']}
        if len(p) >= 3:
            eigenvalues = np.linalg.eigvalsh(np.cov(p.T))
            metrics['covariance_eigenvalues_mm2'] = eigenvalues.tolist()
        for model in ('plane', 'line'):
            try:
                if model == 'plane':
                    fit, _ = robust_plane(p, threshold_mm=number(region['planeRansacMm'], 'planeRansacMm'),
                        min_points=max(3, int(number(region['min_points'], 'min_points'))),
                        iterations=int(number(region['iterations'], 'iterations')))
                else:
                    fit = _line3d(p, region)
                metrics[model] = {'fit_available': True, **fit}
            except ValueError as exc:
                metrics[model] = {'fit_available': False, 'reason': str(exc)}
        metrics['acceptance'] = 'diagnostic_only_requires_repeat_captures_and_physical_identity'
        result['regions'][name] = metrics
    return result


def repeatability(records, *, min_frames, target_three_sigma_mm):
    """N independent captures of a fixed rack; rejected frames remain in counts."""
    minimum = max(2, int(number(min_frames, 'min_frames')))
    target = np.broadcast_to(np.asarray(target_three_sigma_mm, float), (2, 3))
    require(np.isfinite(target).all() and np.all(target > 0), 'INVALID_CONFIG', 'acceptance', '3σ 目标无效')
    accepted, seen, rejected, context = [], set(), 0, None
    for row in records:
        signature = tuple(row.get(k) for k in ('condition_id', 'config_digest', 'calibration_digest', 'robot_frame'))
        require(all(signature) and (context is None or signature == context),
                'MIXED_STUDY_CONDITIONS', 'acceptance', '固定架统计必须使用相同载荷/工况、算法配置、标定和机器人坐标系')
        context = signature
        frame_id = row.get('frame_id')
        require(bool(frame_id) and frame_id not in seen, 'REPEATED_FRAME', 'acceptance', '每个重复性样本必须来自独立采集帧，禁止同帧复算冒充重复拍照')
        seen.add(frame_id)
        if row.get('success') is not True:
            rejected += 1
            continue
        points = np.asarray(row['robot_points'], float)
        require(points.shape == (2, 3) and np.isfinite(points).all(), 'INVALID_INPUT', 'acceptance', '重复性记录需要有限双点 XYZ')
        accepted.append(points)
    result = {'total_frames': len(records), 'accepted_frames': len(accepted), 'rejected_frames': rejected,
              'failure_rate': rejected/len(records) if records else None, 'target_three_sigma_mm': target.tolist(),
              'production_accepted': False, 'enough_frames': len(accepted) >= minimum}
    if len(accepted) < minimum:
        return {**result, 'reason': '独立有效采集帧不足'}
    data = np.asarray(accepted)
    sigma = data.std(axis=0, ddof=1)
    return {**result, 'mean_mm': data.mean(0).tolist(), 'sigma_mm': sigma.tolist(),
            'three_sigma_mm': (3*sigma).tolist(), 'peak_to_peak_mm': np.ptp(data, axis=0).tolist(),
            'within_exploratory_target': (3*sigma <= target).tolist(),
            'note': '3σ 衡量波动，不证明绝对准确度或现场验收通过；另需偏倚、工艺限值与 GR&R'}


def crossed_grr(values, tolerance_mm):
    """Balanced crossed random-effects ANOVA, interaction retained (no pooling).

    Shape: part × operator/setup × repeat × P1/P2 × XYZ. Negative estimated
    variance components are truncated at zero. %Tolerance uses 6*sigma/width.
    https://support.minitab.com/en-us/minitab/help-and-how-to/quality-and-process-improvement/measurement-system-analysis/how-to/gage-study/crossed-gage-r-r-study/methods-and-formulas/gage-r-r-table/
    """
    v = np.asarray(values, float)
    require(v.ndim == 5 and v.shape[-2:] == (2, 3) and min(v.shape[:3]) >= 2 and np.isfinite(v).all(),
            'INVALID_GRR_DESIGN', 'acceptance', 'GR&R 需要完整均衡的零件×操作者/重装×重复×2×3 数据，禁止丢弃缺测格')
    tolerance = np.broadcast_to(np.asarray(tolerance_mm, float), (2, 3))
    require(np.isfinite(tolerance).all() and np.all(tolerance > 0), 'INVALID_CONFIG', 'acceptance', 'GR&R 公差必须为正的 USL-LSL 全宽')
    p, o, r = v.shape[:3]
    cell = v.mean(2)
    parts, operators, grand = cell.mean(1), cell.mean(0), cell.mean((0, 1))
    mse = ((v-cell[:, :, None])**2).sum((0, 1, 2))/(p*o*(r-1))
    msi = r*((cell-parts[:, None]-operators[None]+grand)**2).sum((0, 1))/((p-1)*(o-1))
    mso = p*r*((operators-grand)**2).sum(0)/(o-1)
    msp = o*r*((parts-grand)**2).sum(0)/(p-1)
    interaction = np.maximum(0, (msi-mse)/r)
    operator = np.maximum(0, (mso-msi)/(p*r))
    part = np.maximum(0, (msp-msi)/(o*r))
    grr = np.sqrt(mse+operator+interaction)
    return {'method': 'balanced_crossed_anova_interaction_retained', 'design': [p, o, r],
            'repeatability_variance_mm2': mse.tolist(), 'operator_variance_mm2': operator.tolist(),
            'interaction_variance_mm2': interaction.tolist(), 'part_variance_mm2': part.tolist(),
            'grr_sigma_mm': grr.tolist(), 'grr_percent_tolerance': (600*grr/tolerance).tolist(),
            'tolerance_width_mm': tolerance.tolist(), 'production_accepted': False,
            'note': '点估计，未计算置信区间或自动剔除交互项；需要经认可的研究设计和现场验收限值'}


def acceptance_report(study):
    """Explicit limits + traceable study; no defaults can declare acceptance."""
    limits = study['acceptance']
    repeat = repeatability(study['repeatability_records'], min_frames=limits['minFrames'],
                           target_three_sigma_mm=limits['exploratoryThreeSigmaMm'])
    grr = crossed_grr(study['grr_values'], limits['toleranceWidthMm']) if 'grr_values' in study else None
    result = {'repeatability': repeat, 'grr': grr, 'production_accepted': False,
              'scope': 'measurement_system_statistics_only_not_PLC_release'}
    required = ('maxThreeSigmaMm', 'maxGrrPercentTolerance', 'maxFailureRate')
    if not limits.get('verified') or not limits.get('evidence') or any(limits.get(k) is None for k in required) or grr is None:
        return {**result, 'reason': '验收限值尚未现场确认，或缺少 GR&R 实测数据'}
    sigma_limit = np.broadcast_to(np.asarray(limits['maxThreeSigmaMm'], float), (2, 3))
    grr_limit = np.broadcast_to(np.asarray(limits['maxGrrPercentTolerance'], float), (2, 3))
    failure_limit = float(limits['maxFailureRate'])
    require(np.isfinite(sigma_limit).all() and np.all(sigma_limit > 0) and np.isfinite(grr_limit).all()
            and np.all(grr_limit > 0) and np.isfinite(failure_limit) and 0 <= failure_limit <= 1,
            'INVALID_CONFIG', 'acceptance', '量化验收限值无效')
    within = (repeat['enough_frames'] and np.all(np.asarray(repeat['three_sigma_mm']) <= sigma_limit)
              and np.all(np.asarray(grr['grr_percent_tolerance']) <= grr_limit)
              and repeat['failure_rate'] <= failure_limit)
    # Statistics alone do not prove physical identity, accuracy or robot behavior.
    return {**result, 'statistical_limits_passed': bool(within), 'limits_evidence': limits['evidence']}
