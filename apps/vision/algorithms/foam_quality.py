"""Independent integrity measurements; never modify the measured foreground."""
import math

import cv2
import numpy as np


QUALITY_VERSION = 'foam-quality-v2'


def quality_config(config):
    """Validate optional limits. Existing recipes retain their acceptance limits."""
    mode = config.get('decision_mode', 'legacy')
    if mode not in ('legacy', 'separated-v2'):
        raise ValueError('decision_mode must be legacy or separated-v2')
    result = {'decision_mode': mode}
    for key, low, high in (
        ('min_area_ratio', 0, None), ('max_area_ratio', 0, None),
        ('max_missing_ratio', 0, 1), ('max_excess_ratio', 0, None),
        ('max_local_missing_ratio', 0, 1),
    ):
        value = config.get(key)
        if value is None:
            continue
        value = float(value)
        if not math.isfinite(value) or value < low or (high is not None and value > high):
            raise ValueError(f'{key} is outside its valid range')
        result[key] = value
    if result.get('max_area_ratio', math.inf) < result.get('min_area_ratio', 0):
        raise ValueError('max_area_ratio must be >= min_area_ratio')
    if mode == 'separated-v2' and not all(k in result for k in (
        'min_area_ratio', 'max_area_ratio', 'max_missing_ratio', 'max_excess_ratio',
    )):
        raise ValueError('separated-v2 requires explicit area, missing and excess limits')
    return result


def measure_integrity(detected, standard):
    """Translation-only comparison, independent of the original position check.

    Centroid translation is a diagnostic estimator, not product registration.
    No scale, deformation, hole filling or free-angle fitting is permitted.
    Excess uses the original area, so translating pixels outside the image
    cannot hide over-segmentation. Local missing uses four template quadrants.
    """
    d = (detected > 0).astype(np.uint8)
    t = standard > 0
    area = int(np.count_nonzero(t))
    pixels = int(np.count_nonzero(d))
    if not area:
        raise ValueError('Integrity measurement requires a nonempty standard mask')
    dm, tm = cv2.moments(d), cv2.moments(t.astype(np.uint8))
    dx = dy = 0.0
    if pixels:
        dx = dm['m10'] / dm['m00'] - tm['m10'] / tm['m00']
        dy = dm['m01'] / dm['m00'] - tm['m01'] / tm['m00']
    aligned = cv2.warpAffine(d, np.float32([[1, 0, -dx], [0, 1, -dy]]),
                             (d.shape[1], d.shape[0]), flags=cv2.INTER_NEAREST) > 0
    overlap = int(np.count_nonzero(aligned & t))
    x, y, w, h = cv2.boundingRect(t.astype(np.uint8))
    local = []
    for ya, yb in ((y, y + h // 2), (y + h // 2, y + h)):
        for xa, xb in ((x, x + w // 2), (x + w // 2, x + w)):
            part = t[ya:yb, xa:xb]
            n = int(np.count_nonzero(part))
            if n:
                local.append(float(np.count_nonzero(part & ~aligned[ya:yb, xa:xb])) / n)
    return {
        'area_ratio': pixels / area,
        'aligned_coverage_ratio': overlap / area,
        'missing_ratio': 1 - overlap / area,
        'excess_ratio': max(0, pixels - overlap) / area,
        'max_local_missing_ratio': max(local, default=1.0),
        'integrity_alignment': 'centroid_translation_only',
    }


def evaluate_integrity(metrics, config):
    """Return all configured failures, not just the first one."""
    failures = []
    for limit, metric, minimum, reason in (
        ('min_area_ratio', 'area_ratio', True, 'area_below_minimum'),
        ('max_area_ratio', 'area_ratio', False, 'area_above_maximum'),
        ('max_missing_ratio', 'missing_ratio', False, 'incomplete'),
        ('max_excess_ratio', 'excess_ratio', False, 'excess_area'),
        ('max_local_missing_ratio', 'max_local_missing_ratio', False, 'local_defect'),
    ):
        if limit in config:
            value, threshold = metrics[metric], config[limit]
            failed = value < threshold - 1e-9 if minimum else value > threshold + 1e-9
            if failed:
                failures.append(reason)
    return failures
