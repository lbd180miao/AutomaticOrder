from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from django.test import TestCase
from django.urls import reverse

from apps.core.constants import MesAction
from apps.mes.client import SimulatedMesClient
from apps.mes.models import MesRecord
from apps.mes.services import MesService
from apps.production.models import Product, Rack, RackRecipe
from apps.workflow.models import StationCycle, StationPhase, WorkflowInstance
from apps.vision.models import RackLayerMeasurement, RackMeasurementProfile


class MesServiceTests(TestCase):
    def test_get_recipe_success_records(self):
        service = MesService(client=SimulatedMesClient())
        resp = service.get_rack_recipe('RK-1')
        self.assertTrue(resp['success'])
        self.assertIn('recipe', resp)
        self.assertTrue(MesRecord.objects.filter(action=MesAction.GET_RACK_RECIPE, success=True).exists())

    def test_get_recipe_failure_records(self):
        client = SimulatedMesClient(fail_actions=[MesAction.GET_RACK_RECIPE])
        service = MesService(client=client)
        resp = service.get_rack_recipe('RK-1')
        self.assertFalse(resp['success'])
        rec = MesRecord.objects.get(action=MesAction.GET_RACK_RECIPE)
        self.assertFalse(rec.success)
        self.assertTrue(rec.error_message)

    def test_upload_barcode(self):
        service = MesService(client=SimulatedMesClient())
        resp = service.upload_product_barcode('P-1', 'RK-1')
        self.assertTrue(resp['success'])


class MesRecordPageTests(TestCase):
    def test_page_shows_compact_height_and_spacing_verification(self):
        recipe = RackRecipe.objects.create(
            recipe_code='MES-RCP-01', name='MES 装箱配方', rack_type='A',
            layer_height=Decimal('100.000'), layer_spacing=Decimal('50.000'),
            tolerance_z=Decimal('0.500'),
        )
        rack = Rack.objects.create(
            rack_code='RACK-001', rack_type='A', current_recipe=recipe,
        )
        product = Product.objects.create(product_code='PRODUCT-001', rack=rack)
        workflow = WorkflowInstance.objects.create(product=product)
        StationCycle.objects.create(
            workflow=workflow, phase=StationPhase.WAIT_FOAM,
            measured_layer_height=Decimal('100.250'),
            measured_layer_spacing=Decimal('50.250'),
            recipe_verified=True,
        )

        response = self.client.get(reverse('mes:recipe_check'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '当前自动核对结果')
        self.assertContains(response, '料架层高')
        self.assertContains(response, '料架层距')
        self.assertContains(response, '100.250 mm')
        self.assertContains(response, '50.250 mm')
        self.assertContains(response, 'DBX51.0')
        self.assertContains(response, '已写入 1')

    def test_page_without_cycle_shows_waiting_state(self):
        response = self.client.get(reverse('mes:recipe_check'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '等待生产任务')
        self.assertGreaterEqual(response.content.decode().count('等待测量'), 2)

    def test_page_contains_manual_and_automatic_measurement_controls(self):
        response = self.client.get(reverse('mes:recipe_check'))

        self.assertContains(response, '手动图片计算')
        self.assertContains(response, '计算当前图片')
        self.assertContains(response, '相机拍照并计算')
        self.assertContains(response, '保存为自动参数')
        self.assertContains(response, '旁路调试 · 不写 PLC')

    def test_record_page_is_separated_from_recipe_debug(self):
        response = self.client.get(reverse('mes:record_list'))

        self.assertContains(response, 'MES 接口监控')
        self.assertContains(response, reverse('mes:recipe_check'))
        self.assertNotContains(response, 'id="rack-image-input"')


class RackMeasurementDebugApiTests(TestCase):
    def setUp(self):
        self.recipe = RackRecipe.objects.create(
            recipe_code='MES-RCP-DEBUG', name='调试配方', rack_type='D',
            layer_count=4, layer_height=Decimal('120'), layer_spacing=Decimal('150'),
            tolerance_z=Decimal('3'),
        )
        rack = Rack.objects.create(rack_code='RACK-DEBUG', rack_type='D', current_recipe=self.recipe)
        product = Product.objects.create(product_code='PRODUCT-DEBUG', rack=rack)
        StationCycle.objects.create(workflow=WorkflowInstance.objects.create(product=product))

    @staticmethod
    def image_upload():
        image = np.full((420, 720, 3), 28, dtype=np.uint8)
        for index in range(4):
            top = 45 + index * 75
            cv2.line(image, (70, top), (650, top), (235, 235, 235), 4)
            cv2.line(image, (70, top + 60), (650, top + 60), (235, 235, 235), 4)
        ok, encoded = cv2.imencode('.jpg', image)
        assert ok
        return SimpleUploadedFile('rack.jpg', encoded.tobytes(), content_type='image/jpeg')

    def test_profile_save_and_manual_upload_measurement(self):
        profile_response = self.client.post(
            reverse('mes:rack_measurement_profile_api'),
            data={
                'name': '调试配置', 'camera_code': 'CAM-RACK-01',
                'roi_x': 50, 'roi_y': 20, 'roi_width': 620, 'roi_height': 350,
                'mm_per_pixel': 2, 'edge_threshold': .12, 'min_peak_distance': 6,
            },
            content_type='application/json',
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertTrue(RackMeasurementProfile.objects.get().is_active)

        parameters = {
            'layer_count': 4, 'expected_layer_height': 120,
            'expected_layer_spacing': 150, 'tolerance': 3,
            'mm_per_pixel': 2, 'edge_threshold': .12, 'min_peak_distance': 6,
            'roi_x': 50, 'roi_y': 20, 'roi_width': 620, 'roi_height': 350,
        }
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            response = self.client.post(
                reverse('mes:rack_measurement_debug_api'),
                data={'mode': 'upload', 'parameters': __import__('json').dumps(parameters), 'image': self.image_upload()},
            )
        payload = response.json()
        self.assertEqual(response.status_code, 200, payload)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['detected_layer_count'], 4)
        self.assertIn('未写入 PLC', payload['side_effects'])
        self.assertEqual(RackLayerMeasurement.objects.count(), 1)
