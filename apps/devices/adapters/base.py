class BaseDeviceAdapter:
    """Base interface for concrete device adapters."""

    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def is_online(self):
        raise NotImplementedError

    def read(self, key):
        raise NotImplementedError

    def write(self, key, value):
        raise NotImplementedError

    def execute(self, command, payload=None):
        raise NotImplementedError
