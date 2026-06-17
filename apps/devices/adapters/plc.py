from .base import BaseDeviceAdapter


class PLCAdapter(BaseDeviceAdapter):
    """PLC adapter placeholder. Replace with site protocol (Modbus/OPC UA/Socket)."""

    def read_signal(self, signal_name):
        raise NotImplementedError

    def write_signal(self, signal_name, value):
        raise NotImplementedError

    def send_rack_offsets(self, payload: dict) -> dict:
        """下发料架三轴补偿及分层数据到 PLC。

        payload 结构（由 RackLocator.plc_payload 直接提供）：
            side            : 'LEFT' | 'RIGHT'
            offset_x/y/z    : float (mm)
            layer_count     : int
            layer_heights   : list[float]
            layer_spacings  : list[float]
            confidence      : float (0~1)
            recipe_matched  : bool
            product_code    : str

        返回：
            {success: bool, sent_at: str, echo: payload}
        """
        raise NotImplementedError

    def send_offsets(self, product_code, side, x, y, z):
        """已废弃，请改用 send_rack_offsets()。保留以兼容旧代码。"""
        raise NotImplementedError

    def send_workstation_lock(self, reason):
        raise NotImplementedError

    def send_workstation_unlock(self):
        raise NotImplementedError
