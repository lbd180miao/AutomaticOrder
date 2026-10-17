"""Suggest pixel ROIs from a verified edge identity; never persist or teach XYZ."""
import copy

import numpy as np

from .algorithms.rack_dual_point import TARGETS, LocalizationError, locate_2d, require


def suggest_rois(image, config):
    """Refit current-frame edges, then frame their actual support near intersections.

    A saved recipe supplies physical edge identity. Do not infer which of several
    visually similar rack edges is the user's reference from brightness alone.
    """
    original = locate_2d(image, config)
    proposed = copy.deepcopy(config)
    by_target = {roi['target']: roi for roi in proposed['rois']}
    for line in original['lines']:
        roi = by_target[line['target']]
        points = np.asarray(line['inlier_points'])
        horizontal = roi.get('imageDirection', 'horizontal' if roi['target'].endswith('horizontal') else 'vertical') == 'horizontal'
        pair = TARGETS.index(roi['target']) // 2
        point = np.asarray(original['pixels'][pair])
        along = 0 if horizontal else 1
        # Keep the closest 120 pixels of real support; do not create a box around
        # the mathematical intersection where the source edge may not exist.
        nearest = points[np.argmin(abs(points[:, along]-point[along])), along]
        close = points[abs(points[:, along]-nearest) <= 120]
        if len(close) >= max(6, config['lineQuality']['min_points']):
            points = close
        pad = np.array([3., max(10., roi['searchHalfWidth']+3)])
        if not horizontal:
            pad = pad[::-1]
        lower = np.maximum(0, np.floor(points.min(0)-pad)).astype(int)
        upper = np.minimum([image.shape[1], image.shape[0]], np.ceil(points.max(0)+pad+1)).astype(int)
        a, b, c = line['line_abc']
        center = (lower+upper-1)/2
        roi.update(x=int(lower[0]), y=int(lower[1]), width=int(upper[0]-lower[0]), height=int(upper[1]-lower[1]),
                   expectedPosition=float((-a*center[0]-c)/b if horizontal else (-b*center[1]-c)/a),
                   expectedSlope=float(-a/b if horizontal else -b/a), edgeSelection='taught')
        roi['caliperCount'] = min(roi['caliperCount'], roi['width'] if horizontal else roi['height'])
    result = locate_2d(image, proposed)
    drift = np.linalg.norm(np.asarray(result['pixels'])-original['pixels'], axis=1)
    require(float(drift.max()) <= 3, 'AUTO_ROI_UNSTABLE', '2d',
            '自动框选后交点变化超过 3px，已保留原框，请人工确认目标边缘')
    return proposed, result


def auto_roi_config(image, current, saved=None):
    errors = []
    for candidate in (current, saved):
        if not candidate or len(candidate.get('rois', [])) != 4:
            continue
        try:
            return suggest_rois(image, candidate)
        except (LocalizationError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    raise LocalizationError('AUTO_ROI_FAILED', '2d',
        '无法根据当前原图和配方可靠生成四 ROI，原框未改动。请先示教清晰的目标边缘。'
        + (' 原因：'+errors[-1] if errors else ' 当前配方没有四 ROI 示教。'))
