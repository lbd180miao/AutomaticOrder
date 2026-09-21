"""Deterministic geometric localisation in robot coordinates (mm)."""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, peak_widths

from .config import load_config, quality_score
from .exceptions import RackPositioningErrorCode as EC, PositioningAlgorithmError


class PositioningAlgorithm:
    MIN_PLANE_POINTS = 10
    MIN_EDGE_POINTS = 5
    MIN_PILLAR_POINTS = 5

    def __init__(self, config=None):
        self.config = load_config(config)

    @staticmethod
    def _points(cloud, minimum, code):
        pts = np.asarray(cloud, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 3 or not np.isfinite(pts).all():
            raise PositioningAlgorithmError(EC.POINTCLOUD_INVALID, '点云必须为有限 N×3 数组')
        if len(pts) < minimum:
            raise PositioningAlgorithmError(code, f'ROI 点数不足: {len(pts)} < {minimum}',
                                            {'point_count': len(pts)})
        return pts

    def detect_support_plane(self, pointcloud, ransac_threshold=None,
                             max_iterations=None, reference_xy=None):
        pts = self._points(pointcloud, self.MIN_PLANE_POINTS, EC.ROI_INSUFFICIENT_POINTS)
        c = self.config
        threshold = c['ransac_threshold_mm'] if ransac_threshold is None else ransac_threshold
        iterations = c['ransac_iterations'] if max_iterations is None else max_iterations
        expected = np.asarray(c['expected_normal'], dtype=float)
        expected /= np.linalg.norm(expected)
        cosine = np.cos(np.deg2rad(c['max_normal_angle_deg']))
        rng = np.random.default_rng(c['seed'])
        best, best_key = None, (-1, -np.inf)
        # One backend and a local RNG, independent of Open3D/global RNG state.
        for _ in range(iterations):
            p = pts[rng.choice(len(pts), 3, replace=False)]
            normal = np.cross(p[1] - p[0], p[2] - p[0])
            norm = np.linalg.norm(normal)
            if norm < 1e-9:
                continue
            normal /= norm
            if abs(normal @ expected) < cosine:
                continue
            distance = np.abs((pts - p[0]) @ normal)
            indices = np.flatnonzero(distance <= threshold)
            key = (len(indices), -float(np.mean(distance[indices] ** 2)))
            if key > best_key:
                best, best_key = indices, key
        if best is None or len(best) < self.MIN_PLANE_POINTS:
            raise PositioningAlgorithmError(EC.RANSAC_FAILED, '未找到满足法向先验的支撑面',
                                            {'point_count': len(pts), 'expected_normal': expected.tolist()})
        sample = pts[best]
        weights = np.ones(len(sample))
        for _ in range(5):
            center = np.average(sample, axis=0, weights=weights)
            _, singular, vh = np.linalg.svd((sample - center) * np.sqrt(weights[:, None]), full_matrices=False)
            if singular[1] < 1e-8:
                raise PositioningAlgorithmError(EC.RANSAC_FAILED, '支撑面退化为直线或点')
            normal = vh[-1]
            if normal @ expected < 0:
                normal = -normal
            residual = (sample - center) @ normal
            scale = max(float(np.median(np.abs(residual))) * 1.4826, 0.05)
            weights = np.minimum(1.0, 1.345 * scale / np.maximum(np.abs(residual), 1e-12))
        d = -float(normal @ center)
        residual = pts @ normal + d
        inliers = np.flatnonzero(np.abs(residual) <= threshold)
        rms = float(np.sqrt(np.mean(residual[inliers] ** 2))) if len(inliers) else float(threshold)
        angle = float(np.rad2deg(np.arccos(np.clip(normal @ expected, -1, 1))))
        ratio = len(inliers) / len(pts)
        metrics = {'normal': normal.tolist(), 'plane_model': [*normal.tolist(), d],
                   'plane_rms_mm': rms, 'normal_angle_deg': angle, 'inlier_ratio': ratio,
                   'inlier_count': len(inliers), 'point_count': len(pts)}
        if len(inliers) < self.MIN_PLANE_POINTS or angle > c['max_normal_angle_deg'] or rms > c['max_plane_rms_mm'] or ratio < c['min_inlier_ratio'] or abs(normal[2]) < 1e-6:
            raise PositioningAlgorithmError(EC.PLANE_FIT_LOW_QUALITY, '支撑面质量超差', metrics)
        xy = np.asarray(reference_xy if reference_xy is not None else (pts[:, :2].min(0) + pts[:, :2].max(0)) / 2, dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise PositioningAlgorithmError(EC.INVALID_PARAMETERS, '参考 XY 必须为有限二维坐标')
        scores = {'inlier_ratio': ratio,
                  'flatness': 1 / (1 + (rms / c['max_plane_rms_mm']) ** 2),
                  'normal': 1 / (1 + (angle / c['max_normal_angle_deg']) ** 2)}
        return {**metrics, 'z_actual': float(-(normal[:2] @ xy + d) / normal[2]),
                'z_std': float(np.std(pts[inliers, 2])), 'reference_xy': xy.tolist(),
                'quality_scores': scores, 'confidence': quality_score(scores)}

    def _projection(self, pointcloud, axis, role, code):
        pts = self._points(pointcloud, 5, code)
        c = self.config
        values = pts[:, axis]
        step = c['projection_bin_mm']
        padding = max(4, int(np.ceil(c['max_peak_width_mm'] / step)))
        start = np.floor(values.min() / step) * step - padding * step
        count = int(np.ceil((values.max() - start) / step)) + padding + 1
        if count > 100000:
            raise PositioningAlgorithmError(code, '投影范围过大，请检查单位和 ROI')
        bins = start + np.arange(count + 1) * step
        hist, _ = np.histogram(values, bins=bins)
        smooth = gaussian_filter1d(hist.astype(float), c['projection_smoothing_mm'] / step, mode='constant')
        peaks, _ = find_peaks(smooth)
        background = max(float(np.median(smooth)), 1.0)
        widths = peak_widths(smooth, peaks, rel_height=0.5)[0] * step if len(peaks) else []
        candidates = []
        for peak, width in zip(peaks, widths):
            ratio = float(smooth[peak] / background)
            center = float((bins[peak] + bins[peak + 1]) / 2)
            radius = max(float(width) / 2, step)
            selected = np.abs(values - center) <= radius
            fraction = float(selected.mean())
            if ratio >= c['min_peak_ratio'] and width <= c['max_peak_width_mm'] and fraction >= c['min_peak_fraction']:
                left, mid, right = smooth[peak-1:peak+2]
                denominator = left - 2 * mid + right
                delta = float(np.clip(0.5 * (left-right) / denominator, -0.5, 0.5)) if denominator < -1e-12 else 0.0
                candidates.append({'coordinate_mm': center + delta * step,
                                   'peak_ratio': ratio, 'peak_width_mm': float(width),
                                   'point_fraction': fraction, 'height': float(mid)})
        details = {'point_count': len(pts), 'background': background,
                   'peaks': candidates, 'bin_mm': step, 'method': 'smoothed_projection'}
        if not candidates:
            raise PositioningAlgorithmError(code, '无显著且宽度合格的投影峰', details)
        if role == 'edge':
            chosen = [candidates[0 if c['edge_direction'] == 'min' else -1]]
        elif c['pillar_mode'] == 'double':
            if len(candidates) != 2:
                raise PositioningAlgorithmError(code, '双峰立柱必须恰有两个显著峰', details)
            chosen = candidates
        else:
            if len(candidates) != 1:
                raise PositioningAlgorithmError(code, '立柱存在多个显著峰，中心不唯一', details)
            chosen = candidates
        coordinate = float(np.mean([p['coordinate_mm'] for p in chosen]))
        ratio = min(p['peak_ratio'] for p in chosen)
        width = max(p['peak_width_mm'] for p in chosen)
        scores = {'prominence': min(1.0, ratio / c['target_peak_ratio']),
                  'width': 1 / (1 + (width / c['max_peak_width_mm']) ** 2)}
        name = 'y' if axis == 1 else 'x'
        return {**details, f'{name}_actual': coordinate, f'{name}_std': float(np.std(values)),
                f'{role}_points_count': len(pts), 'selected_peaks': chosen,
                'peak_ratio': ratio, 'peak_width_mm': width,
                'quality_scores': scores, 'confidence': quality_score(scores)}

    def detect_front_edge(self, pointcloud):
        return self._projection(pointcloud, 1, 'edge', EC.EDGE_DETECTION_FAILED)

    def detect_pillar(self, pointcloud):
        return self._projection(pointcloud, 0, 'pillar', EC.PILLAR_DETECTION_FAILED)
