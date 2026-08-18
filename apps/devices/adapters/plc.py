"""Siemens DB100 adapter.

``Snap7Transport`` imports python-snap7 lazily so development and unit tests can
run without the native PLC dependency. ``MemoryPLCTransport`` is a byte-accurate
DB simulator used for offline end-to-end testing.
"""
from __future__ import annotations

from apps.devices.plc_db100 import (
    DB_NUMBER, DB_SIZE, POINTS_BY_NAME, decode_value, encode_value,
)

from .base import BaseDeviceAdapter


class Snap7Transport:
    def __init__(self, address, rack=0, slot=1, tcp_port=102):
        self.address = address
        self.rack = int(rack)
        self.slot = int(slot)
        self.tcp_port = int(tcp_port)
        self.client = None
        self.connected = False

    def connect(self):
        try:
            import snap7
        except ImportError as exc:
            raise RuntimeError('真实 PLC 模式需要安装 python-snap7') from exc
        if self.client is None:
            client_class = getattr(snap7, 'Client', None) or snap7.client.Client
            self.client = client_class()
        try:
            self.client.connect(self.address, self.rack, self.slot, self.tcp_port)
        except TypeError:
            # python-snap7 3.x defaults to TCP/102 and exposes a 3-arg API.
            if self.tcp_port != 102:
                raise
            self.client.connect(self.address, self.rack, self.slot)
        self.connected = True
        return self.is_connected()

    def disconnect(self):
        if self.client is not None:
            self.client.disconnect()
        self.connected = False

    def is_connected(self):
        if not (self.client and self.connected):
            return False
        getter = getattr(self.client, 'get_connected', None)
        return bool(getter()) if getter else True

    def read(self, db_number, offset, size):
        return bytes(self.client.db_read(db_number, offset, size))

    def write(self, db_number, offset, data):
        self.client.db_write(db_number, offset, bytearray(data))


class MemoryPLCTransport:
    """In-memory Siemens DB transport for deterministic integration tests."""

    def __init__(self, size=DB_SIZE):
        self.buffer = bytearray(size)
        self.connected = False

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def read(self, db_number, offset, size):
        if not self.connected:
            raise ConnectionError('PLC 未连接')
        return bytes(self.buffer[offset:offset + size])

    def write(self, db_number, offset, data):
        if not self.connected:
            raise ConnectionError('PLC 未连接')
        self.buffer[offset:offset + len(data)] = data


class PLCAdapter(BaseDeviceAdapter):
    """Typed read/write facade for the fixed DB100 contract."""

    def __init__(self, transport=None, *, address='', rack=0, slot=1, tcp_port=102):
        self.transport = transport or Snap7Transport(address, rack, slot, tcp_port)

    def connect(self):
        return self.transport.connect()

    def disconnect(self):
        self.transport.disconnect()
        return True

    def is_online(self):
        return self.transport.is_connected()

    def read(self, key):
        return self.read_point(key)

    def write(self, key, value):
        self.write_point(key, value)
        return True

    def execute(self, command, payload=None):
        if command == 'snapshot':
            return self.read_snapshot()
        raise ValueError(f'不支持的 PLC 命令: {command}')

    def _ensure_connected(self):
        if not self.is_online():
            self.connect()

    def read_point(self, name):
        point = POINTS_BY_NAME[name]
        self._ensure_connected()
        data = self.transport.read(DB_NUMBER, point.offset, point.size)
        return decode_value(point, data)

    def write_point(self, name, value):
        point = POINTS_BY_NAME[name]
        self._ensure_connected()
        data = encode_value(point, value)
        if point.data_type == 'BOOL':
            current = bytearray(self.transport.read(DB_NUMBER, point.offset, 1))
            mask = 1 << point.bit
            current[0] = (current[0] | mask) if bool(value) else (current[0] & ~mask)
            data = bytes(current)
        self.transport.write(DB_NUMBER, point.offset, data)

    def read_snapshot(self):
        self._ensure_connected()
        raw = self.transport.read(DB_NUMBER, 0, DB_SIZE)
        return {
            name: decode_value(point, raw[point.offset:point.offset + point.size])
            for name, point in POINTS_BY_NAME.items()
            if point.direction == 'IN' or name == 'heartbeat'
        }

    def tick_heartbeat(self):
        current = self.read_point('heartbeat')
        value = -32768 if current >= 32767 else current + 1
        self.write_point('heartbeat', value)
        return value

    def read_signal(self, signal_name):
        return self.read_point(signal_name)

    def write_signal(self, signal_name, value):
        self.write_point(signal_name, value)
        return True
    
    def read_robot_pose(self, robot_code: str = 'ROBOT-01') -> dict:
        """
        从PLC读取机器人当前位姿（T_base_flange）
        
        Args:
            robot_code: 机器人设备代码
            
        Returns:
            机器人位姿字典 {
                'success': bool,
                'pose': {'x': float, 'y': float, 'z': float, 'rx': float, 'ry': float, 'rz': float},
                'timestamp': str
            }
        """
        raise NotImplementedError

    def send_rack_offsets(self, payload: dict) -> dict:
        """下发料架三轴补偿数据到 PLC。

        兼容两种 payload 格式：

        旧格式（双料架全扫描，由 RackLocator.plc_payload 提供）：
            side            : 'LEFT' | 'RIGHT'
            offset_x/y/z    : float (mm)
            layer_count     : int
            layer_heights   : list[float]
            layer_spacings  : list[float]
            confidence      : float (0~1)
            recipe_matched  : bool
            product_code    : str

        新格式（3D 单点位补偿，由 RackLocationOutput.to_payload 提供）：
            task_kind       : 'RACK_3D_LOCATION'
            side            : 'LEFT' | 'RIGHT' | 'BOTH'
            position_no     : int
            layer_no        : int
            locate_ok       : bool
            offset_x/y/z    : float (mm)
            offset_rz       : float (deg)
            confidence      : float (0~1)
            compensation_valid : bool

        返回：
            {success: bool, sent_at: str, echo: payload}
        """
        delta_z = payload.get('layer_delta_z')
        if delta_z is None:
            delta_z = payload.get('compensation_z', payload.get('offset_z'))
        if delta_z is None:
            return {'success': False, 'error': 'DB100 规则要求下发当前层 ΔZ'}
        self.write_point('layer_delta_z', delta_z)
        return {'success': True, 'echo': payload}

    def send_offsets(self, product_code, side, x, y, z):
        """已废弃，请改用 send_rack_offsets()。保留以兼容旧代码。"""
        raise NotImplementedError

    def send_workstation_lock(self, reason):
        self.write_point('workstation_locked', True)
        return {'success': True, 'locked': True, 'reason': reason}

    def send_workstation_unlock(self):
        self.write_point('workstation_locked', False)
        return {'success': True, 'locked': False}
