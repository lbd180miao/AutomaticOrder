from .base import BaseDeviceAdapter


class ScannerAdapter(BaseDeviceAdapter):
    """Barcode scanner adapter placeholder (serial/TCP/PLC relay)."""

    def read_product_code(self):
        raise NotImplementedError

    def read_rack_code(self):
        raise NotImplementedError
