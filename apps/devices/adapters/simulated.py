"""模拟设备适配器：在无现场设备时跑通页面与流程。

模拟能力：固定产品条码、料框码、打标结果、视觉相关触发，以及可注入的
扫码失败、设备离线等异常。所有设备访问都应经过适配器，业务代码不直接
调用协议细节。
"""
from .base import BaseDeviceAdapter


class SimulatedDeviceAdapter(BaseDeviceAdapter):
    """Deterministic adapter for developing without shop-floor equipment."""

    def __init__(self, *, online=True, fail_product_scan=False, fail_rack_scan=False,
                 mark_ok=True, product_code='P-DEMO-0001', rack_code='RK-DEMO-01'):
        self.online = online
        self.fail_product_scan = fail_product_scan
        self.fail_rack_scan = fail_rack_scan
        self.mark_ok = mark_ok
        self._product_code = product_code
        self._rack_code = rack_code
        self._connected = False

    # --- 基础接口 ---
    def connect(self):
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False
        return True

    def is_online(self):
        return self.online

    def read(self, key):
        return {'key': key, 'online': self.online}

    def write(self, key, value):
        return True

    def execute(self, command, payload=None):
        return {'command': command, 'payload': payload or {}, 'success': True}

    # --- 扫码枪 ---
    def read_product_code(self):
        if self.fail_product_scan:
            return {'success': False, 'error': '产品条码读取失败'}
        return {'success': True, 'code': self._product_code}

    def read_rack_code(self):
        if self.fail_rack_scan:
            return {'success': False, 'error': '料框码读取失败'}
        return {'success': True, 'code': self._rack_code}

    # --- 激光打标机 ---
    def trigger_mark(self, product_code):
        return {'success': True, 'triggered': True, 'product_code': product_code}

    def get_mark_result(self):
        if self.mark_ok:
            return {'success': True, 'result': 'OK'}
        return {'success': False, 'error': '打标失败'}

    # --- 相机 ---
    def capture(self, camera_code, task_type):
        return {
            'success': True,
            'camera_code': camera_code,
            'task_type': task_type,
            'image_path': '',
            'width': 1280,
            'height': 720,
        }

    # --- PLC 控制信号 ---
    def send_offsets(self, product_code, side, x, y, z):
        return {'success': True, 'product_code': product_code, 'side': side,
                'x': x, 'y': y, 'z': z}

    def send_workstation_lock(self, reason):
        return {'success': True, 'locked': True, 'reason': reason}

    def send_workstation_unlock(self):
        return {'success': True, 'locked': False}

    # --- 泡棉供料台距离传感器 ---
    def read_foam_height(self):
        return {'success': True, 'height_mm': 35.0}
