from .base import BaseDeviceAdapter


class CameraAdapter(BaseDeviceAdapter):
    """Camera adapter placeholder for OpenCV or vendor SDK capture."""

    def capture(self, camera_code, task_type):
        """Trigger capture and return image path plus metadata."""
        raise NotImplementedError
