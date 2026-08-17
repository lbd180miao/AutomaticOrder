import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Device, DeviceSignalRecord
from apps.core.constants import DeviceType, DeviceStatus
from .plc_db100 import DB100_POINTS


PLC_POINT_DEFINITIONS = DB100_POINTS

PLC_HANDSHAKES = (
    ('产品条码', 'mark_trigger', 'DBX24.0', 'product_barcode', 'DBB2', 'mark_read_done', 'DBX25.0', ('WAIT_PRODUCT', 'WAIT_MARK_RESET')),
    ('料框配方', 'rack_trigger', 'DBX48.0', 'rack_barcode', 'DBB26', 'rack_done', 'DBX49.0', ('WAIT_RACK', 'WAIT_RACK_RESET')),
    ('3D 定位', 'position_trigger', 'DBX118.0', '', 'DBB54–117', 'position_done', 'DBX119.0', ('WAIT_POSITION', 'WAIT_POSITION_RESET')),
    ('配方校验', 'recipe_verify_trigger', 'DBX50.0', 'boxing_allowed', 'DBX51.0', 'recipe_verify_done', 'DBX52.0', ('WAIT_RECIPE_VERIFY', 'WAIT_RECIPE_RESET')),
    ('泡棉检测', 'foam_trigger', 'DBX120.0', 'foam_passed', 'DBX121.0', 'foam_done', 'DBX122.0', ('WAIT_FOAM', 'WAIT_FOAM_RESET')),
    ('装箱上传', 'boxing_trigger', 'DBX123.0', 'mes_upload_success', 'DBX124.0', 'mes_upload_done', 'DBX125.0', ('WAIT_BOXING', 'WAIT_BOXING_RESET')),
)


def _get_plc_device():
    """获取PLC设备对象（取第一个PLC类型设备）。"""
    return Device.objects.filter(device_type=DeviceType.PLC, enabled=True).first()


def status(request):
    devices = Device.objects.filter(enabled=True).order_by('device_type', 'code')
    plc = _get_plc_device()
    now = timezone.now()
    heartbeat_age = None
    plc_connected = False
    if plc and plc.last_seen_at:
        heartbeat_age = round((now - plc.last_seen_at).total_seconds(), 1)
        plc_connected = plc.status == DeviceStatus.ONLINE and heartbeat_age <= 10

    recent_signals = list(
        DeviceSignalRecord.objects.filter(device=plc).order_by('-recorded_at')[:20]
    ) if plc else []
    signal_values = {}
    for record in recent_signals:
        signal_values.setdefault(record.signal_name, record.signal_value)

    from apps.workflow.models import StationCycle, StationPhase
    station_cycle = (
        StationCycle.objects.exclude(phase=StationPhase.COMPLETED)
        .order_by('-created_at').first()
    )
    phase = station_cycle.phase if station_cycle else ''
    active_index = next(
        (index for index, item in enumerate(PLC_HANDSHAKES) if phase in item[7]),
        None,
    )
    handshake_rows = []
    for index, item in enumerate(PLC_HANDSHAKES):
        name, trigger_name, trigger_address, result_name, result_address, confirm_name, confirm_address, _phases = item
        handshake_rows.append({
            'number': index + 1,
            'name': name,
            'trigger_address': trigger_address,
            'result_address': result_address,
            'confirm_address': confirm_address,
            'trigger_value': signal_values.get(trigger_name),
            'result_value': signal_values.get(result_name) if result_name else None,
            'confirm_value': signal_values.get(confirm_name),
            'status': (
                'done' if active_index is not None and index < active_index
                else 'active' if active_index == index
                else 'pending'
            ),
        })

    main_devices = [device for device in devices if 'TEST' not in device.code.upper()]
    hidden_test_count = len(devices) - len(main_devices)
    config = plc.configuration if plc and plc.configuration else {}
    return render(request, 'devices/status.html', {
        'devices': devices,
        'main_devices': main_devices,
        'hidden_test_count': hidden_test_count,
        'plc': plc,
        'plc_connected': plc_connected,
        'heartbeat_age': heartbeat_age,
        'plc_config': config,
        'plc_points': PLC_POINT_DEFINITIONS,
        'recent_signals': recent_signals[:8],
        'handshake_rows': handshake_rows,
        'station_cycle': station_cycle,
        'current_phase_label': station_cycle.get_phase_display() if station_cycle else '等待生产任务',
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
                'db_number': 100,
            }
            plc.save(update_fields=['address', 'protocol', 'configuration', 'updated_at'])
    return render(request, 'devices/plc_config.html', {
        'plc': plc,
        'plc_points': PLC_POINT_DEFINITIONS,
    })


def api_plc_status(request):
    """JSON接口：返回PLC实时连接状态、心跳、最近信号记录，供前端每2s轮询。"""
    plc = _get_plc_device()
    if not plc:
        return JsonResponse({'connected': False, 'error': '未找到PLC设备配置', 'signals': []})

    # 最近10条信号记录
    recent = list(
        DeviceSignalRecord.objects
        .filter(device=plc)
        .order_by('-recorded_at')[:10]
        .values('signal_name', 'signal_value', 'direction', 'recorded_at')
    )
    for r in recent:
        r['recorded_at'] = r['recorded_at'].strftime('%H:%M:%S') if r['recorded_at'] else '-'

    # 心跳：距上次通信不超过10s视为在线
    is_connected = False
    last_seen_str = '-'
    heartbeat_age = None
    if plc.last_seen_at:
        delta = (timezone.now() - plc.last_seen_at).total_seconds()
        heartbeat_age = round(delta, 1)
        is_connected = delta < 10 and plc.status == DeviceStatus.ONLINE
        last_seen_str = plc.last_seen_at.strftime('%H:%M:%S')

    return JsonResponse({
        'connected': is_connected,
        'status': plc.get_status_display(),
        'status_raw': plc.status,
        'address': plc.address or '-',
        'protocol': plc.protocol or '-',
        'last_seen': last_seen_str,
        'heartbeat_age': heartbeat_age,
        'signals': recent,
    })
