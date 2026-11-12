"""Page-scoped PLC/camera handshake with a cross-process ownership lease."""
import json
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from .plc_db100 import POSITION_FAILURE_OFFSET, PLC_SCAN_INTERVAL


class DebugBusy(RuntimeError):
    pass


def active(state):
    return (state.get('expires', 0) > time.time()
            or any(active(session) for session in state.get('sessions', {}).values()))


@contextmanager
def ownership(mode=None, *, scan=False, stopping=False):
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

            scanning = scan or mode is not None
            if scanning:
                previous = state.get('_scan_finished_at', 0)
                elapsed = time.monotonic() - previous
                if previous and 0 <= elapsed < PLC_SCAN_INTERVAL:
                    time.sleep(PLC_SCAN_INTERVAL - elapsed)

            if mode is None:
                try:
                    yield state, save
                finally:
                    if scanning:
                        state['_scan_finished_at'] = time.monotonic()
                        save()
            else:
                # Preserve leases created before the two-channel format was introduced.
                if 'sessions' not in state:
                    previous = dict(state)
                    state.clear()
                    if '_scan_finished_at' in previous:
                        state['_scan_finished_at'] = previous.pop('_scan_finished_at')
                    state['sessions'] = ({previous.get('mode', 'position'): previous}
                                         if previous.get('token') else {})
                sessions = state['sessions']
                if not stopping and any(name != mode and active(other)
                       for name, other in sessions.items()):
                    raise ValueError('已有其他工序正在轮询，请先停止该工序，再启动当前工序')
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
                    state['_scan_finished_at'] = time.monotonic()
                    save_session()
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def step(state, plc, capture, save=lambda: None):
    """Consume the request; publish capture completion before computing offsets."""
    plc.tick_heartbeat()
    trigger = plc.read_point('position_trigger')
    state['trigger'] = trigger
    phase = state['phase']
    if phase == 'ARMING':
        if not trigger:
            state.update(phase='WAIT_TRIGGER', message='等待 PLC 3D 触发')
        return
    if phase == 'WAIT_ACK':
        if plc.read_point('position_done') or plc.read_point('position_success'):
            return
        state.update(phase='WAIT_TRIGGER', message='等待下一次 3D 触发')
        save()
        return
    if phase == 'WAIT_TRIGGER' and (plc.read_point('position_done') or plc.read_point('position_success')):
        return
    if phase not in ('CAPTURING', 'WRITE_PENDING') and not trigger:
        return
    if phase == 'CAPTURING':
        # A previous request died after consuming the trigger. Never capture it twice.
        state['pending_result'] = {
            'ok': False, 'error': '上次采集被中断，回写失败结果',
            'values': dict.fromkeys(('x', 'y', 'z', 'x2', 'y2', 'z2'), POSITION_FAILURE_OFFSET),
        }
    elif phase != 'WRITE_PENDING':
        state.update(phase='CAPTURING', message='正在采集点云并计算双组三轴补偿',
                     error='', values=None, result_id=None, done=False, ok=False, capture_done=False)
        save()
        try:
            plc.write_point('position_done', False)
            plc.write_point('position_success', False)
            plc.write_point('position_trigger', False)
            state['trigger'] = False

            def captured():
                plc.write_point('position_done', True)
                state['capture_done'] = True
                save()

            result = capture(state['recipe_id'], state['layer_no'], on_captured=captured)
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
        verified('position_success', False)
        for axis, value in pending['values'].items():
            verified(f'layer_delta_{axis}', value)
        # PLC can consume/reset the valid bit immediately; only data needs readback.
        plc.write_point('position_success', pending['ok'])
    except Exception as exc:
        state.update(done=False, ok=False, error=f"{pending['error']}；PLC回写失败：{exc}".lstrip('；'),
                     message='结果尚未完整回写，将重试回写，不重复拍照')
        save()
        return
    state.update(phase='WAIT_ACK', values=pending['values'], ok=pending['ok'], done=True,
                 error=pending['error'], count=state.get('count', 0) + 1,
                 completed_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                 message=('补偿已回写，等待 PLC 读取并复位 49.1/49.2' if pending['ok'] else
                          '定位失败，两组X/Y/Z已回写999'))
    state.pop('pending_result', None)
    save()


def capture_position(recipe_id, layer_no, *, on_captured=None):
    from apps.vision.models import RackLocationRecipe
    recipe = RackLocationRecipe.objects.get(pk=recipe_id, enabled=True)
    if not 1 <= layer_no <= recipe.layer_count:
        raise ValueError('当前层号超出配方范围')
    if not (recipe.roi_config or {}).get('cloud_center_reference'):
        return {'is_success': False, 'error_message': '请先保存点云标准模板'}
    from apps.vision.rack_location import Rack3DLocator, RackLocationService
    captured = Rack3DLocator().capture(recipe_id=recipe_id, layer_no=layer_no)
    if on_captured is not None:
        on_captured()
    result = RackLocationService().calculate_workbench(
        token=captured['pointcloud_token'], recipe_id=recipe_id,
        layer_no=layer_no, save_record=True,
    )
    return dual_group_position(result, recipe)


def dual_group_position(result, recipe):
    """Map A/B robot-base translations to both PLC XYZ groups (mm)."""
    try:
        if result.get('plc_publish_allowed') is False:
            raise ValueError('点云匹配结果尚未允许 PLC 发布')
        if not result.get('locate_ok'):
            raise ValueError(result.get('error_message') or '3D 定位失败')
        values = {}
        for name, suffix in (('A', ''), ('B', '2')):
            group = (result.get('robot_groups') or {}).get(name)
            if name == 'B' and group is None:
                values.update({f'compensation_{axis}2': 0.0 for axis in 'xyz'})
                continue
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
