"""DB100 communication contract and Siemens S7 value codecs.

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


DB_NUMBER = 100
DB_SIZE = 71


def _point(name, offset, data_type, direction, description, size, bit=0):
    return DB100Point(name, offset, data_type, direction, description, size, bit)


DB100_POINTS = (
    _point('heartbeat', 0, 'INT', 'OUT', '心跳计数', 2),
    _point('product_barcode', 2, 'STRING[20]', 'IN', '产品条码', 22),
    _point('mark_trigger', 24, 'BOOL', 'IN', '产品条码就绪触发', 1),
    _point('mark_read_done', 25, 'BOOL', 'OUT', '产品条码处理完成确认', 1),
    _point('product_barcode_valid', 26, 'BOOL', 'OUT', '产品条码校验结果（1=OK，0=NG）', 1),
    _point('reserved_27', 27, 'BYTE', '-', '对齐填充', 1),
    _point('rack_barcode', 28, 'STRING[20]', 'IN', '料框码', 22),
    _point('rack_trigger', 50, 'BOOL', 'IN', '料框到位触发', 1),
    _point('rack_done', 51, 'BOOL', 'OUT', '料框处理完成确认', 1),
    _point('rack_result', 52, 'BOOL', 'OUT', '料框处理结果（1=OK，0=NG）', 1),
    _point('recipe_verify_trigger', 53, 'BOOL', 'IN', '配方校验触发', 1),
    _point('recipe_verify_done', 54, 'BOOL', 'OUT', '配方校验完成确认', 1),
    _point('boxing_allowed', 55, 'BOOL', 'OUT', '可装箱结果（1=OK，0=NG）', 1),
    _point('position_trigger', 56, 'BOOL', 'IN', '3D定位触发', 1),
    _point('position_done', 57, 'BOOL', 'OUT', '3D定位完成确认', 1),
    _point('position_success', 58, 'BOOL', 'OUT', '3D定位结果（1=OK，0=NG）', 1),
    _point('reserved_59', 59, 'BYTE', '-', '对齐填充', 1),
    _point('layer_delta_z', 60, 'REAL', 'OUT', '当前层视觉补偿值 ΔZ（mm）', 4),
    _point('foam_trigger', 64, 'BOOL', 'IN', '泡棉检测结果记录触发', 1),
    _point('foam_passed', 65, 'BOOL', 'IN', '泡棉检测结果（1=OK，0=NG）', 1),
    _point('foam_done', 66, 'BOOL', 'OUT', '泡棉检测记录完成确认', 1),
    _point('boxing_trigger', 67, 'BOOL', 'IN', '装箱完成 / MES上传触发', 1),
    _point('mes_upload_done', 68, 'BOOL', 'OUT', 'MES上传完成确认', 1),
    _point('mes_upload_success', 69, 'BOOL', 'OUT', 'MES上传结果（1=OK，0=NG）', 1),
    _point('workstation_locked', 70, 'BOOL', 'OUT', '工位锁定（1=锁定，0=正常）', 1),
)

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


def validate_barcode(value: str, label: str = '条码') -> str:
    code = (value or '').strip()
    if not code:
        raise ValueError(f'{label}为空')
    try:
        encoded = code.encode('ascii')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{label}必须为 ASCII 字符') from exc
    if len(encoded) > 20:
        raise ValueError(f'{label}超过 PLC STRING[20] 长度')
    if any(ord(char) < 33 or ord(char) == 127 for char in code):
        raise ValueError(f'{label}包含空格或控制字符')
    return code
