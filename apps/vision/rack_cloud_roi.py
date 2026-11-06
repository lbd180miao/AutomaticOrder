"""Pixel regions used to select the point-cloud registration template."""
import math

import numpy as np


TARGETS = ('P1_horizontal', 'P1_vertical', 'P2_horizontal', 'P2_vertical')


def cloud_config(config):
    """Only current capture and cloud-template settings belong in new packages."""
    return {key: value for key, value in (config or {}).items()
            if key in {'camera_roi', 'cloud_match_config', 'cloud_match_reference'}}


def config_status(config):
    config = config if isinstance(config, dict) else {}
    rois = config.get('rois') or []
    size = config.get('imageSize') or []
    valid_targets = set()
    if isinstance(rois, list) and len(size) == 2:
        for roi in rois:
            try:
                image_roi(roi, (size[1], size[0]))
                if roi.get('target') in TARGETS:
                    valid_targets.add(roi['target'])
            except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
                continue
    return {
        'has_saved_roi': bool(valid_targets),
        'configured_count': len(valid_targets),
        'is_complete': len(valid_targets) == 4 and len(rois) == 4,
        'rois': rois,
    }


def image_roi(raw, shape):
    x, y = float(raw['x']), float(raw['y'])
    width = float(raw.get('width', raw.get('w')))
    height = float(raw.get('height', raw.get('h')))
    if not np.isfinite([x, y, width, height]).all() or width < 3 or height < 3:
        raise ValueError('ROI 必须为有限数值且宽高至少 3 像素')
    x0, y0, x1, y1 = math.floor(x), math.floor(y), math.ceil(x+width), math.ceil(y+height)
    if x0 < 0 or y0 < 0 or x1 > shape[1] or y1 > shape[0]:
        raise ValueError('ROI 超出原图，禁止静默裁剪')
    return x0, y0, x1, y1
