"""Server-owned continuous camera pipeline. Browser closure does not stop capture.

Acquisition overwrites one latest-frame slot; inference never builds a backlog.
Detection is read-only with respect to PLC. No foam result writes are enabled.
"""
import atexit
import copy
import threading
import time
import uuid

from .algorithms.foam_stream import FoamStreamInspector
from .foam_video_sessions import profile_path, encode_preview


class LiveFoamRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.halt = threading.Event()
        self.changed = threading.Event()
        self.threads = []
        self.latest = None
        self.result = None
        self.image = None
        self.error = ''
        self.generation = 0
        self.started_at = None
        self.result_at = 0
        self.ng_event = 0
        self.preview = None
        self.preview_at = 0
        self.processing_fps = 0
        self.session_id = uuid.uuid4().hex
        self.processing_error = ''

    def set_manual(self, enabled):
        from apps.devices.plc_position_debug import ownership, active
        # The same cross-process lock guards a complete automatic dispatch.
        # Never acknowledge a pause while that dispatch is still executing.
        with ownership() as (state, save):
            if enabled and not state.get('foam_manual') and active(state):
                raise ValueError('其他工序正在调试，请先退出该调试')
            self.start()
            state['foam_manual'] = bool(enabled)
            save()
            self.reset()

    @staticmethod
    def manual_status():
        from apps.devices.plc_position_debug import ownership
        with ownership() as (state, save):
            return bool(state.get('foam_manual'))

    def start(self):
        with self.lock:
            if any(t.is_alive() for t in self.threads):
                if self.halt.is_set():
                    raise RuntimeError('相机正在停止，请稍后重试')
                return
            detector = FoamStreamInspector(profile_path())
            from apps.devices.adapters.camera import CameraAdapter
            with CameraAdapter._capture_lock:
                if CameraAdapter._stream_active:
                    raise RuntimeError('2D 相机已有连续采集任务')
                CameraAdapter._stream_active = True
            self.detector = detector
            self.halt.clear()
            self.changed.clear()
            self.latest = self.result = self.image = None
            self.preview = None
            self.preview_at = 0
            self.processing_fps = 0
            self.result_at = 0
            self.error = ''
            self.processing_error = ''
            self.started_at = time.monotonic()
            self.generation += 1
            self.threads = [threading.Thread(target=self._capture,name='foam-live-capture',daemon=True),
                            threading.Thread(target=self._process,name='foam-live-detect',daemon=True)]
            for thread in self.threads:
                thread.start()

    def stop(self):
        self.halt.set()
        self.changed.set()
        for thread in self.threads:
            thread.join(timeout=1)

    def reset(self):
        with self.lock:
            if any(t.is_alive() for t in self.threads):
                self.generation += 1
                self.result = self.image = None
                self.result_at = 0

    def _capture(self):
        from apps.devices.adapters.camera import CameraAdapter
        adapter = CameraAdapter()
        index = 0
        try:
            while not self.halt.is_set():
                with self.lock:
                    generation = self.generation
                try:
                    raw = adapter.acquire_frame('CAM-INSPECT-FOAM-01','FOAM_INSPECTION',continuous=True)
                    image = adapter.decode_frame(raw)
                    now = time.monotonic()
                    preview = encode_preview(image) if now-self.preview_at >= .1 else None
                except Exception as exc:
                    with self.lock:
                        self.error = f'相机断流，正在重连：{exc}'
                        self.latest = None
                        self.result_at = 0
                    if self.halt.wait(2):
                        break
                    continue
                with self.lock:
                    if generation != self.generation:
                        continue
                    self.error = ''
                    self.latest = (index,now,image,generation)
                    if preview is not None:
                        self.preview, self.preview_at = preview, now
                index += 1
                self.changed.set()
        except Exception as exc:
            with self.lock:
                self.error = f'连续采集失败：{exc}'
            self.halt.set()
            self.changed.set()
        finally:
            with CameraAdapter._capture_lock:
                CameraAdapter.close_worker()
                CameraAdapter._stream_active = False

    def _process(self):
        last_index, generation = -1, -1
        try:
            while not self.halt.is_set():
                self.changed.wait(.2)
                self.changed.clear()
                with self.lock:
                    latest = self.latest
                    current_generation = self.generation
                if latest is None or latest[0] == last_index:
                    continue
                index, timestamp, frame, gen = latest
                if gen != current_generation:
                    continue
                if gen != generation:
                    self.detector.reset()
                    generation = gen
                try:
                    result = self.detector.process(frame,timestamp=timestamp-self.started_at,frame_id=index)
                    preview = encode_preview(frame,result)
                except Exception as exc:
                    with self.lock:
                        self.processing_error = f'检测异常，正在重试：{exc}'
                        self.result = self.image = None
                        self.result_at = 0
                    generation = -1
                    last_index = index
                    self.halt.wait(.2)
                    continue
                if result['state'] == 'FALLEN':
                    from .foam_ng_log import record
                    # Never publish or discard a confirmed NG before its audit is durable.
                    while not self.halt.is_set():
                        try:
                            record(f'{self.session_id}:{gen}:{index}', result)
                            break
                        except Exception as exc:
                            with self.lock:
                                self.processing_error = f'NG 日志保存失败，正在重试：{exc}'
                            self.halt.wait(1)
                    if self.halt.is_set():
                        break
                with self.lock:
                    if gen != self.generation:
                        continue
                    previous = self.result or {}
                    if result['state'] == 'FALLEN' and previous.get('state') != 'FALLEN':
                        self.ng_event += 1
                    self.result, self.image = result, preview
                    self.processing_error = ''
                    self.processing_fps = 1 / max(.001, timestamp-self.result_at) if self.result_at else 0
                    self.result_at = timestamp
                last_index = index
        except Exception as exc:
            with self.lock:
                self.error = f'连续检测失败：{exc}'
            self.halt.set()

    def status(self):
        with self.lock:
            age = time.monotonic()-self.result_at if self.result_at else None
            running = bool(self.threads) and not self.halt.is_set() and all(t.is_alive() for t in self.threads)
            stale = not running or bool(self.error or self.processing_error) or age is None or age > 2
            preview_stale = not running or bool(self.error) or time.monotonic()-self.preview_at > 2
            return {'running':running,'stopping':self.halt.is_set() and any(t.is_alive() for t in self.threads),
                    'error':self.error,'processing_error':self.processing_error,'result':None if stale else copy.deepcopy(self.result),
                    'image':None if preview_stale else self.preview,
                    'result_image':None if stale else self.image,
                    'processing_fps':self.processing_fps if not stale else 0,
                    'preview_stale':preview_stale,
                    'stale':stale,'age_seconds':age,
                    'ng_event':self.ng_event,'generation':self.generation}


runtime = LiveFoamRuntime()
atexit.register(runtime.stop)


def start_automatic():
    """Serving entry points only; external deployments do not start AGV hardware."""
    import logging
    from django.conf import settings
    if getattr(settings, 'FOAM_STREAM_AUTO_START', False):
        try:
            runtime.start()
        except Exception as exc:
            with runtime.lock:
                runtime.error = f'连续泡棉检测启动失败：{exc}'
            logging.getLogger(__name__).exception('连续泡棉检测启动失败，其他服务继续运行')
