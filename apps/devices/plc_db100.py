"""DB2 communication contract and Siemens S7 value codecs.

The workflow layer uses symbolic point names only.  Byte offsets, S7 STRING
headers and big-endian numeric encoding are deliberately kept in this module.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DB100Point:
    name: str
    offset: int
    data_type: str
    direction: str
    description: str
    size: int
    bit: int = 0


DB_NUMBER = 2
DB_SIZE = 104
PLC_SCAN_INTERVAL = 0.5  # Minimum gap after a scan completes, shared by all listeners.
POSITION_FAILURE_OFFSET = 0.0  # 无法计算时覆盖两组 XYZ 为零


def _point(name, offset, data_type, direction, description, size, bit=0):
    return DB100Point(name, offset, data_type, direction, description, size, bit)


DB100_POINTS = (
    _point('product_barcode', 0, 'STRING[20]', 'IN', '当前产品条码', 22, 0),
    _point('rack_barcode', 24, 'STRING[20]', 'IN', '料框码 1', 22),
    _point('rack_barcode_2', 46, 'STRING[20]', 'IN', '料框码 2', 22),
    _point('position_trigger', 68, 'BOOL', 'IN', '3D 定位触发', 1, 3),
    _point('foam_trigger', 68, 'BOOL', 'IN', '泡棉视觉检测触发', 1, 4),
    _point('boxing_trigger', 68, 'BOOL', 'IN', 'MES 封箱上传触发 1', 1, 5),
    _point('boxing_trigger_2', 68, 'BOOL', 'IN', 'MES 封箱上传触发 2', 1, 6),
    _point('rack_working', 68, 'BOOL', 'IN', '料箱 1 工作中', 1, 7),
    _point('rack_working_2', 69, 'BOOL', 'IN', '料箱 2 工作中', 1, 0),
    _point('heartbeat', 70, 'BOOL', 'OUT', 'AGV 在线心跳（每 0.5 秒翻转）', 1, 0),
    _point('layer_delta_x', 76, 'REAL', 'OUT', '当前层视觉补偿 ΔX1', 4, 0),
    _point('layer_delta_y', 80, 'REAL', 'OUT', '当前层视觉补偿 ΔY1', 4, 0),
    _point('layer_delta_z', 84, 'REAL', 'OUT', '当前层视觉补偿 ΔZ1', 4, 0),
    _point('layer_delta_x2', 88, 'REAL', 'OUT', '当前层视觉补偿 ΔX2', 4, 0),
    _point('layer_delta_y2', 92, 'REAL', 'OUT', '当前层视觉补偿 ΔY2', 4, 0),
    _point('layer_delta_z2', 96, 'REAL', 'OUT', '当前层视觉补偿 ΔZ2', 4, 0),
    _point('rack_type_code_2', 102, 'INT', 'OUT', '料架种类 2', 2),
    _point('rack_type_code', 100, 'INT', 'OUT', '料架种类 1', 2),
)

ACTIVE_OUTPUT_NAMES = frozenset(point.name for point in DB100_POINTS if point.direction == 'OUT')

POINTS_BY_NAME = {point.name: point for point in DB100_POINTS}


def encode_value(point: DB100Point, value: Any) -> bytes:
    if point.data_type == 'BOOL':
        return bytes([1 << point.bit if bool(value) else 0])
    if point.data_type == 'INT':
        return struct.pack('>h', int(value))
    if point.data_type == 'REAL':
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f'{point.name} 不能写入非有限浮点数')
        return struct.pack('>f', numeric)
    if point.data_type == 'BYTE':
        return bytes([int(value) & 0xFF])
    if point.data_type == 'STRING[20]':
        raw = str(value).encode('ascii')
        if len(raw) > 20:
            raise ValueError(f'{point.name} 超过 STRING[20] 长度')
        return bytes([20, len(raw)]) + raw.ljust(20, b'\x00')
    raise ValueError(f'不支持的数据类型: {point.data_type}')


def decode_value(point: DB100Point, data: bytes) -> Any:
    if len(data) < point.size:
        raise ValueError(f'{point.name} 数据不足: {len(data)} < {point.size}')
    if point.data_type == 'BOOL':
        return bool(data[0] & (1 << point.bit))
    if point.data_type == 'INT':
        return struct.unpack('>h', data[:2])[0]
    if point.data_type == 'REAL':
        return struct.unpack('>f', data[:4])[0]
    if point.data_type == 'BYTE':
        return data[0]
    if point.data_type == 'STRING[20]':
        maximum, current = data[0], data[1]
        if maximum > 20 or current > maximum:
            raise ValueError(f'{point.name} 的 S7 STRING 头无效: max={maximum}, len={current}')
        return data[2:2 + current].decode('ascii').strip()
    raise ValueError(f'不支持的数据类型: {point.data_type}')


def position_values(payload):
    """Validate all six offsets before writing any, rounding to Siemens REAL."""
    values = {}
    for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2'):
        keys = (f'layer_delta_{axis}', f'compensation_{axis}', f'offset_{axis}')
        key = next((key for key in keys if key in payload), None)
        if key is None:
            if axis.endswith('2') and not any(
                f'{prefix}_{a}' in payload
                for prefix in ('layer_delta', 'compensation', 'offset')
                for a in ('x2', 'y2', 'z2')
            ):
                values[axis] = 0.0
                continue
            raise ValueError(f'缺少补偿 {axis}，必须提供两组 XYZ')
        point = POINTS_BY_NAME[f'layer_delta_{axis}']
        values[axis] = decode_value(point, encode_value(point, payload[key]))
    return values
