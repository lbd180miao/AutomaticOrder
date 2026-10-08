"""Page-scoped PLC/camera handshake with a cross-process ownership lease."""
import json
import math
import os
import struct
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from .plc_db100 import POSITION_FAILURE_OFFSET


class DebugBusy(RuntimeError):
    pass


def active(state):
    return (state.get('expires', 0) > time.time()
            or any(active(session) for session in state.get('sessions', {}).values()))


@contextmanager
def ownership(mode=None):
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

            if mode is None:
                yield state, save
            else:
                # Preserve leases created before the two-channel format was introduced.
                if 'sessions' not in state:
                    previous = dict(state)
                    state.clear()
                    state['sessions'] = ({previous.get('mode', 'position'): previous}
                                         if previous.get('token') else {})
                sessions = state['sessions']
                session = sessions.setdefault(mode, {})
                waiting = [other for name, other in sessions.items()
                           if name != mode and active(other)]
                last_saved = time.monotonic()

                def save_session():
                    nonlocal last_saved
                    now = time.monotonic()
                    # The other channel cannot renew while this PLC lock is held.
                    for other in waiting:
                        other['expires'] += now - last_saved
                    last_saved = now
                    save()

                try:
                    yield session, save_session
                finally:
                    save_session()
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
    state.update(phase='CAPTURING', message='正在采集点云并计算三轴补偿', error='', values=None, result_id=None)
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
        if plc.read_point('position_success') is not True:
            raise ValueError('定位成功标志写后回读不一致')
        plc.write_point('position_done', True)
        if plc.read_point('position_done') is not True:
            raise ValueError('定位完成标志写后回读不一致')
        state.update(values=values, ok=True, done=True, message='定位成功，三轴补偿已回写；等待 PLC 复位')
    except Exception as exc:
        state.update(ok=False, done=False, values=None, error=str(exc), message='定位失败，正在回写三轴失败值999')
        try:
            plc.write_point('position_done', False)
            plc.write_point('position_success', False)
            if plc.read_point('position_success') is not False:
                raise ValueError('定位失败标志写后回读不一致')
            failed_values = dict.fromkeys('xyz', POSITION_FAILURE_OFFSET)
            for axis, value in failed_values.items():
                plc.write_point(f'layer_delta_{axis}', value)
            for axis, value in failed_values.items():
                if plc.read_point(f'layer_delta_{axis}') != value:
                    raise ValueError(f'Δ{axis.upper()} 失败值999写后回读不一致')
            state['values'] = failed_values
            plc.write_point('position_done', True)
            if plc.read_point('position_done') is not True:
                raise ValueError('定位完成标志写后回读不一致')
            state['done'] = True
            state['message'] = '定位失败，X/Y/Z已回写999；等待PLC复位后重试'
        except Exception as write_exc:
            state['error'] += f'；失败信号回写失败：{write_exc}'
            state['message'] = '定位失败且PLC失败结果未完整回写，请检查连接'
    finally:
        state['phase'] = 'WAIT_RESET'
        state['count'] = state.get('count', 0) + 1
        state['completed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')


def capture_position(recipe_id, layer_no):
    from apps.vision.models import RackLocationRecipe
    from apps.vision.rack_3d.services import RackPositioningService
    simulated = getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True)
    recipe = RackLocationRecipe.objects.get(pk=recipe_id, enabled=True)
    if not 1 <= layer_no <= recipe.layer_count:
        raise ValueError('当前层号超出配方范围')
    if (recipe.roi_config or {}).get('local_template_rois'):
        # 三平面配方与工作台使用同一采集/计算链路，不能送入需要另一套
        # RackLocationROI3DEnhanced 配置的旧定位算法。
        from apps.vision.rack_location import Rack3DLocator, RackLocationService, SampleRackFrameProvider
        provider = SampleRackFrameProvider() if simulated else None
        captured = Rack3DLocator(frame_provider=provider).capture(recipe_id=recipe_id, layer_no=layer_no)
        if not simulated and captured.get('source') != 'rvc_camera':
            raise ValueError('真实3D采集失败：' + (captured.get('fallback_reason') or '未取得真实相机点云'))
        result = RackLocationService().calculate_workbench(
            token=captured['pointcloud_token'], roi_config=recipe.roi_config,
            recipe_id=recipe_id, layer_no=layer_no, save_record=True,
        )
        payload = result.get('plc_payload') or {}
        valid = bool(result.get('locate_ok') and payload.get('compensation_valid'))
        return {
            'result_id': result.get('result_id'),
            'is_success': valid,
            'error_message': '' if valid else (
                result.get('error_message') or result.get('warning_message') or '补偿无效，请检查标准模板及配方限值'
            ),
            **{f'compensation_{axis}': payload.get(f'offset_{axis}') for axis in 'xyz'},
        }
    # Never allow the global MOCK camera default to feed a real PLC.
    return RackPositioningService(mode='MOCK' if simulated else 'REAL').execute_positioning(
        recipe_id, layer_no, save=True,
    )
