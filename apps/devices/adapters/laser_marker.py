from .base import BaseDeviceAdapter


class LaserMarkerAdapter(BaseDeviceAdapter):
    """Laser marker adapter placeholder (PLC trigger or marker SDK)."""

    def trigger_mark(self, product_code):
        raise NotImplementedError

    def get_mark_result(self):
        raise NotImplementedError
