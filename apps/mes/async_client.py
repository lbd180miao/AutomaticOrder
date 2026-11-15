"""Nonblocking adapter for direct REST/SOAP clients used by the PLC listener."""
from concurrent.futures import ThreadPoolExecutor
from .remote_client import RemoteMesClient, RemotePending


class AsyncDirectMesClient(RemoteMesClient):
    def __init__(self, client):
        self.client = client
        self.nonblocking = True
        self.context_cycle = None
        self.context_request = None
        self._jobs = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='mes-http')

    def _invoke(self, method, *args):
        import json
        key = (self.context_cycle, self.context_request, method,
               json.dumps(args, sort_keys=True, default=str))
        if key not in self._jobs:
            self._jobs[key] = self._executor.submit(getattr(self.client, method), *args)
        future = self._jobs[key]
        if not future.done():
            raise RemotePending()
        # Retain completed response so a resumed handler never repeats HTTP.
        return future.result()

    def get_rack_recipe(self, rack_code):
        return self._invoke('get_rack_recipe', rack_code)

    def upload_product_barcode(self, product_code, rack_code):
        return self._invoke('upload_product_barcode', product_code, rack_code)

    def upload_boxing_result(self, payload):
        return self._invoke('upload_boxing_result', payload)

    def upload_vision_result(self, payload):
        return self._invoke('upload_vision_result', payload)

    def upload_alarm(self, payload):
        return self._invoke('upload_alarm', payload)
