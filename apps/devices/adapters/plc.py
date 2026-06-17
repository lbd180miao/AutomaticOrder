from .base import BaseDeviceAdapter


class PLCAdapter(BaseDeviceAdapter):
    """PLC adapter placeholder. Replace with site protocol (Modbus/OPC UA/Socket)."""

    def read_signal(self, signal_name):
        raise NotImplementedError

    def write_signal(self, signal_name, value):
        raise NotImplementedError

    def send_offsets(self, product_code, side, x, y, z):
        raise NotImplementedError

    def send_workstation_lock(self, reason):
        raise NotImplementedError

    def send_workstation_unlock(self):
        raise NotImplementedError
