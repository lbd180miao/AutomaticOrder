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
DB_SIZE = 63
POSITION_FAILURE_OFFSET = 999.0  # 3D 联调失败哨兵值（不是有效补偿）


def _point(name, offset, data_type, direction, description, size, bit=0):
    return DB100Point(name, offset, data_type, direction, description, size, bit)


DB100_POINTS = (
    _point('product_barcode', 0, 'STRING[20]', 'IN', '当前产品条码', 22, 0),
    _point('mark_trigger', 22, 'BOOL', 'IN', '扫码完成', 1, 0),
    _point('rack_barcode', 24, 'STRING[20]', 'IN', '料框码', 22, 0),
    _point('rack_trigger', 46, 'BOOL', 'IN', '料框到位触发', 1, 0),
    _point('recipe_verify_trigger', 46, 'BOOL', 'IN', '配方校验触发', 1, 1),
    _point('position_trigger', 46, 'BOOL', 'IN', '3D 定位触发', 1, 2),
    _point('foam_trigger', 46, 'BOOL', 'IN', '泡棉视觉检测触发', 1, 3),
    _point('boxing_trigger', 46, 'BOOL', 'IN', 'MES 封箱上传触发', 1, 4),
    _point('heartbeat', 48, 'BOOL', 'OUT', '心跳信号', 1, 0),
    _point('mark_read_done', 48, 'BOOL', 'OUT', '产品条码处理完成确认', 1, 1),
    _point('product_barcode_valid', 48, 'BOOL', 'OUT', '产品条码校验结果', 1, 2),
    _point('product_mes_upload_done', 48, 'BOOL', 'OUT', '单件 MES 上传完成确认', 1, 3),
    _point('product_mes_upload_success', 48, 'BOOL', 'OUT', '单件 MES 上传结果', 1, 4),
    _point('rack_done', 48, 'BOOL', 'OUT', '料框处理完成确认', 1, 5),
    _point('rack_result', 48, 'BOOL', 'OUT', '料框处理结果', 1, 6),
    _point('recipe_verify_done', 48, 'BOOL', 'OUT', '配方校验完成确认', 1, 7),
    _point('boxing_allowed', 49, 'BOOL', 'OUT', '可装箱结果', 1, 0),
    _point('position_done', 49, 'BOOL', 'OUT', '3D 定位完成确认', 1, 1),
    _point('position_success', 49, 'BOOL', 'OUT', '3D 定位结果', 1, 2),
    _point('layer_delta_x', 50, 'REAL', 'OUT', '当前层视觉补偿 ΔX', 4, 0),
    _point('layer_delta_y', 54, 'REAL', 'OUT', '当前层视觉补偿 ΔY', 4, 0),
    _point('layer_delta_z', 58, 'REAL', 'OUT', '当前层视觉补偿 ΔZ', 4, 0),
    _point('foam_done', 62, 'BOOL', 'OUT', '泡棉检测完成确认', 1, 0),
    _point('foam_passed', 62, 'BOOL', 'OUT', '泡棉检测结果', 1, 1),
    _point('mes_upload_done', 62, 'BOOL', 'OUT', 'MES 封箱上传完成确认', 1, 2),
    _point('mes_upload_success', 62, 'BOOL', 'OUT', 'MES 封箱上传结果', 1, 3),
    _point('workstation_locked', 62, 'BOOL', 'OUT', '工位锁定', 1, 4),
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
    """使用统一三维校验引擎校验条码。"""
    from apps.core.barcode_validator import validate_rack_barcode, validate_product_barcode
    if '料框' in label:
        res = validate_rack_barcode(value, check_db_duplicate=True)
    else:
        res = validate_product_barcode(value, check_db_duplicate=True)
    return res.raise_if_invalid()
