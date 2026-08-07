import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Device, DeviceSignalRecord
from apps.core.constants import DeviceType, DeviceStatus


# ── PLC 点位定义（对应需求文档四大场景所需的DB块点位）──────────────────────────
# 每个点位: (信号名, 中文说明, 方向 IN=PLC→上位机 OUT=上位机→PLC, DB块号, 偏移)
PLC_POINT_DEFINITIONS = [
    # 场景一：料框到位
    ('rack_barcode',          '料框条码',           'IN',  10, 0),
    ('rack_arrived_trigger',  '料框到位触发',        'IN',  10, 20),
    ('empty_check_trigger',   '空箱检查触发',        'IN',  10, 22),
    ('mes_verify_result',     'MES校验结果反馈',     'OUT', 10, 24),
    ('empty_check_result',    '空箱检测结果反馈',    'OUT', 10, 26),
    # 场景二：料架定位补偿
    ('locate_trigger',        '定位扫描触发',        'IN',  20, 0),
    ('current_layer',         '当前装箱层数',        'IN',  20, 2),
    ('offset_x',              '偏差X (mm)',          'OUT', 20, 4),
    ('offset_y',              '偏差Y (mm)',          'OUT', 20, 8),
    ('offset_z',              '偏差Z (mm)',          'OUT', 20, 12),
    ('locate_result',         '定位结果反馈',        'OUT', 20, 16),
    # 场景三：泡棉检测
    ('foam_detect_trigger',   '泡棉检测触发',        'IN',  30, 0),
    ('foam_detect_result',    '泡棉检测结果反馈',    'OUT', 30, 2),
    ('foam_detect_reset',     '检测复位指令',        'IN',  30, 4),
    # 场景四：装箱完成与上传
    ('boxing_barcode',        '装箱条码',            'IN',  40, 0),
    ('upload_trigger',        '上传触发',            'IN',  40, 20),
    ('upload_result',         '上传结果反馈',        'OUT', 40, 22),
    # 心跳
    ('heartbeat',             '心跳',                'OUT', 1,  0),
]


def _get_plc_device():
    """获取PLC设备对象（取第一个PLC类型设备）。"""
    return Device.objects.filter(device_type=DeviceType.PLC, enabled=True).first()


def status(request):
    devices = Device.objects.order_by('device_type', 'code')
    plc = _get_plc_device()
    return render(request, 'devices/status.html', {
        'devices': devices,
        'plc': plc,
        'plc_points': PLC_POINT_DEFINITIONS,
    })


def signals(request):
    records = (
        DeviceSignalRecord.objects.select_related('device').order_by('-recorded_at')[:200]
    )
    return render(request, 'devices/signals.html', {'records': records})


def plc_config(request):
    """PLC点位配置页面。"""
    plc = _get_plc_device()
    if request.method == 'POST':
        # 保存PLC连接参数到设备记录
        if plc and request.POST.get('action') == 'save_connection':
            plc.address = request.POST.get('address', plc.address)
            plc.protocol = request.POST.get('protocol', plc.protocol)
            plc.save(update_fields=['address', 'protocol', 'updated_at'])
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
