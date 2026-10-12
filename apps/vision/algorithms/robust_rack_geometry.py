"""Deterministic, robust plane estimation in camera millimetres."""
import numpy as np

FIT_VERSION = 'robust_irls_plane_v2'


def robust_plane(points, threshold_mm=5.0, min_points=50, iterations=256,
                 expected_normal=None, normal_tolerance_deg=10.0, max_search_points=6000):
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < min_points:
        raise ValueError('有效点不足，无法拟合平面')
    if not np.isfinite(threshold_mm) or threshold_mm <= 0:
        raise ValueError('平面阈值必须为正数')
    points = points[np.lexsort((points[:, 2], points[:, 1], points[:, 0]))]
    pivot = np.median(points, axis=0)
    local = points - pivot
    sample = local[np.linspace(0, len(local)-1, min(max_search_points, len(local)), dtype=int)]
    center = sample.mean(0)
    eigenvalues, vectors = np.linalg.eigh((sample-center).T @ (sample-center))
    if eigenvalues[1] <= max(eigenvalues[-1], 1.) * 1e-10:
        raise ValueError('点云退化为直线，无法拟合平面')
    normal = vectors[:, 0]
    offset = -normal @ center
    def score(n, d):
        residual = np.abs(sample @ n + d)
        # Truncated squared loss breaks ties using the whole support, not the RNG order.
        return (int(np.count_nonzero(residual < threshold_mm)),
                -float(np.minimum(residual**2, threshold_mm**2).sum()))
    best_score = score(normal, offset)
    reference = None
    if expected_normal is not None:
        reference = np.asarray(expected_normal, dtype=float)
        if not np.isfinite(reference).all() or np.linalg.norm(reference) < 1e-8:
            raise ValueError('参考法向量无效')
        reference = reference / np.linalg.norm(reference)
    def matches(n):
        return reference is not None and abs(n @ reference) >= np.cos(np.deg2rad(normal_tolerance_deg))
    preferred = (best_score, normal.copy(), offset) if matches(normal) else None
    rng = np.random.default_rng(42)
    for _ in range(iterations):
        a, b, c = sample[rng.choice(len(sample), 3, replace=False)]
        u, v = b-a, c-a
        cross = np.cross(u, v)
        length = np.linalg.norm(cross)
        if length < .05 * np.linalg.norm(u) * np.linalg.norm(v) or length < 1e-8:
            continue
        n = cross/length
        d = -n @ a
        candidate_score = score(n, d)
        if candidate_score > best_score:
            normal, offset, best_score = n, d, candidate_score
        if matches(n) and (preferred is None or candidate_score > preferred[0]):
            preferred = (candidate_score, n, d)
    if preferred is not None and preferred[0][0] >= .8 * best_score[0]:
        best_score, normal, offset = preferred
    if best_score[0] < max(3, int(.15*len(sample))):
        raise ValueError('没有足够一致的平面点')
    # Re-estimate support on all points; center coordinates avoid long-range cancellation.
    for _ in range(12):
        residual = local @ normal + offset
        mask = np.abs(residual) < threshold_mm
        if mask.sum() < min_points:
            raise ValueError('平面内点不足')
        selected = local[mask]
        errors = residual[mask]
        sigma = max(.1, 1.4826*np.median(np.abs(errors-np.median(errors))))
        cutoff = min(threshold_mm, max(.5, 4.685*sigma))
        weights = np.maximum(0, 1-(errors/cutoff)**2)**2
        if np.count_nonzero(weights) < min_points:
            raise ValueError('鲁棒精拟合内点不足')
        center = np.average(selected, axis=0, weights=weights)
        centered = selected-center
        eig, vec = np.linalg.eigh((centered*weights[:, None]).T @ centered / weights.sum())
        if eig[1] <= max(eig[-1], 1.) * 1e-10:
            raise ValueError('平面内点退化为直线')
        updated = vec[:, 0]
        if updated @ normal < 0:
            updated = -updated
        d = -updated @ center
        change = np.linalg.norm(updated-normal) + abs(d-offset)
        normal, offset = updated, d
        if change < 1e-8:
            break
    # A stable sign convention preserves the plane equation as a pair (n,d).
    if normal[np.argmax(np.abs(normal))] < 0:
        normal, offset = -normal, -offset
    residual = local @ normal + offset
    mask = np.abs(residual) < threshold_mm
    inliers = points[mask]
    centroid = center+pivot
    warnings = []
    if mask.mean() < .5:
        warnings.append(f'内点比例 {mask.mean()*100:.1f}%，ROI 可能包含多个表面')
    if eig[0] / max(eig[1], 1e-12) > .1:
        warnings.append('平面有效宽度不足或表面不平整，法向量可能不稳定')
    return {'normal':normal.tolist(), 'offset':float(offset-normal@pivot),
            'centroid':centroid.tolist(), 'inlier_ratio':float(mask.mean()),
            'inlier_count':int(mask.sum()), 'total_points':len(points),
            'rms_mm':float(np.sqrt(np.mean(residual[mask]**2))),
            'eigenvalue_ratio':float(eig[0]/max(eig[1],1e-12)),
            'fit_version':FIT_VERSION, 'threshold_mm':float(threshold_mm),
            'quality_warnings':warnings}, inliers
