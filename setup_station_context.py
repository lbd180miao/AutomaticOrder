import os
import django
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.utils import timezone
from apps.devices.models import Device
from apps.core.constants import DeviceStatus, DeviceType, WorkflowState
from apps.production.models import Rack, Product
from apps.workflow.models import StationCycle, StationPhase, WorkflowInstance


def setup_active_station_context():
    now = timezone.now()

    # 1. 活跃设备在线时间更新
    devices = Device.objects.filter(enabled=True)
    for dev in devices:
        if dev.device_type in [DeviceType.INSPECT_CAMERA, DeviceType.DEPTH_CAMERA]:
            dev.status = DeviceStatus.ONLINE
            dev.last_seen_at = now
            dev.save()
        elif dev.device_type == DeviceType.PLC:
            # PLC 处于报警中断状态 (对应我们真实的 PLC 报警)
            dev.status = DeviceStatus.OFFLINE
            dev.last_seen_at = now - timedelta(minutes=15)
            dev.save()

    # 2. 当前正在进行装箱的料框与产品
    rack = Rack.objects.filter(status='LOADING').first()
    if not rack:
        rack = Rack.objects.filter(rack_code='RACK-20260820-002').first()
    
    product = Product.objects.filter(rack=rack).order_by('-updated_at').first()
    if not product:
        product = Product.objects.first()

    # 3. 创建/更新当前活跃的 StationCycle
    cycle = StationCycle.objects.filter(is_locked=True).first()
    if not cycle:
        cycle = StationCycle.objects.create(
            rack=rack,
            phase=StationPhase.LOCKED,
            resume_phase='WAIT_FOAM',
            loaded_quantity=8,
            planned_quantity=12,
            position_delta_z=2.15,
            is_locked=True,
            last_error='3D 视觉料架定位 ΔZ 补偿超限，工位保持安全停机',
        )
    else:
        cycle.rack = rack
        cycle.is_locked = True
        cycle.phase = StationPhase.LOCKED
        cycle.resume_phase = 'WAIT_FOAM'
        cycle.loaded_quantity = 8
        cycle.planned_quantity = 12
        cycle.position_delta_z = 2.15
        cycle.last_error = '3D 视觉料架定位 ΔZ 补偿超限，工位保持安全停机'
        cycle.save()

    print("已成功建立当前活跃工位上下文数据：料框 RACK-20260820-002, 进度 8/12 件, 工位锁定状态 True")

if __name__ == '__main__':
    setup_active_station_context()
