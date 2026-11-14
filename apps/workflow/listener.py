"""Server-owned PLC polling; never starts during migrations or packaging."""
import atexit
import logging
from logging.handlers import RotatingFileHandler
import threading
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections

from apps.devices.plc_db100 import PLC_SCAN_INTERVAL

logger = logging.getLogger('plc_listener')
_lock = threading.Lock()
_stop = threading.Event()
_thread = None
_input_status = {}
_debug_lock = threading.Lock()
_debug_enabled = False
_debug_generation = uuid.uuid4().hex


def debug_status():
    with _debug_lock:
        return {'enabled': _debug_enabled, 'generation': _debug_generation}


def set_debug_enabled(enabled):
    global _debug_enabled, _debug_generation
    with _debug_lock:
        if _debug_enabled != enabled:
            _debug_enabled = enabled
            _debug_generation = uuid.uuid4().hex
        return {'enabled': _debug_enabled, 'generation': _debug_generation}



def publish_inputs(sample=None, error=''):
    from django.utils import timezone
    global _input_status
    _input_status = {'values': dict(sample or {}), 'error': error,
                     'checked_at': timezone.now().isoformat(), 'sampled_at': time.monotonic()}


def input_status():
    return dict(_input_status)


class PLCInputSampler:
    """Keep sampling while the workflow is busy capturing/calculating images."""
    def __init__(self, plc, interval=PLC_SCAN_INTERVAL):
        from collections import deque
        self.plc = plc
        self.interval = interval
        self.stop = threading.Event()
        self.lock = threading.Lock()
        plc.tick_heartbeat()
        self.latest = plc.read_listener_snapshot()
        publish_inputs(self.latest)
        self.samples = deque([self.latest])
        self.error = None
        self.thread = threading.Thread(target=self._run, name='plc-inputs', daemon=True)
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat, name='plc-heartbeat', daemon=True)
        self.heartbeat_thread.start()
        self.thread.start()

    def _heartbeat(self):
        while not self.stop.wait(0.5):
            try:
                self.plc.tick_heartbeat()
            except Exception as exc:
                publish_inputs(error=str(exc))
                with self.lock:
                    self.error = exc
                return

    def _run(self):
        while not self.stop.wait(self.interval):
            try:
                sample = self.plc.read_listener_snapshot()
                publish_inputs(sample)
                with self.lock:
                    if sample != self.latest:
                        self.samples.append(sample)
                    self.latest = sample
            except Exception as exc:
                publish_inputs(error=str(exc))
                with self.lock:
                    self.error = exc
                return

    def drain(self):
        with self.lock:
            # Deliver already observed edges before reporting a later disconnect.
            # Otherwise a low/high pulse during camera work can vanish on reconnect.
            if self.error is not None and not self.samples:
                raise self.error
            samples = list(self.samples) or [self.latest]
            self.samples.clear()
            return samples

    def close(self):
        self.stop.set()
        self.thread.join()
        self.heartbeat_thread.join()


def poll_loop(stop, interval, retry_interval, factory=None):
    if factory is None:
        from .station_service import StationWorkflowService
        factory = StationWorkflowService
    from apps.devices.listener_logs import record, cleanup
    service = None
    previous_phase = None
    connection_reported = False
    try:
        while not stop.is_set():
            delay = max(PLC_SCAN_INTERVAL, interval)
            try:
                close_old_connections()
                cleanup()
                if service is None:
                    service = factory()
                    service.input_sampler = PLCInputSampler(service.plc)
                    transport = service.plc.transport
                    logger.info('PLC 监听目标 %s:%s Rack=%s Slot=%s DB=2',
                                getattr(transport, 'address', 'memory'),
                                getattr(transport, 'tcp_port', 102),
                                getattr(transport, 'rack', 0), getattr(transport, 'slot', 1))
                cycle, changed = service.poll_once()
                if not connection_reported and getattr(service, 'last_scan_succeeded', False):
                    record('connection', 'PLC 扫描成功，监听运行中')
                    connection_reported = True
                phase = (cycle.pk, cycle.phase) if cycle else None
                if changed or phase != previous_phase:
                    logger.info('PLC 工位状态 %s changed=%s', phase, changed)
                    previous_phase = phase
            except Exception as exc:
                publish_inputs(error=str(exc))
                record('connection', f'[报警] PLC 监听失败，{retry_interval} 秒后重连：{exc}')
                logger.exception('PLC 监听失败，%s 秒后重新连接', retry_interval)
                if service is not None:
                    try:
                        service.devices.mark_offline(service.plc_device_code)
                    except Exception:
                        logger.exception('更新 PLC 离线状态失败')
                    try:
                        if getattr(service, 'input_sampler', None):
                            service.input_sampler.close()
                        service.plc.disconnect()
                    except Exception:
                        logger.exception('关闭 PLC 连接失败')
                service = None
                previous_phase = None
                connection_reported = False
                delay = max(PLC_SCAN_INTERVAL, retry_interval)
            finally:
                close_old_connections()
            stop.wait(delay)
    finally:
        if service is not None:
            try:
                if getattr(service, 'input_sampler', None):
                    service.input_sampler.close()
                service.plc.disconnect()
            except Exception:
                logger.exception('停止 PLC 连接失败')
        close_old_connections()


def listener_running():
    return _thread is not None and _thread.is_alive() and not _stop.is_set()


def listener_stopping():
    return _thread is not None and _thread.is_alive() and _stop.is_set()


def start_listener(*, manual=False):
    global _thread
    if not manual and not getattr(settings, 'PLC_LISTENER_AUTO_START', False):
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        log_path = Path(settings.DATA_DIR) / 'logs' / 'plc-listener.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not logger.handlers:
            handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
            handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(message)s'))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        set_debug_enabled(False)
        _stop.clear()
        publish_inputs()
        _thread = threading.Thread(target=poll_loop, args=(_stop, PLC_SCAN_INTERVAL, 5.0),
                                   name='plc-listener', daemon=True)
        _thread.start()
        atexit.register(stop_listener)
        logger.info('后台 PLC 监听已启动；扫描间隔 0.5 秒，失败重连间隔 5 秒')


def stop_listener(*, wait=True):
    with _lock:
        set_debug_enabled(False)
        _stop.set()
        thread = _thread
    if wait and thread is not None:
        thread.join(timeout=3)
