"""初始化演示数据：设备档案、装箱配方、批次。

用法：python manage.py seed_demo
"""
from django.core.management.base import BaseCommand

from apps.core.constants import DeviceStatus, DeviceType
from apps.devices.models import Device
from apps.production.models import ProductionBatch, RackRecipe


DEVICES = [
    ('PLC-01', '主控PLC', DeviceType.PLC, 'Modbus TCP', '192.168.1.10'),
    ('ROBOT-INJ-01', '注塑取件机器人', DeviceType.INJECTION_ROBOT, 'PLC中转', ''),
    ('ROBOT-BOX-01', '装箱机器人', DeviceType.BOXING_ROBOT, 'PLC中转', ''),
    ('SCAN-01', '产品扫码枪', DeviceType.SCANNER, 'TCP', '192.168.1.21'),
    ('CAM-DEPTH-01', '机器人深度相机', DeviceType.DEPTH_CAMERA, 'GigE Vision', '192.168.1.31'),
    ('CAM-INSPECT-01', '固定检测相机', DeviceType.INSPECT_CAMERA, 'GigE Vision', '192.168.1.32'),
    ('LASER-01', '激光打标机', DeviceType.LASER_MARKER, 'PLC触发', ''),
    ('SENSOR-FOAM-01', '泡棉距离传感器', DeviceType.FOAM_SENSOR, 'PLC中转', ''),
]


class Command(BaseCommand):
    help = '初始化演示用设备、配方与批次数据'

    def handle(self, *args, **options):
        for code, name, dtype, protocol, address in DEVICES:
            Device.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'device_type': dtype,
                    'protocol': protocol,
                    'address': address,
                    'enabled': True,
                    'status': DeviceStatus.ONLINE,
                },
            )
        self.stdout.write(self.style.SUCCESS(f'已写入 {len(DEVICES)} 台设备'))

        RackRecipe.objects.update_or_create(
            recipe_code='RCP-RK-DEMO-01',
            defaults={
                'name': '演示标准配方',
                'rack_type': 'STANDARD',
                'layer_count': 4,
                'quantity_per_layer': 6,
                'total_quantity': 24,
                'layer_height': 120.0,
                'layer_spacing': 150.0,
                'tolerance_x': 2.0,
                'tolerance_y': 2.0,
                'tolerance_z': 3.0,
                'is_active': True,
            },
        )
        self.stdout.write(self.style.SUCCESS('已写入演示配方 RCP-RK-DEMO-01'))

        ProductionBatch.objects.get_or_create(
            batch_no='BATCH-DEMO-001',
            defaults={'product_type': '保险杠', 'status': 'OPEN'},
        )
        self.stdout.write(self.style.SUCCESS('已写入演示批次 BATCH-DEMO-001'))
        self.stdout.write(self.style.SUCCESS('演示数据初始化完成'))
