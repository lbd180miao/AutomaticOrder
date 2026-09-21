"""Recipe parameters: mm, points/mm³ and degrees; no hardware-dependent defaults."""
from copy import deepcopy
import numpy as np
from .exceptions import ConfigurationError, RackPositioningErrorCode as EC

DEFAULTS = {
    'nb_neighbors': 20, 'std_ratio': 2.0, 'voxel_size_mm': 3.0,
    'downsample_threshold': 5000, 'min_roi_points': 10,
    'min_density': 0.00001, 'target_points': 100, 'target_density': 0.0001,
    'ransac_threshold_mm': 3.0, 'ransac_iterations': 600, 'seed': 42,
    'expected_normal': [0.0, 0.0, 1.0], 'max_normal_angle_deg': 12.0,
    'max_plane_rms_mm': 2.5, 'min_inlier_ratio': 0.5,
    'projection_bin_mm': 1.0, 'projection_smoothing_mm': 1.0,
    'min_peak_ratio': 2.0, 'target_peak_ratio': 5.0,
    'max_peak_width_mm': 12.0, 'min_peak_fraction': 0.1,
    'edge_direction': 'min', 'pillar_mode': 'single',
    'frame_count': 1, 'max_frame_mad_mm': 2.0, 'frame_outlier_mm': 3.0,
    'frame_mad_multiplier': 3.0, 'max_history_jump_mm': None,
    'save_failure_artifacts': True,
}

def load_config(overrides=None):
    config = deepcopy(DEFAULTS)
    try:
        if overrides is not None:
            if not isinstance(overrides, dict) or set(overrides) - set(config):
                raise ValueError('未知定位参数或参数不是对象')
            config.update(overrides)
        integers = ('nb_neighbors', 'downsample_threshold', 'min_roi_points',
                    'target_points', 'ransac_iterations', 'seed', 'frame_count')
        for key in integers:
            if type(config[key]) is not int or config[key] < (0 if key == 'seed' else 1):
                raise ValueError(f'{key} 必须为有效整数')
        if config['frame_count'] not in (1, 3, 4, 5):
            raise ValueError('frame_count 必须为 1 或 3~5')
        if config['nb_neighbors'] < 2 or config['ransac_iterations'] > 10000:
            raise ValueError('邻居数至少 2，RANSAC 迭代数至多 10000')
        excluded = set(integers) | {'expected_normal', 'edge_direction', 'pillar_mode',
                                    'save_failure_artifacts', 'max_history_jump_mm'}
        for key in set(config) - excluded:
            value = config[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f'{key} 必须为有限正数')
        normal = np.asarray(config['expected_normal'], dtype=float)
        if normal.shape != (3,) or not np.isfinite(normal).all() or np.linalg.norm(normal) < 1e-9:
            raise ValueError('expected_normal 必须为非零三维向量')
        if not 0 < config['max_normal_angle_deg'] < 45:
            raise ValueError('法向容差必须在 0~45° 内')
        if not 0 < config['min_inlier_ratio'] <= 1 or not 0 < config['min_peak_fraction'] <= 1:
            raise ValueError('占比阈值必须在 (0,1] 内')
        if config['edge_direction'] not in ('min', 'max') or config['pillar_mode'] not in ('single', 'double'):
            raise ValueError('边缘方向或立柱峰模式无效')
        if type(config['save_failure_artifacts']) is not bool:
            raise ValueError('save_failure_artifacts 必须为布尔值')
        history = config['max_history_jump_mm']
        if history is not None and (isinstance(history, bool) or not isinstance(history, (int, float)) or not np.isfinite(history) or history <= 0):
            raise ValueError('max_history_jump_mm 必须为空或有限正数')
        if config['target_density'] < config['min_density'] or config['target_peak_ratio'] < config['min_peak_ratio']:
            raise ValueError('置信度目标必须不小于拦截阈值')
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(EC.INVALID_PARAMETERS, str(exc)) from exc
    return config

def quality_score(metrics):
    return float(min(metrics.values()))
