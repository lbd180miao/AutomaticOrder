import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


class TofConfigError(ValueError):
    """Raised when a TOF camera configuration cannot be decoded or validated."""


@dataclass(frozen=True)
class TofCameraConfig:
    frame_rate: int
    exposure_time: int
    trigger_mode: str
    confidence: tuple[bool, int]
    flying_pixels: tuple[bool, int]
    spatial: tuple[bool, int]


def _required(data, field):
    if field not in data:
        raise TofConfigError(f'missing required field: {field}')
    return data[field]


def _boolean(data, field):
    value = _required(data, field)
    if type(value) is not bool:
        raise TofConfigError(f'{field} must be a boolean')
    return value


def _integer(data, field, *, minimum):
    value = _required(data, field)
    if type(value) is not int:
        raise TofConfigError(f'{field} must be an integer')
    if value < minimum:
        raise TofConfigError(f'{field} must be at least {minimum}')
    return value


def load_tof_config(path=None):
    config_path = Path(path) if path is not None else Path(settings.BASE_DIR) / '3d_SDK' / 'tofconfig'

    try:
        encoded = config_path.read_bytes()
    except FileNotFoundError as exc:
        raise TofConfigError(f'TOF config missing: {config_path}') from exc
    except OSError as exc:
        raise TofConfigError(f'cannot read TOF config {config_path}: {exc}') from exc

    decoded_bytes = bytes(byte ^ 0xFF for byte in encoded)
    try:
        decoded_text = decoded_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise TofConfigError(f'TOF config UTF-8 decode error: {exc}') from exc

    try:
        data = json.loads(decoded_text)
    except json.JSONDecodeError as exc:
        raise TofConfigError(f'TOF config JSON error: {exc}') from exc

    if not isinstance(data, dict):
        raise TofConfigError('TOF config root must be a JSON object')

    frame_rate = _integer(data, 'fps_value', minimum=1)

    exposure_values = _required(data, 'exposure_time')
    if not isinstance(exposure_values, list) or not exposure_values:
        raise TofConfigError('exposure_time must be a non-empty list')
    exposure_time = exposure_values[0]
    if type(exposure_time) is not int or exposure_time <= 0:
        raise TofConfigError('exposure_time first item must be a positive integer')

    trigger_value = _integer(data, 'trigger_mode', minimum=0)
    trigger_modes = {0: 'ACTIVE', 1: 'SOFT', 2: 'HARD'}
    try:
        trigger_mode = trigger_modes[trigger_value]
    except KeyError as exc:
        raise TofConfigError(f'unknown trigger_mode: {trigger_value}') from exc

    confidence = (
        _boolean(data, 'is_confidence_filtering'),
        _integer(data, 'confidence_filter_value', minimum=0),
    )
    flying_pixels = (
        _boolean(data, 'is_fly_filtering'),
        _integer(data, 'fly_filter_value', minimum=0),
    )
    spatial = (
        _boolean(data, 'is_spatial_filtering'),
        _integer(data, 'spatial_filter_value', minimum=0),
    )

    return TofCameraConfig(
        frame_rate=frame_rate,
        exposure_time=exposure_time,
        trigger_mode=trigger_mode,
        confidence=confidence,
        flying_pixels=flying_pixels,
        spatial=spatial,
    )
