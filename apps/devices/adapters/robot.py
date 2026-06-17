from .base import BaseDeviceAdapter


class RobotAdapter(BaseDeviceAdapter):
    """Robot adapter placeholder. Usually called through PLC or vendor SDK."""

    def move_to(self, position):
        raise NotImplementedError

    def confirm_vacuum(self):
        raise NotImplementedError

    def release(self):
        raise NotImplementedError
