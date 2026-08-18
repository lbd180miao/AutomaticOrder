from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import DeviceStatus, DeviceType, SignalDirection
from apps.production.models import Rack, RackRecipe
from apps.workflow.models import StationCycle, StationPhase

from .models import Device, DeviceSignalRecord


class PLCStatusViewTests(TestCase):
    def setUp(self):
        self.plc = Device.objects.create(
            code='PLC-STATUS-01', name='主控 PLC', device_type=DeviceType.PLC,
            protocol='S7', address='192.168.1.10', status=DeviceStatus.ONLINE,
            last_seen_at=timezone.now(),
        )
        recipe = RackRecipe.objects.create(
            recipe_code='RCP-STATUS', name='状态页配方', rack_type='STD',
            layer_count=4, quantity_per_layer=6, total_quantity=24,
            layer_height=120, layer_spacing=150,
        )
        rack = Rack.objects.create(
            rack_code='RK-STATUS-001', rack_type='STD', current_recipe=recipe,
        )
        self.cycle = StationCycle.objects.create(
            rack=rack, phase=StationPhase.WAIT_POSITION,
            planned_quantity=24, loaded_quantity=6,
            position_delta_z=Decimal('1.800'), started_at=timezone.now(),
        )
        DeviceSignalRecord.objects.create(
            device=self.plc, signal_name='position_trigger', signal_value='1',
            direction=SignalDirection.IN, recorded_at=timezone.now(),
        )

    def test_status_page_is_focused_on_process_and_plc_interaction(self):
        response = self.client.get(reverse('devices:status'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '当前流程到哪里了')
        self.assertContains(response, '与 PLC 的交互结果')
        self.assertContains(response, 'DBX56.0')
        self.assertNotContains(response, 'DB100 内存布局')
        self.assertNotContains(response, '生产设备节点')

    def test_snapshot_api_returns_four_scenes_and_new_delta_z_point(self):
        response = self.client.get(reverse('devices:api_plc_status'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['scenes']), 4)
        position = next(scene for scene in payload['scenes'] if scene['key'] == 'position')
        self.assertEqual(position['status'], 'active')
        delta = next(row for row in position['interactions'] if row['name'] == 'layer_delta_z')
        self.assertEqual(delta['address'], 'DBD60')
        self.assertEqual(delta['value'], '+1.800 mm')
