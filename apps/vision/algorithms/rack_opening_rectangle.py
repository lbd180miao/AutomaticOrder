"""Rectangle-opening location for the V2 3D rack locator.

The module deliberately has no Django dependency.  It accepts points that are
already expressed in the required coordinate system, reconstructs the four
physical opening corners, derives the centre, and fits the standard-to-actual
rigid transform.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import math
from typing import Any

import cv2
import numpy as np


ALGORITHM_VERSION = 'RECTANGLE_CORNERS_V2'
AUTO_ALGORITHM_VERSION = 'RECTANGLE_CORNERS_AUTO_V2'
LEGACY_ALGORITHM_VERSION = 'MEDIAN_V1'
POINT_KEYS = ('p1', 'p2', 'p3', 'p4')


class RectangleLocationError(ValueError):
    """Expected V2 location failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def get_algorithm_version(reference_feature_config: dict | None) -> str:
    config = reference_feature_config or {}
    return str(config.get('algorithm_version') or LEGACY_ALGORITHM_VERSION).upper()


def is_rectangle_v2(reference_feature_config: dict | None) -> bool:
    return get_algorithm_version(reference_feature_config) == ALGORITHM_VERSION


def is_rectangle_result(algorithm_version: Any) -> bool:
    return str(algorithm_version or '').upper() in {
        ALGORITHM_VERSION, AUTO_ALGORITHM_VERSION,
    }


def _as_point(value: Any, name: str) -> np.ndarray:
    if not isinstance(value, dict):
        raise RectangleLocationError(
            'REFERENCE_GEOMETRY_NOT_CONFIGURED',
            f'标准点 {name.upper()} 未配置',
        )
    try:
        point = np.asarray([value['x'], value['y'], value['z']], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        raise RectangleLocationError(
            'REFERENCE_GEOMETRY_NOT_CONFIGURED',
            f'标准点 {name.upper()} 必须包含有效的 x/y/z',
        ) from exc
    if not np.isfinite(point).all():
        raise RectangleLocationError(
            'REFERENCE_GEOMETRY_NOT_CONFIGURED',
            f'标准点 {name.upper()} 包含无效数值',
        )
    return point


def _unit(vector: np.ndarray, *, code: str = 'RECTANGLE_CONSTRAINT_FAILED') -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length <= 1e-9:
        raise RectangleLocationError(code, '矩形轴长度为零，无法建立局部坐标系')
    return vector / length


def _point_dict(point: np.ndarray, **extra) -> dict:
    result = {
        'x': round(float(point[0]), 4),
        'y': round(float(point[1]), 4),
        'z': round(float(point[2]), 4),
    }
    result.update(extra)
    return result


def standard_geometry(reference_feature_config: dict | None) -> dict:
    """Validate V2 standard points and recompute all derived geometry."""
    config = reference_feature_config or {}
    opening = config.get('opening_rectangle') or {}
    points_config = opening.get('standard_points') or {}
    points = np.vstack([_as_point(points_config.get(key), key) for key in POINT_KEYS])

    p1, p2, p3, p4 = points
    width_top = float(np.linalg.norm(p2 - p1))
    width_bottom = float(np.linalg.norm(p3 - p4))
    height_left = float(np.linalg.norm(p1 - p4))
    height_right = float(np.linalg.norm(p2 - p3))
    width = (width_top + width_bottom) / 2.0
    height = (height_left + height_right) / 2.0
    if width <= 1e-6 or height <= 1e-6:
        raise RectangleLocationError(
            'REFERENCE_GEOMETRY_NOT_CONFIGURED',
            '标准四点不能构成有效矩形',
        )

    x_axis = _unit(((p2 - p1) + (p3 - p4)) / 2.0, code='REFERENCE_GEOMETRY_NOT_CONFIGURED')
    z_raw = ((p1 - p4) + (p2 - p3)) / 2.0
    z_axis = _unit(z_raw - np.dot(z_raw, x_axis) * x_axis, code='REFERENCE_GEOMETRY_NOT_CONFIGURED')
    normal_out = _unit(np.cross(x_axis, z_axis), code='REFERENCE_GEOMETRY_NOT_CONFIGURED')
    y_axis_in = -normal_out
    center = points.mean(axis=0)

    diagonal_error = float(np.linalg.norm((p1 + p3) / 2.0 - (p2 + p4) / 2.0))
    opposite_width_error = abs(width_top - width_bottom)
    opposite_height_error = abs(height_left - height_right)
    default_reference_tolerance = max(2.0, min(width, height) * 0.01)
    reference_tolerance = float(opening.get('reference_rectangle_tolerance_mm', default_reference_tolerance))
    if max(diagonal_error, opposite_width_error, opposite_height_error) > reference_tolerance:
        raise RectangleLocationError(
            'REFERENCE_GEOMETRY_NOT_CONFIGURED',
            '标准四点不满足矩形一致性要求',
            {
                'diagonal_midpoint_error_mm': diagonal_error,
                'opposite_width_error_mm': opposite_width_error,
                'opposite_height_error_mm': opposite_height_error,
                'tolerance_mm': reference_tolerance,
            },
        )

    return {
        'points_array': points,
        'points': {key: _point_dict(points[index]) for index, key in enumerate(POINT_KEYS)},
        'center_array': center,
        'center': _point_dict(center),
        'width_mm': width,
        'height_mm': height,
        'x_axis': x_axis,
        'y_axis_in': y_axis_in,
        'z_axis': z_axis,
        'normal_out': normal_out,
        'thresholds': dict(opening.get('thresholds') or {}),
        'coordinate_system': str(opening.get('coordinate_system') or 'robot_base'),
    }


def normalize_reference_feature_config(reference_feature_config: dict | None) -> dict:
    """Return a server-normalized V2 config; legacy configs pass through."""
    config = deepcopy(reference_feature_config or {})
    if not is_rectangle_v2(config):
        return config
    geometry = standard_geometry(config)
    opening = dict(config.get('opening_rectangle') or {})
    opening.update({
        'point_order': [
            'P1_TOP_LEFT', 'P2_TOP_RIGHT', 'P3_BOTTOM_RIGHT', 'P4_BOTTOM_LEFT',
        ],
        'coordinate_system': geometry['coordinate_system'],
        'point_unit': 'mm',
        'standard_points': geometry['points'],
        'standard_center': geometry['center'],
        'standard_width_mm': round(geometry['width_mm'], 4),
        'standard_height_mm': round(geometry['height_mm'], 4),
        'standard_axes': {
            'x_axis': geometry['x_axis'].round(8).tolist(),
            'y_axis_in': geometry['y_axis_in'].round(8).tolist(),
            'z_axis': geometry['z_axis'].round(8).tolist(),
            'normal_out': geometry['normal_out'].round(8).tolist(),
        },
    })
    config['algorithm_version'] = ALGORITHM_VERSION
    config['opening_rectangle'] = opening
    return config


def _fit_plane_ransac(
    points: np.ndarray,
    threshold_mm: float,
    iterations: int,
    *,
    expected_center: np.ndarray | None = None,
    expected_normal: np.ndarray | None = None,
    max_normal_angle_deg: float = 15.0,
    max_reference_distance_mm: float = 100.0,
    min_candidate_inliers: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(points) < 3:
        raise RectangleLocationError('INSUFFICIENT_POINTS', '有效点数不足，无法拟合开口平面')

    rng = np.random.default_rng(20260722)
    best_mask = None
    best_count = 0
    best_rmse = float('inf')
    best_reference_distance = float('inf')
    for _ in range(max(20, int(iterations))):
        indices = rng.choice(len(points), size=3, replace=False)
        a, b, c = points[indices]
        normal = np.cross(b - a, c - a)
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-9:
            continue
        normal /= norm
        if expected_normal is not None:
            alignment = float(np.clip(abs(np.dot(normal, expected_normal)), 0.0, 1.0))
            normal_angle = math.degrees(math.acos(alignment))
            if normal_angle > max_normal_angle_deg:
                continue
        if expected_center is not None:
            reference_distance = abs(float(np.dot(expected_center - a, normal)))
            if reference_distance > max_reference_distance_mm:
                continue
        else:
            reference_distance = 0.0
        distances = np.abs((points - a) @ normal)
        mask = distances <= threshold_mm
        count = int(mask.sum())
        if count < max(3, int(min_candidate_inliers)):
            continue
        rmse = float(np.sqrt(np.mean(np.square(distances[mask]))))
        if expected_center is not None:
            better = (
                reference_distance < best_reference_distance - threshold_mm
                or (
                    abs(reference_distance - best_reference_distance) <= threshold_mm
                    and (count > best_count or (count == best_count and rmse < best_rmse))
                )
            )
        else:
            better = count > best_count or (count == best_count and rmse < best_rmse)
        if better:
            best_mask = mask
            best_count = count
            best_rmse = rmse
            best_reference_distance = reference_distance

    if best_mask is None:
        raise RectangleLocationError('OPENING_PLANE_NOT_FOUND', '未找到稳定的开口前平面')

    inliers = points[best_mask]
    center = inliers.mean(axis=0)
    _, _, vt = np.linalg.svd(inliers - center, full_matrices=False)
    normal = _unit(vt[-1])
    distances = np.abs((points - center) @ normal)
    refined_mask = distances <= threshold_mm
    refined = points[refined_mask]
    if len(refined) >= 3:
        center = refined.mean(axis=0)
        _, _, vt = np.linalg.svd(refined - center, full_matrices=False)
        normal = _unit(vt[-1])
        distances = np.abs((points - center) @ normal)
        refined_mask = distances <= threshold_mm
    return center, normal, refined_mask


def _internal_opening_boundary_mask(pixel_coordinates: np.ndarray, margin_px: int) -> np.ndarray:
    """Find a closed hole inside the fitted front-plane pixel mask.

    A target ROI crop itself also creates an outer point-cloud boundary.  Only
    contours with a parent (holes inside the plane mask) are accepted here, so
    the ROI rectangle cannot be reported as P1-P4.
    """
    pixels = np.rint(np.asarray(pixel_coordinates, dtype=float)).astype(int)
    if pixels.ndim != 2 or pixels.shape[1] != 2 or len(pixels) < 4:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '缺少有效的像素拓扑，无法确认实体开口边缘')
    min_xy = pixels.min(axis=0)
    local = pixels - min_xy
    width = int(local[:, 0].max()) + 1
    height = int(local[:, 1].max()) + 1
    if width < 5 or height < 5:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '开口像素区域过小')

    mask = np.zeros((height, width), dtype=np.uint8)
    mask[local[:, 1], local[:, 0]] = 255
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '前平面内未检测到闭合开口轮廓')

    candidates = []
    for index, contour in enumerate(contours):
        parent = int(hierarchy[0][index][3])
        if parent < 0:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if (
            x <= margin_px or y <= margin_px
            or x + w >= width - margin_px or y + h >= height - margin_px
        ):
            continue
        area = abs(float(cv2.contourArea(contour)))
        if area > 0:
            candidates.append((area, contour))
    if not candidates:
        raise RectangleLocationError(
            'RECTANGLE_CONSTRAINT_FAILED',
            '未找到ROI内部的实体开口轮廓；已拒绝使用ROI裁剪边界作为四角点',
        )

    _, contour = max(candidates, key=lambda item: item[0])
    contour_mask = np.zeros_like(mask)
    cv2.drawContours(contour_mask, [contour], -1, 255, 2)
    return contour_mask[local[:, 1], local[:, 0]] > 0


def _pixel_line_record(line: np.ndarray) -> dict:
    x1, y1, x2, y2 = np.asarray(line, dtype=float)
    length = float(math.hypot(x2 - x1, y2 - y1))
    if length <= 1e-6:
        raise ValueError('zero length line')
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
    coefficients = np.asarray([y1 - y2, x2 - x1, x1 * y2 - x2 * y1], dtype=float)
    coefficients /= math.hypot(coefficients[0], coefficients[1])
    return {
        'line': np.asarray([x1, y1, x2, y2], dtype=float),
        'length': length,
        'angle': angle,
        'coefficients': coefficients,
    }


def _pixel_line_angle_difference(first: float, second: float) -> float:
    difference = abs(float(first) - float(second)) % 180.0
    return min(difference, 180.0 - difference)


def _pixel_line_y(line: dict, x: float) -> float:
    a, b, c = line['coefficients']
    return float(-(a * x + c) / b) if abs(b) > 1e-9 else float('inf')


def _pixel_line_x(line: dict, y: float) -> float:
    a, b, c = line['coefficients']
    return float(-(b * y + c) / a) if abs(a) > 1e-9 else float('inf')


def _pixel_line_intersection(first: dict, second: dict) -> np.ndarray:
    homogeneous = np.cross(first['coefficients'], second['coefficients'])
    if abs(homogeneous[2]) <= 1e-9:
        return np.asarray([float('nan'), float('nan')])
    return homogeneous[:2] / homogeneous[2]


def _segment_pixel_support(edge_image: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    mask = np.zeros_like(edge_image, dtype=np.uint8)
    cv2.line(
        mask,
        tuple(np.rint(start).astype(int)),
        tuple(np.rint(end).astype(int)),
        255,
        5,
    )
    pixel_count = int(np.count_nonzero(mask))
    if pixel_count <= 0:
        return 0.0
    return float(np.count_nonzero((mask > 0) & (edge_image > 0)) / pixel_count)


def _detect_opening_quad_from_depth(
    depth_values: np.ndarray,
    pixel_coordinates: np.ndarray,
    *,
    min_area_ratio: float,
) -> tuple[np.ndarray, dict]:
    """Detect four physical depth edges inside the ROI.

    The ROI is only a search window.  Its crop boundary is never inserted into
    the edge image, so the returned quadrilateral must be supported by depth
    discontinuities in the captured data.
    """
    depths = np.asarray(depth_values, dtype=float).reshape(-1)
    pixels = np.asarray(pixel_coordinates, dtype=float)
    valid = (
        np.isfinite(depths) & (depths > 1e-6)
        & np.isfinite(pixels).all(axis=1)
    )
    depths = depths[valid]
    pixels = np.rint(pixels[valid]).astype(int)
    if len(depths) < 50:
        raise RectangleLocationError('INSUFFICIENT_POINTS', 'ROI 内有效深度点不足，无法自动提取四边')
    roi_min_xy = pixels.min(axis=0)
    roi_max_xy = pixels.max(axis=0)
    depth_median = float(np.median(depths))
    depth_floor, depth_ceiling = np.quantile(depths, [0.005, 0.9995])
    if depth_median > 0:
        depth_floor = max(float(depth_floor), depth_median * 0.20)
        depth_ceiling = depth_median * 2.10
    robust_depth = (depths >= depth_floor) & (depths <= depth_ceiling)
    depths = depths[robust_depth]
    pixels = pixels[robust_depth]

    min_xy = roi_min_xy
    local = pixels - min_xy
    width = int(roi_max_xy[0] - roi_min_xy[0]) + 1
    height = int(roi_max_xy[1] - roi_min_xy[1]) + 1
    if width < 20 or height < 20 or width * height > 20_000_000:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', 'ROI 像素范围无效，无法自动提取四边')

    depth_image = np.full((height, width), np.nan, dtype=np.float32)
    depth_image[local[:, 1], local[:, 0]] = depths.astype(np.float32)
    finite = np.isfinite(depth_image) & (depth_image > 1e-6)
    if int(finite.sum()) < 50:
        raise RectangleLocationError('INSUFFICIENT_POINTS', 'ROI 内有效深度像素不足')
    low, high = np.quantile(depth_image[finite], [0.02, 0.98])
    if not np.isfinite(low) or not np.isfinite(high) or high - low <= 1e-6:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', 'ROI 深度变化不足，未检测到实体四边')

    normalized = np.zeros((height, width), dtype=np.uint8)
    normalized[finite] = np.clip(
        (depth_image[finite] - low) * 255.0 / (high - low), 0.0, 255.0,
    ).astype(np.uint8)
    missing = (~finite).astype(np.uint8) * 255
    filled = cv2.inpaint(normalized, missing, 5, cv2.INPAINT_NS)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(filled)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 90)

    # 对水平和垂直方向分别用各自的长度作为基准，避免 ROI 呈横条形时垂直线被过小的 minLineLength 过滤掉
    min_h_dim = max(width, height)    # 水平线长度基准用宽度
    min_v_dim = max(height, width)    # 垂直线长度基准用高度
    hough = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 360.0,
        threshold=max(15, int(min(width, height) * 0.08)),
        minLineLength=max(18, int(min(width, height) * 0.10)),
        maxLineGap=max(12, int(min(width, height) * 0.12)),
    )
    if hough is None:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', 'ROI 内未检测到稳定的实体边线，请确保 ROI 包住料架开口四边')

    records = []
    for raw_line in hough[:, 0]:
        try:
            records.append(_pixel_line_record(raw_line))
        except ValueError:
            continue
    horizontal = sorted(
        [line for line in records if min(line['angle'], 180.0 - line['angle']) <= 25.0],
        key=lambda item: item['length'], reverse=True,
    )[:35]
    vertical = sorted(
        [line for line in records if 55.0 <= line['angle'] <= 125.0],
        key=lambda item: item['length'], reverse=True,
    )[:25]
    if len(horizontal) < 2 or len(vertical) < 2:
        h_cnt, v_cnt = len(horizontal), len(vertical)
        missing = []
        if h_cnt < 2: missing.append(f'水平线不足(当前{h_cnt}条，需≥2）')
        if v_cnt < 2: missing.append(f'垂直线不足(当前{v_cnt}条，需≥2）')
        raise RectangleLocationError(
            'RECTANGLE_CONSTRAINT_FAILED',
            f'ROI 内{"|".join(missing)}。请重新画 ROI：框住整个开口(包含上下左右四条边线)，勿画成细长横条',
            {'horizontal_line_count': h_cnt, 'vertical_line_count': v_cnt},
        )

    horizontal_pairs = []
    for first, second in combinations(horizontal, 2):
        first_y = _pixel_line_y(first, width / 2.0)
        second_y = _pixel_line_y(second, width / 2.0)
        if first_y > second_y:
            first, second, first_y, second_y = second, first, second_y, first_y
        separation = second_y - first_y
        if (
            _pixel_line_angle_difference(first['angle'], second['angle']) <= 15.0
            and separation >= 0.25 * height           # 放宽：原 0.35
            and -0.20 * height <= first_y <= 0.60 * height  # 放宽
            and 0.40 * height <= second_y <= 1.20 * height  # 放宽
        ):
            horizontal_pairs.append((first, second))

    vertical_pairs = []
    for first, second in combinations(vertical, 2):
        first_x = _pixel_line_x(first, height / 2.0)
        second_x = _pixel_line_x(second, height / 2.0)
        if first_x > second_x:
            first, second, first_x, second_x = second, first, second_x, first_x
        separation = second_x - first_x
        if (
            _pixel_line_angle_difference(first['angle'], second['angle']) <= 30.0
            and separation >= 0.30 * width           # 放宽：原 0.45
            and -0.20 * width <= first_x <= 0.55 * width   # 放宽左边界
            and 0.40 * width <= second_x <= 1.20 * width   # 放宽右边界
        ):
            vertical_pairs.append((first, second))

    candidates = []
    roi_area = float(width * height)
    for top, bottom in horizontal_pairs:
        for left, right in vertical_pairs:
            quad = np.vstack([
                _pixel_line_intersection(top, left),
                _pixel_line_intersection(top, right),
                _pixel_line_intersection(bottom, right),
                _pixel_line_intersection(bottom, left),
            ])
            if not np.isfinite(quad).all():
                continue
            if (
                (quad[:, 0] < -0.12 * width).any() or (quad[:, 0] > 1.12 * width).any()
                or (quad[:, 1] < -0.12 * height).any() or (quad[:, 1] > 1.12 * height).any()
            ):
                continue
            area_ratio = abs(float(cv2.contourArea(quad.astype(np.float32)))) / roi_area
            if area_ratio < float(min_area_ratio) or area_ratio > 1.05:
                continue
            supports = [
                _segment_pixel_support(edges, quad[index], quad[(index + 1) % 4])
                for index in range(4)
            ]
            support = float(np.mean(supports))
            parallel_score = 1.0 - (
                _pixel_line_angle_difference(top['angle'], bottom['angle']) / 12.0
                + _pixel_line_angle_difference(left['angle'], right['angle']) / 25.0
            ) / 2.0
            length_score = min(
                1.0,
                sum(line['length'] for line in (top, right, bottom, left))
                / max(2.0 * (width + height), 1.0),
            )
            score = 0.50 * area_ratio + 0.30 * support + 0.10 * parallel_score + 0.10 * length_score
            candidates.append((score, quad, area_ratio, supports))

    if not candidates:
        raise RectangleLocationError(
            'RECTANGLE_CONSTRAINT_FAILED',
            '检测到了深度边线，但无法组成稳定的开口四边形；请让 ROI 包住完整四边',
        )
    score, local_quad, area_ratio, supports = max(candidates, key=lambda item: item[0])
    global_quad = local_quad + min_xy
    return global_quad, {
        'quad_score': round(float(score), 4),
        'quad_area_ratio': round(float(area_ratio), 4),
        'edge_support_ratio': [round(float(value), 4) for value in supports],
        'edge_pixel_count': int(np.count_nonzero(edges)),
        'roi_pixel_bounds': {
            'x': int(min_xy[0]), 'y': int(min_xy[1]),
            'w': int(width), 'h': int(height),
        },
    }


def _distance_to_pixel_segment(pixels: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    direction = end - start
    length_squared = float(np.dot(direction, direction))
    if length_squared <= 1e-9:
        return np.linalg.norm(pixels - start, axis=1)
    amount = np.clip(((pixels - start) @ direction) / length_squared, 0.0, 1.0)
    nearest = start + amount[:, None] * direction
    return np.linalg.norm(pixels - nearest, axis=1)


def _fit_balanced_edge_plane(
    camera_points: np.ndarray,
    pixel_coordinates: np.ndarray,
    quad_pixels: np.ndarray,
    *,
    edge_band_px: float,
    threshold_mm: float,
    iterations: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    point_groups = []
    for index in range(4):
        distances = _distance_to_pixel_segment(
            pixel_coordinates, quad_pixels[index], quad_pixels[(index + 1) % 4],
        )
        point_groups.append(np.flatnonzero(distances <= edge_band_px))
    if any(len(group) < 10 for group in point_groups):
        raise RectangleLocationError(
            'RECTANGLE_CONSTRAINT_FAILED',
            '四边附近的有效 3D 点不足，无法还原角点坐标',
            {'edge_point_count': [int(len(group)) for group in point_groups]},
        )

    edge_points = np.vstack([camera_points[group] for group in point_groups])
    labels = np.concatenate([
        np.full(len(group), index, dtype=int) for index, group in enumerate(point_groups)
    ])
    group_sizes = np.asarray([len(group) for group in point_groups], dtype=float)
    rng = np.random.default_rng(20260722)
    best = None
    for _ in range(max(200, int(iterations))):
        sample = rng.choice(len(edge_points), size=3, replace=False)
        a, b, c = edge_points[sample]
        normal = np.cross(b - a, c - a)
        normal_length = float(np.linalg.norm(normal))
        if normal_length <= 1e-9:
            continue
        normal /= normal_length
        distances = np.abs((edge_points - a) @ normal)
        mask = distances <= threshold_mm
        counts = np.bincount(labels[mask], minlength=4)
        ratios = counts / group_sizes
        score = float(5.0 * ratios.min() + ratios.mean() + 0.1 * mask.mean())
        if best is None or score > best[0]:
            best = (score, mask)
    if best is None:
        raise RectangleLocationError('OPENING_PLANE_NOT_FOUND', '四条实体边无法共同拟合前平面')

    inliers = edge_points[best[1]]
    center = inliers.mean(axis=0)
    _, _, vt = np.linalg.svd(inliers - center, full_matrices=False)
    normal = _unit(vt[-1])
    distances = np.abs((edge_points - center) @ normal)
    inlier_mask = distances <= threshold_mm
    inliers = edge_points[inlier_mask]
    if len(inliers) >= 3:
        center = inliers.mean(axis=0)
        _, _, vt = np.linalg.svd(inliers - center, full_matrices=False)
        normal = _unit(vt[-1])
        distances = np.abs((edge_points - center) @ normal)
        inlier_mask = distances <= threshold_mm
    edge_counts = np.bincount(labels[inlier_mask], minlength=4)
    return center, normal, edge_points, labels, inlier_mask


def _estimate_camera_rays(camera_points: np.ndarray, pixels: np.ndarray, query_pixels: np.ndarray) -> np.ndarray:
    z = camera_points[:, 2]
    valid = np.isfinite(camera_points).all(axis=1) & np.isfinite(pixels).all(axis=1) & (np.abs(z) > 1e-6)
    if int(valid.sum()) < 20:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '无法从点云恢复相机射线')
    points = camera_points[valid]
    image_points = pixels[valid]
    design_x = np.column_stack((image_points[:, 0], np.ones(len(image_points))))
    design_y = np.column_stack((image_points[:, 1], np.ones(len(image_points))))
    coefficient_x = np.linalg.lstsq(design_x, points[:, 0] / points[:, 2], rcond=None)[0]
    coefficient_y = np.linalg.lstsq(design_y, points[:, 1] / points[:, 2], rcond=None)[0]
    return np.column_stack((
        coefficient_x[0] * query_pixels[:, 0] + coefficient_x[1],
        coefficient_y[0] * query_pixels[:, 1] + coefficient_y[1],
        np.ones(len(query_pixels)),
    ))


def _camera_to_output_points(
    camera_points: np.ndarray,
    output_points: np.ndarray,
    query_points: np.ndarray,
) -> np.ndarray:
    design = np.column_stack((camera_points, np.ones(len(camera_points))))
    coefficients = np.linalg.lstsq(design, output_points, rcond=None)[0]
    return np.column_stack((query_points, np.ones(len(query_points)))) @ coefficients


def _line_metrics(points_2d: np.ndarray, start: np.ndarray, end: np.ndarray, band_mm: float) -> dict:
    direction = _unit(end - start)
    length = float(np.linalg.norm(end - start))
    rel = points_2d - start
    along = rel @ direction
    perpendicular = np.abs(rel[:, 0] * direction[1] - rel[:, 1] * direction[0])
    mask = (along >= -band_mm) & (along <= length + band_mm) & (perpendicular <= band_mm)
    selected = points_2d[mask]
    if len(selected) >= 2:
        centroid = selected.mean(axis=0)
        _, _, vt = np.linalg.svd(selected - centroid, full_matrices=False)
        fitted_direction = vt[0]
        if float(np.dot(fitted_direction, direction)) < 0:
            fitted_direction = -fitted_direction
        fitted_distances = np.abs(
            (selected[:, 0] - centroid[0]) * fitted_direction[1]
            - (selected[:, 1] - centroid[1]) * fitted_direction[0]
        )
        rmse = float(np.sqrt(np.mean(np.square(fitted_distances))))
    else:
        fitted_direction = direction
        rmse = float('inf')
    return {
        'count': int(mask.sum()),
        'rmse_mm': rmse,
        'direction': fitted_direction,
    }


def _fit_line_ransac_2d(
    points: np.ndarray,
    *,
    threshold_mm: float,
    iterations: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, float, np.ndarray]:
    """用 RANSAC 在 2D 平面内拟合一条直线，返回 (单位法向量 n, 截距 d, 内点掩码).

    直线方程: n · p = d，n 是单位法向量，d 是原点到直线的有符号距离。
    避免用斜率表示避免垂直线奇点。
    """
    if len(points) < 2:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '边缘候选点不足，无法拟合直线')

    best_mask: np.ndarray | None = None
    best_count = 0
    best_rmse = float('inf')

    for _ in range(max(30, int(iterations))):
        indices = rng.choice(len(points), size=2, replace=False)
        a, b = points[indices]
        diff = b - a
        diff_len = float(np.linalg.norm(diff))
        if diff_len < 1e-9:
            continue
        normal = np.array([-diff[1], diff[0]]) / diff_len  # 单位法向量
        d = float(normal @ a)
        distances = np.abs(points @ normal - d)
        mask = distances <= threshold_mm
        count = int(mask.sum())
        if count > best_count or (count == best_count and float(np.sqrt(np.mean(np.square(distances[mask])))) < best_rmse):
            best_count = count
            best_mask = mask
            best_rmse = float(np.sqrt(np.mean(np.square(distances[mask])))) if count > 0 else float('inf')

    if best_mask is None or best_count < 2:
        raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', 'RANSAC未能找到有效直线内点')

    # 用所有内点做最小二乘精化
    selected = points[best_mask]
    centroid = selected.mean(axis=0)
    _, _, vt = np.linalg.svd(selected - centroid, full_matrices=False)
    line_dir = vt[0]  # 直线方向
    normal = np.array([-line_dir[1], line_dir[0]])  # 法向量
    d = float(normal @ centroid)
    distances = np.abs(points @ normal - d)
    refined_mask = distances <= threshold_mm
    return normal, d, refined_mask


def _classify_edge_points_2d(
    projected: np.ndarray,
    *,
    std_width: float,
    std_height: float,
    margin_ratio: float = 0.25,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """将2D投影点分配到上/右/下/左四条边的候选区域.

    u轴（水平）= 标准 x_axis 方向，v轴（竖直）= 标准 z_axis 方向。
    按距离各边最近且在边中央区段范围内进行分组。

    返回 (top_mask, right_mask, bottom_mask, left_mask)。
    """
    u = projected[:, 0]
    v = projected[:, 1]
    half_w = std_width / 2.0
    half_h = std_height / 2.0
    edge_margin = margin_ratio * min(std_width, std_height)

    # 各边距离
    dist_top    = np.abs(v - half_h)
    dist_bottom = np.abs(v + half_h)
    dist_right  = np.abs(u - half_w)
    dist_left   = np.abs(u + half_w)

    # 每个点到四条边的最小距离，属于最近的那条边
    all_dist = np.column_stack((dist_top, dist_right, dist_bottom, dist_left))
    nearest = np.argmin(all_dist, axis=1)

    # 额外要求：点必须在该边的中央 margin 带内（避免跨角点的点干扰）
    in_horizontal_span = (u >= -half_w - edge_margin) & (u <= half_w + edge_margin)
    in_vertical_span   = (v >= -half_h - edge_margin) & (v <= half_h + edge_margin)

    top_mask    = (nearest == 0) & in_horizontal_span
    right_mask  = (nearest == 1) & in_vertical_span
    bottom_mask = (nearest == 2) & in_horizontal_span
    left_mask   = (nearest == 3) & in_vertical_span

    return top_mask, right_mask, bottom_mask, left_mask


def _line_intersection_2d(n1: np.ndarray, d1: float, n2: np.ndarray, d2: float) -> np.ndarray:
    """求两条直线 n1·p=d1 与 n2·p=d2 的交点."""
    mat = np.column_stack((n1, n2)).T  # 2x2
    rhs = np.array([d1, d2])
    det = float(n1[0] * n2[1] - n1[1] * n2[0])
    if abs(det) < 1e-9:
        return np.array([float('nan'), float('nan')])
    # Cramer's rule
    x = (d1 * n2[1] - d2 * n1[1]) / det
    y = (n1[0] * d2 - n2[0] * d1) / det
    return np.array([x, y])


def _rectangle_constraint_refine(
    top: tuple[np.ndarray, float],
    right: tuple[np.ndarray, float],
    bottom: tuple[np.ndarray, float],
    left: tuple[np.ndarray, float],
    *,
    top_centroid: np.ndarray,
    right_centroid: np.ndarray,
    bottom_centroid: np.ndarray,
    left_centroid: np.ndarray,
) -> tuple[tuple[np.ndarray, float], tuple[np.ndarray, float], tuple[np.ndarray, float], tuple[np.ndarray, float]]:
    """对四条独立拟合的直线施加矩形约束：上下平行、左右平行、相邻垂直.

    策略（可靠版）：
    1. 从每组点的质心重新计算截距 d = n · centroid，确保符号与组的几何位置一致
    2. 上下法向量平均得到统一的水平法向量 n_h（方向朝向使 top 截距更大）
    3. 左右法向量平均并正交化得到统一的竖直法向量 n_v
    4. 使用统一法向量重新计算各边截距（保持截距=n·centroid）
    """
    n_top, _ = top
    n_right, _ = right
    n_bottom, _ = bottom
    n_left, _ = left

    # 步骤1：用各组质心重新计算截距，保证 d = n · centroid 的符号可靠
    # （RANSAC 的截距可能因法向量随机方向而符号不定）
    d_top    = float(n_top    @ top_centroid)
    d_right  = float(n_right  @ right_centroid)
    d_bottom = float(n_bottom @ bottom_centroid)
    d_left   = float(n_left   @ left_centroid)

    # 步骤2：确保 top 和 bottom 的法向量指向同一大致方向（v+ 方向）
    # top 的质心 v 值应 > bottom 的质心 v 值，因此 top 截距在法向量朝 v+ 时更大
    # 先统一让 n_top 朝向使 d_top > 0 的方向（top 组的 v > 0）
    v_top    = float(top_centroid[1])
    v_bottom = float(bottom_centroid[1])
    u_right  = float(right_centroid[0])
    u_left   = float(left_centroid[0])

    # 若 top 质心 v > 0（上方），法向量应能使 d = n·c 为正，即 n 朝向 v+
    # 若当前 d_top < 0，说明 n_top 方向反了，翻转
    if v_top > 0 and d_top < 0:
        n_top, d_top = -n_top, -d_top
    elif v_top < 0 and d_top > 0:
        n_top, d_top = -n_top, -d_top

    if v_bottom < 0 and d_bottom < 0:
        n_bottom, d_bottom = -n_bottom, -d_bottom
    elif v_bottom > 0 and d_bottom > 0:
        # bottom 在上方（v>0），d 应为正方向，保持
        pass

    # 确保 n_top 和 n_bottom 方向相同（都指向 v 方向），以便平均
    if float(n_top @ n_bottom) < 0:
        n_bottom, d_bottom = -n_bottom, -d_bottom

    if u_right > 0 and d_right < 0:
        n_right, d_right = -n_right, -d_right
    elif u_right < 0 and d_right > 0:
        n_right, d_right = -n_right, -d_right

    if u_left < 0 and d_left < 0:
        n_left, d_left = -n_left, -d_left
    elif u_left > 0 and d_left > 0:
        pass

    # 确保 n_right 和 n_left 方向相同（都指向 u 方向），以便平均
    if float(n_right @ n_left) < 0:
        n_left, d_left = -n_left, -d_left

    # 步骤3：上下平均法向量 n_h，左右平均法向量 n_v
    n_h = n_top + n_bottom
    nh_len = float(np.linalg.norm(n_h))
    if nh_len < 1e-9:
        n_h = np.array([0.0, 1.0])
    else:
        n_h = n_h / nh_len

    n_v = n_right + n_left
    nv_len = float(np.linalg.norm(n_v))
    if nv_len < 1e-9:
        n_v = np.array([1.0, 0.0])
    else:
        n_v = n_v / nv_len

    # 步骤4：正交化：去掉 n_v 中平行于 n_h 的分量
    n_v = n_v - float(n_v @ n_h) * n_h
    nv_len = float(np.linalg.norm(n_v))
    if nv_len < 1e-9:
        n_v = np.array([-n_h[1], n_h[0]])
    else:
        n_v = n_v / nv_len

    # 步骤5：用统一法向量重新计算各边截距（保证直线过各组质心）
    d_top_new    = float(n_h @ top_centroid)
    d_bottom_new = float(n_h @ bottom_centroid)
    d_right_new  = float(n_v @ right_centroid)
    d_left_new   = float(n_v @ left_centroid)

    return (n_h, d_top_new), (n_v, d_right_new), (n_h, d_bottom_new), (n_v, d_left_new)




def _angle_between_deg(a: np.ndarray, b: np.ndarray, *, parallel: bool) -> float:
    cosine = float(np.clip(abs(np.dot(_unit(a), _unit(b))), 0.0, 1.0))
    angle = math.degrees(math.acos(cosine))
    return angle if parallel else abs(90.0 - angle)


def _kabsch(standard: np.ndarray, actual: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    standard_center = standard.mean(axis=0)
    actual_center = actual.mean(axis=0)
    covariance = (standard - standard_center).T @ (actual - actual_center)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    translation = actual_center - rotation @ standard_center
    fitted = (rotation @ standard.T).T + translation
    residuals = np.linalg.norm(actual - fitted, axis=1)
    return rotation, translation, residuals


def _matrix(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


class RackOpeningRectangleLocator:
    """Fit one regular rectangular rack opening and return P1 through P5."""

    DEFAULT_THRESHOLDS = {
        'min_valid_points': 200,
        'min_plane_inliers': 200,
        'min_edge_points': 30,
        'plane_inlier_threshold_mm': 3.0,
        'plane_rmse_mm': 2.0,
        'edge_band_mm': 6.0,
        'edge_rmse_mm': 2.0,
        'parallel_angle_deg': 2.0,
        'perpendicular_angle_deg': 3.0,
        'center_consistency_mm': 2.0,
        'rigid_fit_max_residual_mm': 3.0,
        'width_tolerance_mm': 20.0,
        'height_tolerance_mm': 20.0,
        'ransac_iterations': 240,
        'trim_quantile': 0.01,
        'max_plane_normal_angle_deg': 15.0,
        'max_reference_plane_distance_mm': 100.0,
        'require_pixel_edge_evidence': True,
        'roi_boundary_margin_px': 2,
        'auto_plane_inlier_threshold_mm': 30.0,
        'auto_plane_rmse_mm': 30.0,
        'auto_edge_band_px': 7.0,
        'auto_ransac_iterations': 1200,
        'auto_min_quad_area_ratio': 0.06,   # 降低：适应小ROI或仅覆盖开口局部的情况
        'auto_min_edge_support_ratio': 0.05,
        'auto_parallel_angle_deg': 8.0,
        'auto_perpendicular_angle_deg': 15.0,
        'auto_center_consistency_mm': 60.0,
        'auto_rectangle_fit_max_residual_mm': 300.0,
    }

    def locate_auto(
        self,
        points: np.ndarray,
        reference_feature_config: dict | None = None,
        *,
        camera_points: np.ndarray,
        depth_values: np.ndarray,
        coordinate_system: str = 'robot_base',
        pixel_coordinates: np.ndarray,
        confidence_threshold: float = 0.7,
    ) -> dict:
        """Extract P1-P5 from the ROI itself; standard P1-P4 are optional."""
        cloud = np.asarray(points, dtype=float)
        camera_cloud = np.asarray(camera_points, dtype=float)
        pixels = np.asarray(pixel_coordinates, dtype=float)
        depths = np.asarray(depth_values, dtype=float).reshape(-1)
        if (
            cloud.ndim != 2 or cloud.shape[1] != 3
            or camera_cloud.shape != cloud.shape
            or pixels.shape != (len(cloud), 2)
            or depths.shape != (len(cloud),)
        ):
            raise RectangleLocationError(
                'RECTANGLE_CONSTRAINT_FAILED',
                'ROI 自动四角点需要一一对应的点云、深度值和像素坐标',
            )
        valid = (
            np.isfinite(cloud).all(axis=1)
            & np.isfinite(camera_cloud).all(axis=1)
            & np.isfinite(pixels).all(axis=1)
            & np.isfinite(depths)
            & (np.abs(depths) > 1e-6)
            & (np.max(np.abs(camera_cloud), axis=1) < 1e7)
        )
        cloud = cloud[valid]
        camera_cloud = camera_cloud[valid]
        pixels = pixels[valid]
        depths = depths[valid]

        opening_config = (reference_feature_config or {}).get('opening_rectangle') or {}
        thresholds = {**self.DEFAULT_THRESHOLDS, **dict(opening_config.get('thresholds') or {})}
        if len(cloud) < int(thresholds['min_valid_points']):
            raise RectangleLocationError(
                'INSUFFICIENT_POINTS',
                f"ROI 内有效点数不足: {len(cloud)} < {int(thresholds['min_valid_points'])}",
            )

        quad_pixels, quad_metrics = _detect_opening_quad_from_depth(
            depths,
            pixels,
            min_area_ratio=float(thresholds['auto_min_quad_area_ratio']),
        )
        plane_center_camera, plane_normal_camera, edge_camera_points, edge_labels, plane_mask = (
            _fit_balanced_edge_plane(
                camera_cloud,
                pixels,
                quad_pixels,
                edge_band_px=float(thresholds['auto_edge_band_px']),
                threshold_mm=float(thresholds['auto_plane_inlier_threshold_mm']),
                iterations=int(thresholds['auto_ransac_iterations']),
            )
        )
        plane_inliers_camera = edge_camera_points[plane_mask]
        plane_distances = np.abs((plane_inliers_camera - plane_center_camera) @ plane_normal_camera)
        plane_rmse = float(np.sqrt(np.mean(np.square(plane_distances))))
        edge_counts_array = np.bincount(edge_labels[plane_mask], minlength=4)

        rays = _estimate_camera_rays(camera_cloud, pixels, quad_pixels)
        denominator = rays @ plane_normal_camera
        if (np.abs(denominator) <= 1e-7).any():
            raise RectangleLocationError('OPENING_PLANE_NOT_FOUND', '开口角点射线与前平面近似平行')
        distance = float(np.dot(plane_normal_camera, plane_center_camera))
        ray_scale = distance / denominator
        actual_camera = rays * ray_scale[:, None]
        if not np.isfinite(actual_camera).all() or (ray_scale <= 0).any():
            raise RectangleLocationError('OPENING_PLANE_NOT_FOUND', '开口前平面无法还原为有效 3D 角点')
        raw_actual = _camera_to_output_points(camera_cloud, cloud, actual_camera)
        raw_center = raw_actual.mean(axis=0)
        fitted_x_axis = _unit(((raw_actual[1] - raw_actual[0]) + (raw_actual[2] - raw_actual[3])) / 2.0)
        fitted_z_raw = ((raw_actual[0] - raw_actual[3]) + (raw_actual[1] - raw_actual[2])) / 2.0
        fitted_z_axis = _unit(fitted_z_raw - np.dot(fitted_z_raw, fitted_x_axis) * fitted_x_axis)
        fitted_width = (
            abs(float(np.dot(raw_actual[1] - raw_actual[0], fitted_x_axis)))
            + abs(float(np.dot(raw_actual[2] - raw_actual[3], fitted_x_axis)))
        ) / 2.0
        fitted_height = (
            abs(float(np.dot(raw_actual[0] - raw_actual[3], fitted_z_axis)))
            + abs(float(np.dot(raw_actual[1] - raw_actual[2], fitted_z_axis)))
        ) / 2.0
        actual = np.vstack([
            raw_center - fitted_x_axis * fitted_width / 2.0 + fitted_z_axis * fitted_height / 2.0,
            raw_center + fitted_x_axis * fitted_width / 2.0 + fitted_z_axis * fitted_height / 2.0,
            raw_center + fitted_x_axis * fitted_width / 2.0 - fitted_z_axis * fitted_height / 2.0,
            raw_center - fitted_x_axis * fitted_width / 2.0 - fitted_z_axis * fitted_height / 2.0,
        ])
        rectangle_fit_residuals = np.linalg.norm(raw_actual - actual, axis=1)
        rectangle_fit_rmse = float(np.sqrt(np.mean(np.square(rectangle_fit_residuals))))
        rectangle_fit_max_residual = float(rectangle_fit_residuals.max())
        p1, p2, p3, p4 = actual
        center = actual.mean(axis=0)

        edge_names = ('top', 'right', 'bottom', 'left')
        edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
        edge_counts = {
            name: int(edge_counts_array[index]) for index, name in enumerate(edge_names)
        }
        edge_rmse = {}
        for index, (name, (start_index, end_index)) in enumerate(zip(edge_names, edge_pairs)):
            selected_camera = edge_camera_points[plane_mask & (edge_labels == index)]
            if len(selected_camera) < 2:
                edge_rmse[name] = None
                continue
            selected = _camera_to_output_points(camera_cloud, cloud, selected_camera)
            start = actual[start_index]
            direction = _unit(actual[end_index] - start)
            residual = selected - start
            perpendicular = residual - (residual @ direction)[:, None] * direction
            edge_rmse[name] = float(np.sqrt(np.mean(np.sum(np.square(perpendicular), axis=1))))

        width_top = float(np.linalg.norm(p2 - p1))
        width_bottom = float(np.linalg.norm(p3 - p4))
        height_left = float(np.linalg.norm(p1 - p4))
        height_right = float(np.linalg.norm(p2 - p3))
        width = (width_top + width_bottom) / 2.0
        height = (height_left + height_right) / 2.0
        x_axis = _unit(((p2 - p1) + (p3 - p4)) / 2.0)
        z_raw = ((p1 - p4) + (p2 - p3)) / 2.0
        z_axis = _unit(z_raw - np.dot(z_raw, x_axis) * x_axis)
        normal_out = _unit(np.cross(x_axis, z_axis))
        y_axis_in = -normal_out

        top_direction = _unit(p2 - p1)
        right_direction = _unit(p3 - p2)
        bottom_direction = _unit(p3 - p4)
        left_direction = _unit(p4 - p1)
        parallel_error = max(
            _angle_between_deg(top_direction, bottom_direction, parallel=True),
            _angle_between_deg(left_direction, right_direction, parallel=True),
        )
        perpendicular_error = max(
            _angle_between_deg(first, second, parallel=False)
            for first, second in (
                (top_direction, right_direction),
                (right_direction, bottom_direction),
                (bottom_direction, left_direction),
                (left_direction, top_direction),
            )
        )
        center_consistency = float(np.linalg.norm((p1 + p3) / 2.0 - (p2 + p4) / 2.0))

        standard = None
        reference_error = ''
        standard_points = opening_config.get('standard_points') or {}
        has_standard = all(
            isinstance(standard_points.get(key), dict)
            and all(axis in standard_points[key] for axis in ('x', 'y', 'z'))
            for key in POINT_KEYS
        )
        if has_standard:
            try:
                standard = standard_geometry(reference_feature_config)
                if standard['coordinate_system'] != coordinate_system:
                    reference_error = (
                        f"标准四点使用{standard['coordinate_system']}，实际点使用{coordinate_system}，"
                        '已跳过标准偏差评估'
                    )
                    standard = None
            except RectangleLocationError as exc:
                reference_error = exc.message

        width_error = None
        height_error = None
        residuals = None
        rigid_rmse = None
        max_residual = None
        deviation = None
        correction = None
        if standard is not None:
            rotation, translation, residuals = _kabsch(standard['points_array'], actual)
            rigid_rmse = float(np.sqrt(np.mean(np.square(residuals))))
            max_residual = float(residuals.max())
            deviation = _matrix(rotation, translation)
            correction = np.linalg.inv(deviation)
            width_error = abs(width - standard['width_mm'])
            height_error = abs(height - standard['height_mm'])

        def score(value: float, limit: float) -> float:
            if not np.isfinite(value) or limit <= 0:
                return 0.0
            return max(0.0, min(1.0, 1.0 - value / (limit * 2.0)))

        plane_score = score(plane_rmse, float(thresholds['auto_plane_rmse_mm']))
        quad_score = min(1.0, float(quad_metrics['quad_score']) / 0.60)
        edge_support = float(np.mean(quad_metrics['edge_support_ratio']))
        support_score = min(1.0, edge_support / 0.12)
        coverage_score = min(1.0, float(edge_counts_array.min()) / max(float(thresholds['min_edge_points']) * 3.0, 1.0))
        geometry_score = min(
            score(parallel_error, float(thresholds['auto_parallel_angle_deg'])),
            score(perpendicular_error, float(thresholds['auto_perpendicular_angle_deg'])),
            score(center_consistency, float(thresholds['auto_center_consistency_mm'])),
            score(rectangle_fit_max_residual, float(thresholds['auto_rectangle_fit_max_residual_mm'])),
        )
        confidence = float(np.clip(
            0.20 * plane_score + 0.25 * quad_score + 0.20 * support_score
            + 0.20 * coverage_score + 0.15 * geometry_score,
            0.0,
            0.99,
        ))

        failures = []
        if plane_rmse > float(thresholds['auto_plane_rmse_mm']):
            failures.append(('OPENING_PLANE_NOT_FOUND', f'四边共同前平面 RMSE {plane_rmse:.2f}mm 超限'))
        if edge_support < float(thresholds['auto_min_edge_support_ratio']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'实体四边深度边缘支持率 {edge_support:.2%} 不足'))
        if parallel_error > float(thresholds['auto_parallel_angle_deg']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'对边平行误差 {parallel_error:.2f}° 超限'))
        if perpendicular_error > float(thresholds['auto_perpendicular_angle_deg']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'邻边垂直误差 {perpendicular_error:.2f}° 超限'))
        if center_consistency > float(thresholds['auto_center_consistency_mm']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'对角线中心误差 {center_consistency:.2f}mm 超限'))
        if rectangle_fit_max_residual > float(thresholds['auto_rectangle_fit_max_residual_mm']):
            failures.append((
                'RECTANGLE_CONSTRAINT_FAILED',
                f'规则矩形拟合最大角点修正量 {rectangle_fit_max_residual:.2f}mm 超限',
            ))
        if standard is not None:
            if width_error > float(thresholds['width_tolerance_mm']) or height_error > float(thresholds['height_tolerance_mm']):
                failures.append(('RECTANGLE_SIZE_OUT_OF_TOLERANCE', '开口宽度或高度超出标准公差'))
            if max_residual > float(thresholds['rigid_fit_max_residual_mm']):
                failures.append(('RIGID_FIT_RESIDUAL_TOO_HIGH', f'四角点刚体拟合残差 {max_residual:.2f}mm 超限'))
        if confidence < float(confidence_threshold):
            failures.append(('CORNER_CONFIDENCE_LOW', f'自动四角点置信度 {confidence:.2%} 不足'))

        pose_rotation = np.column_stack((x_axis, y_axis_in, z_axis))
        pose_matrix = _matrix(pose_rotation, center)
        point_confidence = round(confidence, 4)
        pixel_points = {
            key: {
                'x': round(float(quad_pixels[index, 0]), 2),
                'y': round(float(quad_pixels[index, 1]), 2),
            }
            for index, key in enumerate(POINT_KEYS)
        }
        pixel_points['p5'] = {
            'x': round(float(quad_pixels[:, 0].mean()), 2),
            'y': round(float(quad_pixels[:, 1].mean()), 2),
        }
        return {
            'algorithm_version': AUTO_ALGORITHM_VERSION,
            'extraction_mode': 'roi_depth_edges_auto',
            'reference_mode': 'standard_four_points' if standard is not None else 'roi_auto_only',
            'standard_geometry_configured': standard is not None,
            'reference_evaluation_error': reference_error,
            'coordinate_system': coordinate_system,
            'point_unit': 'mm',
            'points': {
                key: _point_dict(
                    point,
                    point_id=key.upper(),
                    confidence=point_confidence,
                    source='roi_depth_edge_and_front_plane',
                )
                for key, point in zip(POINT_KEYS, actual)
            },
            'center': _point_dict(center, point_id='P5', source='derived_from_p1_p4'),
            'geometry': {
                'width_mm': round(width, 4),
                'height_mm': round(height, 4),
                'width_top_mm': round(width_top, 4),
                'width_bottom_mm': round(width_bottom, 4),
                'height_left_mm': round(height_left, 4),
                'height_right_mm': round(height_right, 4),
                'x_axis': x_axis.round(8).tolist(),
                'y_axis_in': y_axis_in.round(8).tolist(),
                'z_axis': z_axis.round(8).tolist(),
                'normal_out': normal_out.round(8).tolist(),
            },
            'pose': {
                **_point_dict(center),
                'rz': round(math.degrees(math.atan2(x_axis[1], x_axis[0])), 4),
                'matrix': pose_matrix.round(8).tolist(),
            },
            'quality': {
                'valid_point_count': int(len(cloud)),
                'plane_inlier_count': int(plane_mask.sum()),
                'plane_inlier_ratio': round(float(plane_mask.sum() / len(cloud)), 4),
                'plane_rmse_mm': round(plane_rmse, 4),
                'edge_evidence_source': 'roi_depth_discontinuity_hough',
                'edge_point_count': edge_counts,
                'edge_rmse_mm': {
                    key: round(float(value), 4) if value is not None and np.isfinite(value) else None
                    for key, value in edge_rmse.items()
                },
                'edge_support_ratio': quad_metrics['edge_support_ratio'],
                'quad_score': quad_metrics['quad_score'],
                'quad_area_ratio': quad_metrics['quad_area_ratio'],
                'parallel_error_deg': round(parallel_error, 4),
                'perpendicular_error_deg': round(perpendicular_error, 4),
                'center_consistency_mm': round(center_consistency, 4),
                'rectangle_fit_rmse_mm': round(rectangle_fit_rmse, 4),
                'rectangle_fit_max_residual_mm': round(rectangle_fit_max_residual, 4),
                'width_error_mm': round(width_error, 4) if width_error is not None else None,
                'height_error_mm': round(height_error, 4) if height_error is not None else None,
                'corner_residuals_mm': [round(float(value), 4) for value in residuals] if residuals is not None else None,
                'mean_corner_residual_mm': round(float(residuals.mean()), 4) if residuals is not None else None,
                'max_corner_residual_mm': round(max_residual, 4) if max_residual is not None else None,
                'rigid_fit_rmse_mm': round(rigid_rmse, 4) if rigid_rmse is not None else None,
                'confidence': round(confidence, 4),
                'thresholds': thresholds,
                'failures': [{'code': code, 'message': message} for code, message in failures],
                'detector': quad_metrics,
            },
            'deviation_transform': {
                'meaning': 'standard_to_actual',
                'matrix': deviation.round(8).tolist(),
            } if deviation is not None else None,
            'correction_transform': {
                'meaning': 'actual_to_standard',
                'matrix': correction.round(8).tolist(),
            } if correction is not None else None,
            'pixel_points': pixel_points,
            'locate_ok': not failures,
            'error_code': failures[0][0] if failures else '',
            'error_message': '; '.join(message for _, message in failures),
        }

    def locate(
        self,
        points: np.ndarray,
        reference_feature_config: dict,
        *,
        coordinate_system: str = 'robot_base',
        pixel_coordinates: np.ndarray | None = None,
        confidence_threshold: float = 0.7,
    ) -> dict:
        standard = standard_geometry(reference_feature_config)
        expected_coordinate_system = standard['coordinate_system']
        if coordinate_system != expected_coordinate_system:
            raise RectangleLocationError(
                'COORDINATE_SYSTEM_INVALID',
                f'V2标准点使用{expected_coordinate_system}，当前点云为{coordinate_system}',
            )

        cloud = np.asarray(points, dtype=float)
        if cloud.ndim != 2 or cloud.shape[1] != 3:
            raise RectangleLocationError('INSUFFICIENT_POINTS', '点云必须是 N x 3')
        valid_mask = np.isfinite(cloud).all(axis=1) & (np.max(np.abs(cloud), axis=1) < 1e7)
        cloud = cloud[valid_mask]
        pixels = None
        if pixel_coordinates is not None:
            pixel_array = np.asarray(pixel_coordinates, dtype=float)
            if pixel_array.shape == (len(valid_mask), 2):
                pixels = pixel_array[valid_mask]

        thresholds = {**self.DEFAULT_THRESHOLDS, **standard['thresholds']}
        if len(cloud) < int(thresholds['min_valid_points']):
            raise RectangleLocationError(
                'INSUFFICIENT_POINTS',
                f"有效点数不足: {len(cloud)} < {int(thresholds['min_valid_points'])}",
            )

        plane_center, plane_normal, plane_mask = _fit_plane_ransac(
            cloud,
            float(thresholds['plane_inlier_threshold_mm']),
            int(thresholds['ransac_iterations']),
            expected_center=standard['center_array'],
            expected_normal=standard['normal_out'],
            max_normal_angle_deg=float(thresholds['max_plane_normal_angle_deg']),
            max_reference_distance_mm=float(thresholds['max_reference_plane_distance_mm']),
            min_candidate_inliers=int(thresholds['min_plane_inliers']),
        )
        plane_points = cloud[plane_mask]
        plane_pixels = pixels[plane_mask] if pixels is not None else None
        if len(plane_points) < int(thresholds['min_plane_inliers']):
            raise RectangleLocationError(
                'OPENING_PLANE_NOT_FOUND',
                f"开口平面内点不足: {len(plane_points)} < {int(thresholds['min_plane_inliers'])}",
            )
        if float(np.dot(plane_normal, standard['normal_out'])) < 0:
            plane_normal = -plane_normal
        plane_distances = np.abs((plane_points - plane_center) @ plane_normal)
        plane_rmse = float(np.sqrt(np.mean(np.square(plane_distances))))

        u_axis = standard['x_axis'] - np.dot(standard['x_axis'], plane_normal) * plane_normal
        u_axis = _unit(u_axis)
        v_axis = _unit(np.cross(plane_normal, u_axis))
        if float(np.dot(v_axis, standard['z_axis'])) < 0:
            v_axis = -v_axis
        projected = np.column_stack(((plane_points - plane_center) @ u_axis, (plane_points - plane_center) @ v_axis))

        require_pixel_edges = bool(thresholds['require_pixel_edge_evidence'])
        if plane_pixels is not None:
            boundary_mask = _internal_opening_boundary_mask(
                plane_pixels, int(thresholds['roi_boundary_margin_px']),
            )
            rectangle_input = projected[boundary_mask]
            edge_evidence_source = 'internal_front_plane_contour'
        elif require_pixel_edges:
            raise RectangleLocationError(
                'RECTANGLE_CONSTRAINT_FAILED',
                'V2缺少组织化点云像素拓扑，无法排除ROI边界伪装成实体边缘',
            )
        else:
            rectangle_input = projected
            edge_evidence_source = 'geometric_extent_fallback'

        trim_quantile = float(np.clip(thresholds['trim_quantile'], 0.0, 0.2))
        if trim_quantile > 0 and len(rectangle_input) >= 20:
            low = np.quantile(rectangle_input, trim_quantile, axis=0)
            high = np.quantile(rectangle_input, 1.0 - trim_quantile, axis=0)
            trim_mask = np.all((rectangle_input >= low) & (rectangle_input <= high), axis=1)
            rectangle_input = rectangle_input[trim_mask]
        if len(rectangle_input) < 4:
            raise RectangleLocationError('RECTANGLE_CONSTRAINT_FAILED', '用于矩形拟合的平面点不足')

        # ── 四边 RANSAC 直线拟合（文档第 6.6～6.8 节） ──────────────────────
        # 按标准宽高将2D投影点分配到上/右/下/左四组，分别拟合直线，再求交点。
        # 不使用 cv2.minAreaRect，避免最小外接矩形不等同于物理四边拟合交点。

        std_half_w = standard['width_mm'] / 2.0
        std_half_h = standard['height_mm'] / 2.0
        edge_threshold = float(thresholds.get('plane_inlier_threshold_mm', 3.0)) * 1.5
        ransac_iters = int(thresholds.get('ransac_iterations', 240))
        rng_2d = np.random.default_rng(20260722)

        top_mask, right_mask, bottom_mask, left_mask = _classify_edge_points_2d(
            rectangle_input,
            std_width=standard['width_mm'],
            std_height=standard['height_mm'],
        )
        edge_group_counts = {
            'top': int(top_mask.sum()),
            'right': int(right_mask.sum()),
            'bottom': int(bottom_mask.sum()),
            'left': int(left_mask.sum()),
        }
        missing_edges = [
            name for name, count in edge_group_counts.items()
            if count < max(4, int(thresholds.get('min_edge_points', 30)) // 4)
        ]
        if missing_edges:
            raise RectangleLocationError(
                'RECTANGLE_CONSTRAINT_FAILED',
                f"以下边的候选点不足，无法拟合直线: {', '.join(missing_edges)}",
                {'edge_group_counts': edge_group_counts},
            )

        try:
            n_top,    d_top,    inlier_top    = _fit_line_ransac_2d(rectangle_input[top_mask],    threshold_mm=edge_threshold, iterations=ransac_iters, rng=rng_2d)
            n_right,  d_right,  inlier_right  = _fit_line_ransac_2d(rectangle_input[right_mask],  threshold_mm=edge_threshold, iterations=ransac_iters, rng=rng_2d)
            n_bottom, d_bottom, inlier_bottom = _fit_line_ransac_2d(rectangle_input[bottom_mask], threshold_mm=edge_threshold, iterations=ransac_iters, rng=rng_2d)
            n_left,   d_left,   inlier_left   = _fit_line_ransac_2d(rectangle_input[left_mask],   threshold_mm=edge_threshold, iterations=ransac_iters, rng=rng_2d)
        except RectangleLocationError as exc:
            raise RectangleLocationError(
                exc.code, f'四边RANSAC直线拟合失败: {exc.message}', exc.details,
            ) from exc

        # 施加矩形约束：上下平行、左右平行、相邻垂直
        # 传入各组质心用于确定法向量方向和截距（比传标准轴更可靠）
        top_centroid    = rectangle_input[top_mask].mean(axis=0)
        right_centroid  = rectangle_input[right_mask].mean(axis=0)
        bottom_centroid = rectangle_input[bottom_mask].mean(axis=0)
        left_centroid   = rectangle_input[left_mask].mean(axis=0)
        (n_top, d_top), (n_right, d_right), (n_bottom, d_bottom), (n_left, d_left) = (
            _rectangle_constraint_refine(
                (n_top, d_top),
                (n_right, d_right),
                (n_bottom, d_bottom),
                (n_left, d_left),
                top_centroid=top_centroid,
                right_centroid=right_centroid,
                bottom_centroid=bottom_centroid,
                left_centroid=left_centroid,
            )
        )

        # 求四条直线的交点 → P1(左上) P2(右上) P3(右下) P4(左下)
        p1_2d = _line_intersection_2d(n_top, d_top, n_left, d_left)
        p2_2d = _line_intersection_2d(n_top, d_top, n_right, d_right)
        p3_2d = _line_intersection_2d(n_bottom, d_bottom, n_right, d_right)
        p4_2d = _line_intersection_2d(n_bottom, d_bottom, n_left, d_left)

        if not np.isfinite(np.vstack([p1_2d, p2_2d, p3_2d, p4_2d])).all():
            raise RectangleLocationError(
                'RECTANGLE_CONSTRAINT_FAILED',
                '四条边线近似平行，无法求出有效交点，请检查ROI内点云是否覆盖完整矩形四边',
            )

        ordered_2d = np.vstack([p1_2d, p2_2d, p3_2d, p4_2d])
        # 将2D交点转回3D机器人基坐标
        actual = np.vstack([
            plane_center + pt[0] * u_axis + pt[1] * v_axis
            for pt in ordered_2d
        ])
        p1, p2, p3, p4 = actual
        center = actual.mean(axis=0)

        # 记录各边内点集合，用于后续 edge_metrics 计算
        edge_inlier_masks = {
            'top':    top_mask,
            'right':  right_mask,
            'bottom': bottom_mask,
            'left':   left_mask,
        }

        edge_names = ('top', 'right', 'bottom', 'left')
        edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
        edge_metrics = {}
        for name, (a, b) in zip(edge_names, edge_pairs):
            edge_metrics[name] = _line_metrics(
                rectangle_input,
                ordered_2d[a],
                ordered_2d[b],
                float(thresholds['edge_band_mm']),
            )
        # 用各边的实际内点增强 RMSE（覆盖 _line_metrics 中可能的 inf）
        for name, mask in edge_inlier_masks.items():
            group_pts = rectangle_input[mask]
            if len(group_pts) >= 2 and not np.isfinite(edge_metrics[name]['rmse_mm']):
                centroid_g = group_pts.mean(axis=0)
                _, _, vt_g = np.linalg.svd(group_pts - centroid_g, full_matrices=False)
                dir_g = vt_g[0]
                perp_dist = np.abs(
                    (group_pts[:, 0] - centroid_g[0]) * dir_g[1]
                    - (group_pts[:, 1] - centroid_g[1]) * dir_g[0]
                )
                edge_metrics[name]['rmse_mm'] = float(np.sqrt(np.mean(np.square(perp_dist))))

        width_top = float(np.linalg.norm(p2 - p1))
        width_bottom = float(np.linalg.norm(p3 - p4))
        height_left = float(np.linalg.norm(p1 - p4))
        height_right = float(np.linalg.norm(p2 - p3))
        width = (width_top + width_bottom) / 2.0
        height = (height_left + height_right) / 2.0
        x_axis = _unit(((p2 - p1) + (p3 - p4)) / 2.0)
        z_raw = ((p1 - p4) + (p2 - p3)) / 2.0
        z_axis = _unit(z_raw - np.dot(z_raw, x_axis) * x_axis)
        normal_out = _unit(np.cross(x_axis, z_axis))
        if float(np.dot(normal_out, standard['normal_out'])) < 0:
            normal_out = -normal_out
        y_axis_in = -normal_out

        center_consistency = float(np.linalg.norm((p1 + p3) / 2.0 - (p2 + p4) / 2.0))
        parallel_error = max(
            _angle_between_deg(edge_metrics['top']['direction'], edge_metrics['bottom']['direction'], parallel=True),
            _angle_between_deg(edge_metrics['left']['direction'], edge_metrics['right']['direction'], parallel=True),
        )
        perpendicular_error = max(
            _angle_between_deg(edge_metrics[a]['direction'], edge_metrics[b]['direction'], parallel=False)
            for a, b in (('top', 'right'), ('right', 'bottom'), ('bottom', 'left'), ('left', 'top'))
        )

        rotation, translation, residuals = _kabsch(standard['points_array'], actual)
        rigid_rmse = float(np.sqrt(np.mean(np.square(residuals))))
        max_residual = float(residuals.max())
        deviation = _matrix(rotation, translation)
        correction = np.linalg.inv(deviation)

        edge_counts = {name: metric['count'] for name, metric in edge_metrics.items()}
        edge_rmse = {name: metric['rmse_mm'] for name, metric in edge_metrics.items()}
        finite_edge_rmse = [value for value in edge_rmse.values() if np.isfinite(value)]
        max_edge_rmse = max(finite_edge_rmse) if finite_edge_rmse else float('inf')
        width_error = abs(width - standard['width_mm'])
        height_error = abs(height - standard['height_mm'])

        def score(value: float, limit: float) -> float:
            """将误差值归一化为0~1的得分，limit是允许上限，超过2*limit给0分。"""
            if not np.isfinite(value) or limit <= 0:
                return 0.0
            return max(0.0, min(1.0, 1.0 - value / (limit * 2.0)))

        point_score = min(1.0, len(plane_points) / max(float(thresholds['min_plane_inliers']) * 2.0, 1.0))
        plane_score = score(plane_rmse, float(thresholds['plane_rmse_mm']))
        # 边线得分：只用有限值，任一边为inf时该项得0分
        valid_edge_rmse = [v for v in edge_rmse.values() if v is not None and np.isfinite(v)]
        if valid_edge_rmse:
            edge_score = score(max(valid_edge_rmse), float(thresholds['edge_rmse_mm']))
        else:
            edge_score = 0.0
        geometry_score = min(
            score(parallel_error, float(thresholds['parallel_angle_deg'])),
            score(perpendicular_error, float(thresholds['perpendicular_angle_deg'])),
            score(center_consistency, float(thresholds['center_consistency_mm'])),
        )
        size_score = min(
            score(width_error, float(thresholds['width_tolerance_mm'])),
            score(height_error, float(thresholds['height_tolerance_mm'])),
        )
        rigid_score = score(max_residual, float(thresholds['rigid_fit_max_residual_mm']))
        # 权重分配（文档第8.1节）：
        #   点云覆盖10% + 平面质量20% + 边线拟合25% + 几何约束20% + 尺寸符合10% + 刚体拟合15%
        confidence = float(np.clip(
            0.10 * point_score + 0.20 * plane_score + 0.25 * edge_score
            + 0.20 * geometry_score + 0.10 * size_score + 0.15 * rigid_score,
            0.0,
            0.99,
        ))

        failures = []
        if plane_rmse > float(thresholds['plane_rmse_mm']):
            failures.append(('OPENING_PLANE_NOT_FOUND', f'平面RMSE {plane_rmse:.2f}mm 超限'))
        low_edges = [name for name, count in edge_counts.items() if count < int(thresholds['min_edge_points'])]
        if low_edges:
            # 用四边分组前的原始点数报告（更准确）
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f"边缘点数不足: {', '.join(low_edges)}"))
        finite_edge_rmse_values = [v for v in edge_rmse.values() if v is not None and np.isfinite(v)]
        if not finite_edge_rmse_values:
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', '所有边线RMSE均无效，拟合失败'))
        elif max(finite_edge_rmse_values) > float(thresholds['edge_rmse_mm']):
            bad_edges = [name for name, val in edge_rmse.items() if val is not None and np.isfinite(val) and val > float(thresholds['edge_rmse_mm'])]
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'边线RMSE超限: {max(finite_edge_rmse_values):.2f}mm (边: {bad_edges})'))
        # inf RMSE 的边视为拟合失败
        inf_edges = [name for name, val in edge_rmse.items() if val is None or not np.isfinite(val)]
        if inf_edges:
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'以下边线拟合残差无效(inf): {inf_edges}'))
        if parallel_error > float(thresholds['parallel_angle_deg']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'对边平行误差 {parallel_error:.2f}° 超限'))
        if perpendicular_error > float(thresholds['perpendicular_angle_deg']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'邻边垂直误差 {perpendicular_error:.2f}° 超限'))
        if center_consistency > float(thresholds['center_consistency_mm']):
            failures.append(('RECTANGLE_CONSTRAINT_FAILED', f'对角线中心不一致 {center_consistency:.2f}mm 超限'))
        if width_error > float(thresholds['width_tolerance_mm']) or height_error > float(thresholds['height_tolerance_mm']):
            failures.append(('RECTANGLE_SIZE_OUT_OF_TOLERANCE',
                             f'开口尺寸超出公差: 宽差={width_error:.2f}mm, 高差={height_error:.2f}mm'))
        if max_residual > float(thresholds['rigid_fit_max_residual_mm']):
            failures.append(('RIGID_FIT_RESIDUAL_TOO_HIGH', f'四角点刚体拟合残差 {max_residual:.2f}mm 超限'))
        if confidence < float(confidence_threshold):
            failures.append(('CORNER_CONFIDENCE_LOW', f'矩形定位置信度 {confidence:.2%} 不足'))

        pixel_points = {}
        if plane_pixels is not None and len(plane_pixels) == len(plane_points):
            for key, corner in zip(POINT_KEYS, actual):
                nearest = int(np.argmin(np.linalg.norm(plane_points - corner, axis=1)))
                pixel_points[key] = {
                    'x': round(float(plane_pixels[nearest, 0]), 2),
                    'y': round(float(plane_pixels[nearest, 1]), 2),
                }
            pixel_points['p5'] = {
                'x': round(sum(pixel_points[key]['x'] for key in POINT_KEYS) / 4.0, 2),
                'y': round(sum(pixel_points[key]['y'] for key in POINT_KEYS) / 4.0, 2),
            }

        pose_rotation = np.column_stack((x_axis, y_axis_in, z_axis))
        pose_matrix = _matrix(pose_rotation, center)
        point_confidence = round(confidence, 4)
        result = {
            'algorithm_version': ALGORITHM_VERSION,
            'coordinate_system': coordinate_system,
            'point_unit': 'mm',
            'points': {
                key: _point_dict(point, point_id=key.upper(), confidence=point_confidence, source='four_edge_fit')
                for key, point in zip(POINT_KEYS, actual)
            },
            'center': _point_dict(center, point_id='P5', source='derived_from_p1_p4'),
            'geometry': {
                'width_mm': round(width, 4),
                'height_mm': round(height, 4),
                'width_top_mm': round(width_top, 4),
                'width_bottom_mm': round(width_bottom, 4),
                'height_left_mm': round(height_left, 4),
                'height_right_mm': round(height_right, 4),
                'x_axis': x_axis.round(8).tolist(),
                'y_axis_in': y_axis_in.round(8).tolist(),
                'z_axis': z_axis.round(8).tolist(),
                'normal_out': normal_out.round(8).tolist(),
            },
            'pose': {
                **_point_dict(center),
                'rz': round(math.degrees(math.atan2(x_axis[1], x_axis[0])), 4),
                'matrix': pose_matrix.round(8).tolist(),
            },
            'quality': {
                'valid_point_count': int(len(cloud)),
                'plane_inlier_count': int(len(plane_points)),
                'plane_inlier_ratio': round(float(len(plane_points) / len(cloud)), 4),
                'plane_rmse_mm': round(plane_rmse, 4),
                'edge_evidence_source': edge_evidence_source,
                'edge_point_count': edge_counts,
                'edge_rmse_mm': {key: round(float(value), 4) if np.isfinite(value) else None for key, value in edge_rmse.items()},
                'parallel_error_deg': round(parallel_error, 4),
                'perpendicular_error_deg': round(perpendicular_error, 4),
                'center_consistency_mm': round(center_consistency, 4),
                'width_error_mm': round(width_error, 4),
                'height_error_mm': round(height_error, 4),
                'corner_residuals_mm': [round(float(value), 4) for value in residuals],
                'mean_corner_residual_mm': round(float(residuals.mean()), 4),
                'max_corner_residual_mm': round(max_residual, 4),
                'rigid_fit_rmse_mm': round(rigid_rmse, 4),
                'confidence': round(confidence, 4),
                'thresholds': thresholds,
                'failures': [{'code': code, 'message': message} for code, message in failures],
            },
            'deviation_transform': {
                'meaning': 'standard_to_actual',
                'matrix': deviation.round(8).tolist(),
            },
            'correction_transform': {
                'meaning': 'actual_to_standard',
                'matrix': correction.round(8).tolist(),
            },
            'pixel_points': pixel_points,
            'locate_ok': not failures,
            'error_code': failures[0][0] if failures else '',
            'error_message': '; '.join(message for _, message in failures),
        }
        return result


def calculate_tcp_verification(
    opening_rectangle: dict,
    measured_points: dict,
    *,
    coordinate_system: str,
    tolerance_mm: float,
) -> dict:
    """Compare robot-probed Q1-Q4 with visual P1-P4 and derive Q5."""
    if not opening_rectangle or not is_rectangle_result(opening_rectangle.get('algorithm_version')):
        raise RectangleLocationError('V2_RESULT_REQUIRED', '该记录不是四角点V2定位结果')
    expected_system = opening_rectangle.get('coordinate_system') or 'robot_base'
    if coordinate_system != expected_system:
        raise RectangleLocationError(
            'COORDINATE_SYSTEM_INVALID',
            f'机器人验证点使用{coordinate_system}，视觉结果使用{expected_system}',
        )
    visual_config = opening_rectangle.get('points') or {}
    visual = np.vstack([_as_point(visual_config.get(key), key) for key in POINT_KEYS])
    measured = np.vstack([_as_point(measured_points.get(f'q{index}'), f'q{index}') for index in range(1, 5)])
    q5 = measured.mean(axis=0)
    p5 = visual.mean(axis=0)
    vectors = measured - visual
    distances = np.linalg.norm(vectors, axis=1)
    center_vector = q5 - p5
    center_distance = float(np.linalg.norm(center_vector))
    passed = bool(float(distances.max()) <= tolerance_mm and center_distance <= tolerance_mm)
    return {
        'coordinate_system': coordinate_system,
        'point_unit': 'mm',
        'measured_points': {
            f'q{index}': _point_dict(measured[index - 1], point_id=f'Q{index}')
            for index in range(1, 5)
        },
        'derived_center': _point_dict(q5, point_id='Q5', source='derived_from_q1_q4'),
        'errors': {
            f'p{index}': {
                'dx': round(float(vectors[index - 1, 0]), 4),
                'dy': round(float(vectors[index - 1, 1]), 4),
                'dz': round(float(vectors[index - 1, 2]), 4),
                'distance_mm': round(float(distances[index - 1]), 4),
            }
            for index in range(1, 5)
        },
        'center_error': {
            'dx': round(float(center_vector[0]), 4),
            'dy': round(float(center_vector[1]), 4),
            'dz': round(float(center_vector[2]), 4),
            'distance_mm': round(center_distance, 4),
        },
        'max_corner_error_mm': round(float(distances.max()), 4),
        'mean_corner_error_mm': round(float(distances.mean()), 4),
        'tolerance_mm': round(float(tolerance_mm), 4),
        'passed': passed,
    }
