"""Coordinate-level temporal consensus; rejected frames cannot contribute an axis."""
import numpy as np
from .exceptions import RackPositioningException, RackPositioningErrorCode as EC


def fuse_frames(frames, config):
    xyz = np.asarray([[f[f'{a}_detection'][f'{a}_actual'] for a in 'xyz'] for f in frames])
    if not np.isfinite(xyz).all():
        raise RackPositioningException(EC.MULTIFRAME_UNSTABLE, '多帧坐标包含非有限数值')
    center = np.median(xyz, axis=0)
    deviations = np.abs(xyz - center)
    mad = np.median(deviations, axis=0)
    tolerance = np.maximum(config['frame_outlier_mm'], config['frame_mad_multiplier'] * 1.4826 * mad)
    accepted = np.flatnonzero(np.all(deviations <= tolerance, axis=1))
    details = {'coordinates_mm': xyz.tolist(), 'median_mm': center.tolist(),
               'mad_mm': mad.tolist(), 'accepted_indices': accepted.tolist(),
               'requested_count': config['frame_count'], 'valid_count': len(frames),
               'tolerance_mm': tolerance.tolist()}
    required = 1 if config['frame_count'] == 1 else config['frame_count'] // 2 + 1
    if len(accepted) < required or np.any(mad > config['max_frame_mad_mm']):
        raise RackPositioningException(EC.MULTIFRAME_UNSTABLE, '多帧一致性不足', details)
    retained = xyz[accepted]
    median = np.median(retained, axis=0)
    retained_mad = np.median(np.abs(retained - median), axis=0)
    details['retained_mad_mm'] = retained_mad.tolist()
    details['confidence'] = float(1 / (1 + (retained_mad.max() / config['max_frame_mad_mm']) ** 2))
    return median, details
