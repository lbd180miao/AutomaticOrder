import json
import logging
import math
import struct

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Device, DeviceSignalRecord
from apps.core.constants import DeviceType, DeviceStatus
from .plc_db100 import DB100_POINTS, DB_NUMBER


PLC_POINT_DEFINITIONS = DB100_POINTS
logger = logging.getLogger(__name__)


def _close_debug_plc(adapter):
    if adapter is not None and not getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True):
        try:
            adapter.disconnect()
        except Exception:
            logger.exception('PLC调试连接释放失败')

PLC_SCENES = (
    {
        'key': 'rack', 'number': 1, 'name': '料框入站检查',
        'subtitle': '料框码、MES 配方与可装箱判定',
        'phases': ('WAIT_RACK', 'WAIT_RACK_RESET', 'WAIT_RECIPE_VERIFY', 'WAIT_RECIPE_RESET'),
        'points': (
            ('料框到位触发', 'rack_trigger', 'DBX46.0', 'IN', 'trigger'),
            ('料框码', 'rack_barcode', 'DBB24', 'IN', 'text'),
            ('料框处理结果', 'rack_result', 'DBX48.6', 'OUT', 'result'),
            ('料框处理完成', 'rack_done', 'DBX48.5', 'OUT', 'done'),
            ('配方校验触发', 'recipe_verify_trigger', 'DBX46.1', 'IN', 'trigger'),
            ('可装箱结果', 'boxing_allowed', 'DBX49.0', 'OUT', 'result'),
            ('配方校验完成', 'recipe_verify_done', 'DBX48.7', 'OUT', 'done'),
        ),
    },
    {
        'key': 'position', 'number': 2, 'name': '料架定位补偿',
        'subtitle': '3D 定位与当前层 ΔZ 写入',
        'phases': ('WAIT_POSITION', 'WAIT_POSITION_RESET'),
        'points': (
            ('3D 定位触发', 'position_trigger', 'DBX46.2', 'IN', 'trigger'),
            ('当前层补偿 ΔX', 'layer_delta_x', 'DBD50', 'OUT', 'real'),
            ('当前层补偿 ΔY', 'layer_delta_y', 'DBD54', 'OUT', 'real'),
            ('当前层补偿 ΔZ', 'layer_delta_z', 'DBD58', 'OUT', 'real'),
            ('3D 定位结果', 'position_success', 'DBX49.2', 'OUT', 'result'),
            ('3D 定位完成', 'position_done', 'DBX49.1', 'OUT', 'done'),
        ),
    },
    {
        'key': 'product', 'number': 3, 'name': '产品装箱与泡棉检测',
        'subtitle': '产品条码、绑定与泡棉结果记录',
        'phases': ('WAIT_PRODUCT', 'WAIT_MARK_RESET', 'WAIT_FOAM', 'WAIT_FOAM_RESET'),
        'points': (
            ('产品条码就绪', 'mark_trigger', 'DBX22.0', 'IN', 'trigger'),
            ('当前产品条码', 'product_barcode', 'DBB0', 'IN', 'text'),
            ('条码校验结果', 'product_barcode_valid', 'DBX48.2', 'OUT', 'result'),
            ('条码处理完成', 'mark_read_done', 'DBX48.1', 'OUT', 'done'),
            ('单件 MES 上传完成', 'product_mes_upload_done', 'DBX48.3', 'OUT', 'done'),
            ('单件 MES 上传结果', 'product_mes_upload_success', 'DBX48.4', 'OUT', 'result'),
            ('泡棉视觉检测触发', 'foam_trigger', 'DBX46.3', 'IN', 'trigger'),
            ('泡棉检测结果', 'foam_passed', 'DBX62.1', 'OUT', 'result'),
            ('泡棉记录完成', 'foam_done', 'DBX62.0', 'OUT', 'done'),
        ),
    },
    {
        'key': 'upload', 'number': 4, 'name': '装箱完成与 MES 上传',
        'subtitle': '整框数据上传、结果回写与补传',
        'phases': ('WAIT_BOXING', 'WAIT_BOXING_RESET', 'COMPLETED'),
        'points': (
            ('装箱完成 / 上传触发', 'boxing_trigger', 'DBX46.4', 'IN', 'trigger'),
            ('MES 上传结果', 'mes_upload_success', 'DBX62.3', 'OUT', 'result'),
            ('MES 上传完成', 'mes_upload_done', 'DBX62.2', 'OUT', 'done'),
            ('工位锁定', 'workstation_locked', 'DBX62.4', 'OUT', 'lock'),
        ),
    },
)


def _format_signal_value(value, kind):
    if value is None or value == '':
        return '—'
    if kind == 'result':
        return 'OK' if str(value).lower() in ('1', 'true', 'ok') else 'NG'
    if kind == 'lock':
        return '已锁定' if str(value).lower() in ('1', 'true') else '正常'
    if kind == 'real':
        try:
            return f'{float(value):+.3f} mm'
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _build_station_snapshot(plc, plc_connected, heartbeat_age, cycle, recent_signals):
    from apps.workflow.models import StationPhase

    records_by_name = {}
    for record in recent_signals:
        records_by_name.setdefault(record.signal_name, record)

    phase = cycle.phase if cycle else ''
    effective_phase = cycle.resume_phase if cycle and phase == StationPhase.LOCKED else phase
    active_index = next(
        (index for index, scene in enumerate(PLC_SCENES) if effective_phase in scene['phases']),
        None,
    )
    if phase == StationPhase.COMPLETED:
        active_index = len(PLC_SCENES) - 1

    rack = cycle.rack if cycle and cycle.rack_id else None
    product = cycle.product if cycle and cycle.workflow_id else None
    overrides = {
        'rack_barcode': rack.rack_code if rack else None,
        'rack_result': True if rack else None,
        'boxing_allowed': cycle.recipe_verified if cycle else None,
        'layer_delta_z': cycle.position_delta_z if cycle else None,
        'position_success': True if cycle and cycle.position_delta_z is not None else None,
        'product_barcode': product.product_code if product else None,
        'product_barcode_valid': True if product else None,
        'foam_passed': cycle.foam_passed if cycle else None,
        'mes_upload_success': cycle.mes_upload_success if cycle else None,
        'workstation_locked': cycle.is_locked if cycle else False,
    }

    scenes = []
    for index, definition in enumerate(PLC_SCENES):
        if phase == StationPhase.COMPLETED:
            scene_status = 'done'
        elif active_index is None:
            scene_status = 'pending'
        elif index < active_index:
            scene_status = 'done'
        elif index == active_index:
            scene_status = 'failed' if cycle and cycle.is_locked else 'active'
        else:
            scene_status = 'pending'
        interactions = []
        scene_time = None
        for label, name, address, direction, kind in definition['points']:
            record = records_by_name.get(name)
            value = overrides.get(name, record.signal_value if record else None)
            recorded_at = record.recorded_at if record else None
            if recorded_at and (scene_time is None or recorded_at > scene_time):
                scene_time = recorded_at
            interactions.append({
                'label': label, 'name': name, 'address': address,
                'direction': direction,
                'direction_label': 'PLC → 上位机' if direction == 'IN' else '上位机 → PLC',
                'value': _format_signal_value(value, kind),
                'raw_value': '—' if value is None else str(value),
                'kind': kind,
                'time': recorded_at.strftime('%H:%M:%S.%f')[:-3] if recorded_at else '—',
            })
        scenes.append({
            'key': definition['key'], 'number': definition['number'],
            'name': definition['name'], 'subtitle': definition['subtitle'],
            'status': scene_status,
            'status_label': {
                'pending': '等待', 'active': '执行中', 'done': '已完成', 'failed': '失败',
            }[scene_status],
            'time': scene_time.strftime('%H:%M:%S') if scene_time else '—',
            'interactions': interactions,
        })

    return {
        'connected': plc_connected,
        'connection_label': 'PLC 通信正常' if plc_connected else ('PLC 离线' if plc else 'PLC 未配置'),
        'address': plc.address if plc and plc.address else '—',
        'heartbeat_age': heartbeat_age,
        'last_seen': plc.last_seen_at.strftime('%H:%M:%S') if plc and plc.last_seen_at else '—',
        'phase': phase,
        'phase_label': cycle.get_phase_display() if cycle else '等待料框到位',
        'cycle_id': cycle.pk if cycle else None,
        'locked': bool(cycle and cycle.is_locked),
        'error': cycle.last_error if cycle else '',
        'rack_code': rack.rack_code if rack else '—',
        'product_code': product.product_code if product else '—',
        'progress': f'{cycle.loaded_quantity} / {cycle.planned_quantity}' if cycle else '0 / —',
        'scenes': scenes,
        'events': [
            {
                'time': record.recorded_at.strftime('%H:%M:%S.%f')[:-3] if record.recorded_at else '—',
                'direction': record.direction,
                'direction_label': 'PLC → 上位机' if record.direction == 'IN' else '上位机 → PLC',
                'name': record.signal_name,
                'value': record.signal_value,
            }
            for record in recent_signals[:8]
        ],
    }


def _get_plc_device():
    """获取PLC设备对象（取第一个PLC类型设备）。"""
    return Device.objects.filter(device_type=DeviceType.PLC, enabled=True).first()


def status(request):
    plc = _get_plc_device()
    now = timezone.now()
    heartbeat_age = None
    plc_connected = False
    if plc and plc.last_seen_at:
        heartbeat_age = round((now - plc.last_seen_at).total_seconds(), 1)
        plc_connected = plc.status == DeviceStatus.ONLINE and heartbeat_age <= 10

    recent_signals = list(
        DeviceSignalRecord.objects.filter(device=plc).order_by('-recorded_at')[:80]
    ) if plc else []
    from apps.workflow.models import StationCycle
    station_cycle = (
        StationCycle.objects
        .select_related('rack__current_recipe', 'workflow__product')
        .order_by('-created_at').first()
    )
    snapshot = _build_station_snapshot(
        plc, plc_connected, heartbeat_age, station_cycle, recent_signals,
    )
    config = plc.configuration if plc and plc.configuration else {}
    return render(request, 'devices/status.html', {
        'plc': plc,
        'plc_connected': plc_connected,
        'heartbeat_age': heartbeat_age,
        'plc_config': config,
        'station_cycle': station_cycle,
        'station_snapshot': snapshot,
    })


def signals(request):
    device_filter = request.GET.get('device', '').strip()
    direction_filter = request.GET.get('direction', '').strip()
    query = request.GET.get('q', '').strip()
    records = DeviceSignalRecord.objects.select_related('device').order_by('-recorded_at')
    if device_filter:
        records = records.filter(device__code=device_filter)
    if direction_filter:
        records = records.filter(direction=direction_filter)
    if query:
        records = records.filter(
            Q(signal_name__icontains=query) | Q(signal_value__icontains=query)
        )
    records = list(records[:200])
    for record in records:
        record.raw_payload_pretty = json.dumps(
            record.raw_payload or {}, ensure_ascii=False, indent=2, sort_keys=True,
        )
    return render(request, 'devices/signals.html', {
        'records': records,
        'devices': Device.objects.order_by('code'),
        'device_filter': device_filter,
        'direction_filter': direction_filter,
        'query': query,
    })


def plc_config(request):
    """PLC点位配置页面。"""
    plc = _get_plc_device()
    if request.method == 'POST':
        # 保存PLC连接参数到设备记录
        if plc and request.POST.get('action') == 'save_connection':
            plc.address = request.POST.get('address', plc.address)
            plc.protocol = request.POST.get('protocol', plc.protocol)
            rack_slot = request.POST.get('rack_slot', '0 / 1').replace(' ', '')
            try:
                rack, slot = [int(item) for item in rack_slot.split('/', 1)]
            except (TypeError, ValueError):
                rack, slot = 0, 1
            try:
                heartbeat_interval = int(request.POST.get('heartbeat_interval', 2))
            except (TypeError, ValueError):
                heartbeat_interval = 2
            plc.configuration = {
                **(plc.configuration or {}),
                'rack': rack,
                'slot': slot,
                'heartbeat_interval': max(1, min(10, heartbeat_interval)),
                'db_number': DB_NUMBER,
                'tcp_port': 102,
                'model': 'S7-1200',
            }
            plc.save(update_fields=['address', 'protocol', 'configuration', 'updated_at'])
    return render(request, 'devices/plc_config.html', {
        'plc': plc,
        'plc_points': PLC_POINT_DEFINITIONS,
    })


def api_plc_status(request):
    """Return one operator-facing station snapshot for the 2-second UI poll."""
    plc = _get_plc_device()
    if not plc:
        return JsonResponse({
            'connected': False, 'connection_label': 'PLC 未配置',
            'error': '未找到 PLC 设备配置', 'scenes': [], 'events': [],
        })

    # 最近10条信号记录
    recent_records = list(
        DeviceSignalRecord.objects
        .filter(device=plc)
        .order_by('-recorded_at')[:80]
    )

    # 心跳：距上次通信不超过10s视为在线
    is_connected = False
    heartbeat_age = None
    if plc.last_seen_at:
        delta = (timezone.now() - plc.last_seen_at).total_seconds()
        heartbeat_age = round(delta, 1)
        is_connected = delta < 10 and plc.status == DeviceStatus.ONLINE
    from apps.workflow.models import StationCycle
    cycle = (
        StationCycle.objects
        .select_related('rack__current_recipe', 'workflow__product')
        .order_by('-created_at').first()
    )
    return JsonResponse(_build_station_snapshot(
        plc, is_connected, heartbeat_age, cycle, recent_records,
    ))


def plc_debug(request):
    """PLC调试页面"""
    from apps.vision.models import RackLocationRecipe, VisionRecipe
    plc = _get_plc_device()
    return render(request, 'devices/plc_debug.html', {
        'plc': plc,
        'plc_points': PLC_POINT_DEFINITIONS,
        'db_number': DB_NUMBER,
        'foam_recipes': VisionRecipe.objects.filter(recipe_type='FOAM_2D', is_active=True).order_by('name'),
        'position_recipes': RackLocationRecipe.objects.filter(enabled=True).order_by('recipe_name'),
        'simulated': getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True),
    })


def api_plc_read(request):
    """读取PLC点位数据的API"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '仅支持POST请求'}, status=405)

    try:
        data = json.loads(request.body)
        point_name = data.get('point_name')

        if not point_name:
            return JsonResponse({'success': False, 'error': '缺少点位名称'})

        # 验证点位名称是否存在
        from apps.devices.plc_db100 import POINTS_BY_NAME
        if point_name not in POINTS_BY_NAME:
            return JsonResponse({'success': False, 'error': f'未知的点位名称: {point_name}'})

        point = POINTS_BY_NAME[point_name]

        # 读取PLC数据
        from apps.devices.services import get_plc_adapter

        adapter = None
        try:
            adapter = get_plc_adapter()
            value = adapter.read_point(point_name)
            return JsonResponse({
                'success': True,
                'point_name': point_name,
                'point_description': point.description,
                'data_type': point.data_type,
                'direction': point.direction,
                'offset': point.offset,
                'bit': point.bit,
                'db_number': DB_NUMBER,
                'value': value,
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'读取失败: {str(e)}'
            })
        finally:
            _close_debug_plc(adapter)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的JSON数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'服务器错误: {str(e)}'})


def _api_plc_write(request):
    """写入PLC点位数据的API"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '仅支持POST请求'}, status=405)

    try:
        data = json.loads(request.body)
        point_name = data.get('point_name')
        value = data.get('value')

        if not point_name:
            return JsonResponse({'success': False, 'error': '缺少点位名称'})

        if value is None:
            return JsonResponse({'success': False, 'error': '缺少写入值'})

        # 验证点位名称是否存在
        from apps.devices.plc_db100 import POINTS_BY_NAME
        if point_name not in POINTS_BY_NAME:
            return JsonResponse({'success': False, 'error': f'未知的点位名称: {point_name}'})

        point = POINTS_BY_NAME[point_name]

        # 检查点位方向（只能写入OUT方向的点位）
        if point.direction != 'OUT':
            return JsonResponse({
                'success': False,
                'error': f'该点位方向为 {point.direction}，只能写入 OUT 方向的点位'
            })

        # 写入PLC数据
        from apps.devices.services import get_plc_adapter

        adapter = None
        try:
            adapter = get_plc_adapter()

            # 类型转换和验证
            if point.data_type == 'BOOL':
                if isinstance(value, str) and value.strip().lower() in ('true', 'false', '1', '0'):
                    value = value.strip().lower() in ('true', '1')
                elif isinstance(value, bool):
                    pass
                elif type(value) is int and value in (0, 1):
                    value = bool(value)
                else:
                    raise ValueError('BOOL 仅支持 true/false 或 1/0')
            elif point.data_type == 'INT':
                value = int(value)
                if not (-32768 <= value <= 32767):
                    return JsonResponse({'success': False, 'error': 'INT 值必须在 -32768 到 32767 之间'})
            elif point.data_type == 'REAL':
                if isinstance(value, bool):
                    raise ValueError('REAL 必须为有限数值')
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError('REAL 必须为有限数值')
                try:
                    value = struct.unpack('>f', struct.pack('>f', value))[0]
                except (OverflowError, struct.error):
                    raise ValueError('REAL 超出 32 位浮点数范围')
            elif point.data_type.startswith('STRING'):
                value = str(value)
                max_len = int(point.data_type.split('[')[1].rstrip(']'))
                if len(value) > max_len:
                    return JsonResponse({'success': False, 'error': f'字符串长度超过 {max_len}'})

            # 写入点位
            adapter.write_point(point_name, value)

            # 回读验证
            read_back = adapter.read_point(point_name)
            verified = read_back == value

            return JsonResponse({
                'success': verified,
                'verified': verified,
                'error': '' if verified else '写入已发送，但回读值不一致，请检查 PLC 程序或自动任务是否改写该点位',
                'point_name': point_name,
                'point_description': point.description,
                'data_type': point.data_type,
                'direction': point.direction,
                'offset': point.offset,
                'bit': point.bit,
                'db_number': DB_NUMBER,
                'written_value': value,
                'read_back_value': read_back,
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            })
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': f'值类型转换失败: {str(e)}'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'写入失败: {str(e)}'
            })
        finally:
            _close_debug_plc(adapter)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的JSON数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'服务器错误: {str(e)}'})


def api_plc_write(request):
    from .plc_position_debug import ownership, active, DebugBusy
    try:
        with ownership() as (state, save):
            if active(state):
                return JsonResponse({'success': False, 'error': '自动联调运行中，请先停止监听再手动写入'})
            return _api_plc_write(request)
    except DebugBusy as exc:
        return JsonResponse({'success': False, 'error': str(exc)})


@require_POST
def api_plc_position_debug(request, mode="position"):
    import secrets
    import time
    from .plc_position_debug import ownership, active, DebugBusy, step, capture_position
    from .services import get_plc_adapter
    from apps.vision.models import RackLocationRecipe, VisionRecipe
    from . import plc_foam_debug
    foam = mode == "foam"
    trigger_point = "foam_trigger" if foam else "position_trigger"
    trigger_address = "DB2.DBX46.3" if foam else "DB2.DBX46.2"
    try:
        data = json.loads(request.body)
        action = data.get('action')
        with ownership(mode=mode) as (state, save):
            if action == 'start':
                if active(state):
                    raise ValueError('已有页面正在监听，请先在原页面停止或等待租约到期')
                recipe = (plc_foam_debug.get_recipe(int(data['recipe_id'])) if foam else
                          RackLocationRecipe.objects.get(pk=int(data['recipe_id']), enabled=True))
                layer = 0 if foam else int(data['layer_no'])
                if not foam and not 1 <= layer <= recipe.layer_count:
                    raise ValueError(f'层号必须在 1 到 {recipe.layer_count} 之间')
                plc = None
                try:
                    plc = get_plc_adapter()
                    trigger = bool(plc.read_point(trigger_point))
                except Exception as exc:
                    return JsonResponse({
                        'success': False,
                        'error': f'PLC通信检查失败，监听未启动：{exc}。请确认PLC已连接、IP及Rack/Slot正确，并检查DB2访问权限。此时尚未触发相机拍照。',
                    })
                finally:
                    _close_debug_plc(plc)
                state.clear()
                state.update(token=secrets.token_hex(24), mode=mode, recipe_id=recipe.pk, layer_no=layer,
                             phase='ARMING' if trigger else 'WAIT_TRIGGER', trigger=trigger,
                             count=0, expires=time.time()+15, done=False, ok=False,
                             message=(f'PLC通信正常，触发位为1；请先将{trigger_address}复位为0，再置1拍照'
                                      if trigger else f'PLC通信正常，触发位为0；等待PLC将{trigger_address}置1拍照'))
                save()
                return JsonResponse({'success': True, **state})
            if action not in ('poll', 'stop'):
                raise ValueError('不支持的操作')
            if not state.get('token') or not secrets.compare_digest(str(data.get('token', '')), state['token']):
                raise ValueError('监听会话已失效，请重新开始')
            if state.get('mode', 'position') != mode:
                raise ValueError('监听类型不匹配')
            if action == 'stop':
                state['expires'] = 0
                save()
                return JsonResponse({'success': True, 'stopped': True, 'message': '监听已停止，已完成的握手信号保留'})
            if not active(state):
                raise ValueError('监听已超时停止，请重新开始')
            plc = None
            try:
                plc = get_plc_adapter()
                if foam:
                    plc_foam_debug.step(state, plc, plc_foam_debug.capture_foam, save)
                else:
                    step(state, plc, capture_position, save)
            except Exception as exc:
                state.update(expires=0, error=str(exc), message='PLC 通讯失败，监听已停止')
                save()
                return JsonResponse({'success': False, 'error': str(exc), 'stopped': True})
            finally:
                _close_debug_plc(plc)
            state['expires'] = time.time()+15
            save()
            return JsonResponse({'success': True, **{k:v for k,v in state.items() if k != 'token'}})
    except DebugBusy as exc:
        return JsonResponse({'success': False, 'busy': True, 'error': str(exc)})
    except (ValueError, TypeError, KeyError, RackLocationRecipe.DoesNotExist, VisionRecipe.DoesNotExist) as exc:
        return JsonResponse({'success': False, 'error': str(exc)})


@require_POST
def api_plc_foam_debug(request):
    return api_plc_position_debug(request, mode="foam")
