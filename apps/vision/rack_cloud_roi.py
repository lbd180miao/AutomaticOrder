"""Pixel regions used to select the point-cloud registration template."""
import math

import numpy as np


TARGETS = ('P1_horizontal', 'P1_vertical', 'P2_horizontal', 'P2_vertical')

def algorithm_keys(algorithm='cloud_match'):
    if algorithm not in ('cloud_match', 'cloud_center'):
        raise ValueError('未知点云定位算法')
    return algorithm + '_config', algorithm + '_reference'


def required_targets(config):
    algorithm_keys(config.get('algorithm', 'cloud_match'))
    layers = config.get('rack_layers', 3)
    if layers not in (2, 3):
        raise ValueError('料架层数必须为 2 或 3')
    if config.get('algorithm') == 'cloud_center':
        return ('P1_cross',) if layers == 2 else ('P1_cross', 'P2_cross')
    return TARGETS[:2] if layers == 2 else TARGETS


def cloud_config(config):
    """Only current capture and cloud-template settings belong in new packages."""
    return {key: value for key, value in (config or {}).items()
            if key in {'camera_roi', 'cloud_match_config', 'cloud_match_reference',
                       'cloud_center_config', 'cloud_center_reference'}}


def config_status(config):
    config = config if isinstance(config, dict) else {}
    rois = config.get('rois') or []
    size = config.get('imageSize') or []
    try:
        targets = required_targets(config)
    except ValueError:
        targets = ()
    valid_targets = set()
    if isinstance(rois, list) and len(size) == 2:
        for roi in rois:
            try:
                image_roi(roi, (size[1], size[0]))
                if roi.get('target') in targets:
                    valid_targets.add(roi['target'])
            except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
                continue
    return {
        'has_saved_roi': bool(valid_targets),
        'configured_count': len(valid_targets),
        'is_complete': bool(targets) and len(valid_targets) == len(targets) and len(rois) == len(targets),
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
