"""Explicit point-cloud units; never infer units from coordinate magnitude."""
import json
from pathlib import Path

import numpy as np


def to_millimeters(cloud, unit='mm'):
    if unit == 'mm':
        return cloud
    if unit == 'm':
        return np.asarray(cloud, dtype=np.float64) * 1000.0
    raise ValueError(f'不支持的点云单位: {unit}')


def load_pointcloud_mm(path):
    path = Path(path)
    marker = path.with_suffix('.units.json')
    unit = json.loads(marker.read_text(encoding='utf-8'))['unit'] if marker.is_file() else 'mm'
    return to_millimeters(np.load(path, allow_pickle=False), unit)
