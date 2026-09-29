"""Page-scoped PLC/camera handshake with a cross-process ownership lease."""
import json
import math
import os
import struct
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


class DebugBusy(RuntimeError):
    pass


def active(state):
    return state.get('expires', 0) > time.time()


@contextmanager
def ownership():
    # One byte remains locked even when the JSON payload is rewritten.
    path = Path(settings.BASE_DIR) / 'logs' / 'plc_debug_ownership.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as initial:
        if initial.tell() == 0:
            initial.write(b' {}')
    with path.open('r+b') as handle:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise DebugBusy('PLC 操作正在执行，请稍后重试') from exc
        try:
            handle.seek(1)
            state = json.loads(handle.read() or b'{}')

            def save():
                handle.seek(1)
                handle.write(json.dumps(state, ensure_ascii=False).encode('utf-8'))
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())

            yield state, save
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def step(state, plc, capture, save=lambda: None):
    """One scan. Persist the consumed trigger before any camera operation."""
    if time.time() - state.get('heartbeat_at', 0) >= 1:
        plc.tick_heartbeat()
        state['heartbeat_at'] = time.time()
    trigger = plc.read_point('position_trigger')
    state['trigger'] = trigger
    phase = state['phase']
    if not trigger:
        plc.write_point('position_done', False)
        plc.write_point('position_success', False)
        state.update(phase='WAIT_TRIGGER', message='等待 PLC 3D 触发', done=False, ok=False)
        return
    if phase in ('ARMING', 'WAIT_RESET', 'CAPTURING'):
        state['message'] = '等待 PLC 将 DB2.DBX46.2 复位为 0'
        return
    state.update(phase='CAPTURING', message='正在采集点云并计算三轴补偿', error='', values=None)
    save()
    try:
        plc.write_point('position_done', False)
        plc.write_point('position_success', False)
        result = capture(state['recipe_id'], state['layer_no'])
        state['result_id'] = result.get('result_id')
        if not result.get('is_success'):
            raise ValueError(result.get('error_message') or '3D 定位失败')
        values = {}
        for axis in 'xyz':
            value = float(result[f'compensation_{axis}'])
            if not math.isfinite(value):
                raise ValueError('三轴补偿包含无效数值')
            values[axis] = struct.unpack('>f', struct.pack('>f', value))[0]
        # All three values are validated before writing; done is always last.
        for axis, value in values.items():
            plc.write_point(f'layer_delta_{axis}', value)
        for axis, value in values.items():
            if plc.read_point(f'layer_delta_{axis}') != value:
                raise ValueError(f'Δ{axis.upper()} 写后回读不一致')
        plc.write_point('position_success', True)
        plc.write_point('position_done', True)
        state.update(values=values, ok=True, done=True, message='定位成功，三轴补偿已回写；等待 PLC 复位')
    except Exception as exc:
        state.update(ok=False, done=False, error=str(exc), message='定位失败；等待 PLC 复位后重试')
        try:
            plc.write_point('position_success', False)
            plc.write_point('position_done', True)
            state['done'] = True
        except Exception as write_exc:
            state['error'] += f'；失败信号回写失败：{write_exc}'
    finally:
        state['phase'] = 'WAIT_RESET'
        state['count'] = state.get('count', 0) + 1
        state['completed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')


def capture_position(recipe_id, layer_no):
    from apps.vision.rack_3d.services import RackPositioningService
    simulated = getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True)
    # Never allow the global MOCK camera default to feed a real PLC.
    return RackPositioningService(mode='MOCK' if simulated else 'REAL').execute_positioning(
        recipe_id, layer_no, save=True,
    )
