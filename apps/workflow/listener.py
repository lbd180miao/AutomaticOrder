"""Server-owned PLC polling; never starts during migrations or packaging."""
import atexit
import logging
from logging.handlers import RotatingFileHandler
import threading
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger('plc_listener')
_lock = threading.Lock()
_stop = threading.Event()
_thread = None


def poll_loop(stop, interval, retry_interval, factory=None):
    if factory is None:
        from .station_service import StationWorkflowService
        factory = StationWorkflowService
    service = None
    previous_phase = None
    try:
        while not stop.is_set():
            delay = interval
            try:
                close_old_connections()
                if service is None:
                    service = factory()
                    transport = service.plc.transport
                    logger.info('PLC 监听目标 %s:%s Rack=%s Slot=%s DB=2',
                                getattr(transport, 'address', 'memory'),
                                getattr(transport, 'tcp_port', 102),
                                getattr(transport, 'rack', 0), getattr(transport, 'slot', 1))
                cycle, changed = service.poll_once()
                phase = (cycle.pk, cycle.phase) if cycle else None
                if changed or phase != previous_phase:
                    logger.info('PLC 工位状态 %s changed=%s', phase, changed)
                    previous_phase = phase
            except Exception:
                logger.exception('PLC 监听失败，%s 秒后重新连接', retry_interval)
                if service is not None:
                    try:
                        service.devices.mark_offline(service.plc_device_code)
                    except Exception:
                        logger.exception('更新 PLC 离线状态失败')
                    try:
                        service.plc.disconnect()
                    except Exception:
                        logger.exception('关闭 PLC 连接失败')
                service = None
                previous_phase = None
                delay = retry_interval
            finally:
                close_old_connections()
            stop.wait(delay)
    finally:
        if service is not None:
            try:
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
        _stop.clear()
        _thread = threading.Thread(target=poll_loop, args=(_stop, 0.25, 5.0),
                                   name='plc-listener', daemon=True)
        _thread.start()
        atexit.register(stop_listener)
        logger.info('后台 PLC 监听已启动；扫描间隔 0.25 秒，失败重连间隔 5 秒')


def stop_listener(*, wait=True):
    with _lock:
        _stop.set()
        thread = _thread
    if wait and thread is not None:
        thread.join(timeout=3)
