"""Rack compensation transform helpers.

The vision system measures the rack pose and sends one standard-to-actual
transform to the robot.  The robot owns the taught placement poses and applies
this transform to all 15 stored poses.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


IDENTITY_4X4 = np.eye(4, dtype=float)


def _round_float(value: Any, digits: int = 6) -> float:
    return round(float(value or 0.0), digits)


def _matrix_list(matrix: np.ndarray, digits: int = 8) -> list[list[float]]:
    return np.asarray(matrix, dtype=float).round(digits).tolist()


def matrix_from_offsets(*, x=0, y=0, z=0, rz=0) -> np.ndarray:
    """Build a 4x4 standard-to-actual transform from legacy XYZ/Rz offsets."""
    angle = math.radians(float(rz or 0.0))
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = np.asarray([
        [cos_a, -sin_a, 0.0],
        [sin_a, cos_a, 0.0],
        [0.0, 0.0, 1.0],
    ])
    matrix[:3, 3] = [float(x or 0.0), float(y or 0.0), float(z or 0.0)]
    return matrix


def _coerce_matrix(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        return None
    return matrix


def euler_degrees_from_matrix(matrix: Any) -> dict:
    """Return roll/pitch/yaw degrees from a homogeneous transform matrix."""
    transform = _coerce_matrix(matrix)
    if transform is None:
        transform = IDENTITY_4X4
    rotation = transform[:3, :3]
    sy = math.sqrt(rotation[0, 0] * rotation[0, 0] + rotation[1, 0] * rotation[1, 0])
    singular = sy < 1e-9
    if singular:
        rx = math.atan2(-rotation[1, 2], rotation[1, 1])
        ry = math.atan2(-rotation[2, 0], sy)
        rz = 0.0
    else:
        rx = math.atan2(rotation[2, 1], rotation[2, 2])
        ry = math.atan2(-rotation[2, 0], sy)
        rz = math.atan2(rotation[1, 0], rotation[0, 0])
    return {
        'rx': _round_float(math.degrees(rx), 6),
        'ry': _round_float(math.degrees(ry), 6),
        'rz': _round_float(math.degrees(rz), 6),
    }


def pose6d_from_matrix(matrix: Any) -> dict:
    transform = _coerce_matrix(matrix)
    if transform is None:
        transform = IDENTITY_4X4
    rotation = euler_degrees_from_matrix(transform)
    return {
        'x': _round_float(transform[0, 3], 6),
        'y': _round_float(transform[1, 3], 6),
        'z': _round_float(transform[2, 3], 6),
        **rotation,
    }


def compensation_from_output(
    *,
    offset_x=0,
    offset_y=0,
    offset_z=0,
    offset_rz=0,
    result_data: dict | None = None,
) -> dict:
    """Build the canonical rack-level compensation transform payload."""
    data = result_data or {}
    opening = data.get('opening_rectangle') or {}
    deviation = (opening.get('deviation_transform') or {}).get('matrix')
    matrix = _coerce_matrix(deviation)
    source = 'opening_rectangle_deviation'
    if matrix is None:
        matrix = matrix_from_offsets(x=offset_x, y=offset_y, z=offset_z, rz=offset_rz)
        source = 'offset_xyz_rz'

    pose6d = pose6d_from_matrix(matrix)
    return {
        'meaning': 'standard_rack_to_current_rack',
        'matrix': _matrix_list(matrix),
        'translation_mm': {
            'x': pose6d['x'],
            'y': pose6d['y'],
            'z': pose6d['z'],
        },
        'rotation_deg': {
            'rx': pose6d['rx'],
            'ry': pose6d['ry'],
            'rz': pose6d['rz'],
        },
        'pose6d': pose6d,
        'source': source,
        'placement_formula': 'actual_place_pose = T_standard_to_current * taught_standard_place_pose',
        'managed_place_pose_count': 0,
        'robot_taught_place_pose_count': 15,
    }


def compensation_from_result(result_data: dict | None, *, fallback_offset: dict | None = None) -> dict:
    data = result_data or {}
    existing = data.get('rack_compensation') or data.get('compensation_transform')
    if isinstance(existing, dict) and _coerce_matrix(existing.get('matrix')) is not None:
        return existing
    fallback = fallback_offset or {}
    return compensation_from_output(
        offset_x=fallback.get('x', 0),
        offset_y=fallback.get('y', 0),
        offset_z=fallback.get('z', 0),
        offset_rz=fallback.get('rz', 0),
        result_data=data,
    )


def combine_compensations(*compensations: dict) -> dict:
    matrix = IDENTITY_4X4.copy()
    sources = []
    for compensation in compensations:
        candidate = _coerce_matrix((compensation or {}).get('matrix'))
        if candidate is None:
            continue
        matrix = candidate @ matrix
        source = (compensation or {}).get('source')
        if source:
            sources.append(str(source))
    pose6d = pose6d_from_matrix(matrix)
    return {
        'meaning': 'standard_rack_to_current_rack',
        'matrix': _matrix_list(matrix),
        'translation_mm': {
            'x': pose6d['x'],
            'y': pose6d['y'],
            'z': pose6d['z'],
        },
        'rotation_deg': {
            'rx': pose6d['rx'],
            'ry': pose6d['ry'],
            'rz': pose6d['rz'],
        },
        'pose6d': pose6d,
        'source': '+'.join(sources) if sources else 'identity',
        'placement_formula': 'actual_place_pose = T_standard_to_current * taught_standard_place_pose',
        'managed_place_pose_count': 0,
        'robot_taught_place_pose_count': 15,
    }
