"""Page-scoped PLC/camera handshake with a cross-process ownership lease."""
import json
import math
import os
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
    path = Path(getattr(settings, 'DATA_DIR', settings.BASE_DIR)) / 'logs' / 'plc_debug_ownership.json'
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
    """Capture once; persist and retry the result until PLC acknowledges the writes."""
    plc.tick_heartbeat()
    trigger = plc.read_point('position_trigger')
    state['trigger'] = trigger
    phase = state['phase']
    if not trigger:
        plc.write_point('position_done', False)
        plc.write_point('position_success', False)
        state.pop('pending_result', None)
        state.update(phase='WAIT_TRIGGER', message='等待 PLC 3D 触发', done=False, ok=False)
        return
    if phase in ('ARMING', 'WAIT_RESET'):
        state['message'] = '等待 PLC 将 DB2.DBX46.2 复位为 0'
        return
    if phase == 'CAPTURING':
        # A previous request died after consuming the trigger. Never capture it twice.
        state['pending_result'] = {
            'ok': False, 'error': '上次采集被中断，回写失败结果',
            'values': dict.fromkeys(('x', 'y', 'z', 'x2', 'y2', 'z2'), POSITION_FAILURE_OFFSET),
        }
    elif phase != 'WRITE_PENDING':
        state.update(phase='CAPTURING', message='正在采集点云并计算双组三轴补偿',
                     error='', values=None, result_id=None, done=False, ok=False)
        save()
        try:
            plc.write_point('position_done', False)
            plc.write_point('position_success', False)
            result = capture(state['recipe_id'], state['layer_no'])
            state['result_id'] = result.get('result_id')
            if not result.get('is_success'):
                raise ValueError(result.get('error_message') or '3D 定位失败')
            from .plc_db100 import position_values
            values = position_values(result)
            pending = {'ok': True, 'error': '', 'values': values}
        except Exception as exc:
            pending = {'ok': False, 'error': str(exc),
                       'values': dict.fromkeys(('x', 'y', 'z', 'x2', 'y2', 'z2'), POSITION_FAILURE_OFFSET)}
        state['pending_result'] = pending
    state['phase'] = 'WRITE_PENDING'
    save()
    pending = state['pending_result']

    def verified(name, value):
        plc.write_point(name, value)
        if plc.read_point(name) != value:
            raise ValueError(f'{name} 写后回读不一致')

    try:
        verified('position_done', False)
        verified('position_success', False)
        for axis, value in pending['values'].items():
            verified(f'layer_delta_{axis}', value)
        verified('position_success', pending['ok'])
        verified('position_done', True)
    except Exception as exc:
        state.update(done=False, ok=False, error=f"{pending['error']}；PLC回写失败：{exc}".lstrip('；'),
                     message='结果尚未完整回写，将重试回写，不重复拍照')
        save()
        return
    state.update(phase='WAIT_RESET', values=pending['values'], ok=pending['ok'], done=True,
                 error=pending['error'], count=state.get('count', 0) + 1,
                 completed_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                 message=('定位成功，双组三轴补偿已回写；等待 PLC 复位' if pending['ok'] else
                          '定位失败，两组X/Y/Z已回写999；等待PLC复位后重试'))
    state.pop('pending_result', None)
    save()


def capture_position(recipe_id, layer_no):
    from apps.vision.models import RackLocationRecipe
    simulated = getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True)
    recipe = RackLocationRecipe.objects.get(pk=recipe_id, enabled=True)
    if not 1 <= layer_no <= recipe.layer_count:
        raise ValueError('当前层号超出配方范围')
    if (recipe.roi_config or {}).get('local_template_rois') or (recipe.roi_config or {}).get('spatial_rois'):
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
        return dual_group_position(result, recipe)
    return {'is_success': False, 'error_message': '当前配方未配置双组定位，请完成双组标准与标定'}


def dual_group_position(result, recipe):
    """Map A/B robot-base translations to both PLC XYZ groups (mm)."""
    try:
        if not result.get('locate_ok'):
            raise ValueError(result.get('error_message') or '3D 定位失败')
        values = {}
        for name, suffix in (('A', ''), ('B', '2')):
            group = (result.get('robot_groups') or {}).get(name)
            if not group:
                raise ValueError(f'缺少{name}组机器人补偿，请保存双组标准及手眼标定')
            if group.get('coordinate_system') != 'robot_base':
                raise ValueError(f'{name}组补偿不是机器人基坐标，禁止回写')
            for axis in 'xyz':
                value = float(group['translation_mm'][axis])
                limit = float(getattr(recipe, f'max_offset_{axis}'))
                if not math.isfinite(value) or not math.isfinite(limit) or abs(value) > limit:
                    raise ValueError(f'{name}组 Δ{axis.upper()} 超出配方限值或数值无效')
                values[f'compensation_{axis}{suffix}'] = value
            rz = float(group['rotation_deg']['rz'])
            limit = float(recipe.max_offset_rz)
            if not math.isfinite(rz) or not math.isfinite(limit) or abs(rz) > limit:
                raise ValueError(f'{name}组 Rz 超出配方限值或数值无效')
        return {'result_id': result.get('result_id'), 'is_success': True,
                'error_message': '', 'compensation_group': 'A+B', **values}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {'result_id': result.get('result_id'), 'is_success': False,
                'error_message': str(exc), 'compensation_group': 'A+B'}


# Compatibility for callers using the previous helper name.
first_group_position = dual_group_position
