from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.constants import ResultStatus, VisionTaskType
from apps.production.models import Product, Rack, RackRecipe
from apps.vision.algorithms.foam_inspector import FoamDefectType
from apps.vision.models import FoamInspectionResult, RackLocationResult, VisionTask
from apps.vision.services import VisionService


class VisionServiceTests(TestCase):
    def setUp(self):
        self.service = VisionService()
        self.product = Product.objects.create(product_code='P-V1')
        self.recipe = RackRecipe.objects.create(
            recipe_code='RCP-V', name='视觉配方', rack_type='STD',
            layer_count=4, quantity_per_layer=6, total_quantity=24,
            layer_height=120, layer_spacing=150,
            tolerance_x=2, tolerance_y=2, tolerance_z=3,
        )
        self.rack = Rack.objects.create(rack_code='RK-V', current_recipe=self.recipe)

    # ------------------------------------------------------------------
    # 料架定位测试
    # ------------------------------------------------------------------

    def test_locate_both_racks_success(self):
        left, right = self.service.locate_both_racks(self.product, self.rack, self.recipe)
        self.assertTrue(left.is_success)
        self.assertTrue(right.is_success)
        self.assertEqual(RackLocationResult.objects.count(), 2)

    # ------------------------------------------------------------------
    # 泡棉检测 — 基础用例
    # ------------------------------------------------------------------

    def test_inspect_foam_pass(self):
        result = self.service.inspect_foam(self.product, self.rack, simulated_pass=True)
        self.assertTrue(result.is_passed)
        self.assertEqual(FoamInspectionResult.objects.count(), 1)

    def test_inspect_foam_fail(self):
        result = self.service.inspect_foam(self.product, self.rack, simulated_pass=False)
        self.assertFalse(result.is_passed)
        # 不合格时至少有一种缺陷标记
        self.assertTrue(result.has_lifted_edge or not result.is_aligned or not result.is_present)

    # ------------------------------------------------------------------
    # 泡棉检测 — position_index 差异
    # ------------------------------------------------------------------

    def test_inspect_foam_position_index_result_data(self):
        """不同 position_index 应产生包含对应 position_index 的 result_data。"""
        for idx in range(3):
            result = self.service.inspect_foam(
                self.product, self.rack, position_index=idx, simulated_pass=True,
            )
            self.assertEqual(result.position_index, idx)
            self.assertIn('offset_x_px', result.result_data)
            self.assertIn('coverage_ratio', result.result_data)

    def test_inspect_foam_fail_has_quantitative_error_message(self):
        """失败时 VisionTask.error_message 应包含缺陷类型和量化偏移信息。"""
        self.service.inspect_foam(self.product, self.rack, simulated_pass=False)
        task = VisionTask.objects.filter(status=ResultStatus.FAILED).first()
        self.assertIsNotNone(task)
        self.assertIn('缺陷', task.error_message)
        # 消息中应包含像素偏移信息
        self.assertIn('px', task.error_message)

    # ------------------------------------------------------------------
    # 泡棉检测 — 批量位置
    # ------------------------------------------------------------------

    def test_inspect_foam_all_positions_all_pass(self):
        """全部合格时 all_passed=True，failed_positions 为空。"""
        summary = self.service.inspect_foam_all_positions(
            self.product, self.rack, position_count=3, simulated_pass=True,
        )
        self.assertTrue(summary['all_passed'])
        self.assertEqual(summary['failed_positions'], [])
        self.assertEqual(len(summary['results']), 3)
        self.assertEqual(FoamInspectionResult.objects.count(), 3)

    def test_inspect_foam_all_positions_with_fail(self):
        """simulated_pass=False 时所有位置均不合格，failed_positions 长度 == position_count。"""
        summary = self.service.inspect_foam_all_positions(
            self.product, self.rack, position_count=3, simulated_pass=False,
        )
        self.assertFalse(summary['all_passed'])
        self.assertEqual(len(summary['failed_positions']), 3)

    # ------------------------------------------------------------------
    # 泡棉检测 — 异常分支
    # ------------------------------------------------------------------

    def test_inspect_foam_exception_marks_task_failed(self):
        """算法抛出异常时，VisionTask 应被标记为 FAILED 并保存错误消息，
        同时异常应继续向上传播。"""
        with patch.object(
            self.service.foam_inspector, 'inspect',
            side_effect=RuntimeError('相机连接超时'),
        ):
            with self.assertRaises(RuntimeError):
                self.service.inspect_foam(self.product, self.rack)

        task = VisionTask.objects.filter(status=ResultStatus.FAILED).first()
        self.assertIsNotNone(task)
        self.assertIn('相机连接超时', task.error_message)
        self.assertIsNotNone(task.finished_at)

    # ------------------------------------------------------------------
    # 泡棉检测 — inspection_config 透传
    # ------------------------------------------------------------------

    def test_inspect_foam_with_inspection_config(self):
        """inspection_config 应透传至 result_data 并影响 score_threshold 字段。"""
        cfg = {'score_threshold': 0.9, 'coverage_threshold': 0.8, 'max_offset_px': 20}
        result = self.service.inspect_foam(
            self.product, self.rack, simulated_pass=True, inspection_config=cfg,
        )
        self.assertEqual(result.result_data.get('score_threshold'), 0.9)
        self.assertEqual(result.result_data.get('coverage_threshold'), 0.8)
        self.assertEqual(result.result_data.get('max_offset_px'), 20)


    def test_inspect_foam_can_use_real_camera_capture_image(self):
        class FakeCameraAdapter:
            def __init__(self, image_path):
                self.image_path = image_path

            def capture(self, camera_code, task_type):
                return {
                    'success': True,
                    'camera_code': camera_code,
                    'task_type': task_type,
                    'image_path': self.image_path,
                }

        with TemporaryDirectory() as tmpdir:
            image_path = str(Path(tmpdir) / 'camera.png')
            cv2.imwrite(image_path, np.full((120, 160, 3), 110, dtype=np.uint8))
            service = VisionService(camera_adapter=FakeCameraAdapter(image_path))

            result = service.inspect_foam(
                self.product,
                self.rack,
                position_index=2,
                use_camera=True,
            )

        self.assertEqual(result.result_data.get('algorithm'), 'camera_foam_inspector')
        self.assertEqual(result.result_data.get('camera_image_path'), image_path)
        self.assertEqual(result.vision_task.images.count(), 2)


class VisionTaskListLayoutTests(SimpleTestCase):
    def test_task_table_header_does_not_overlap_first_row(self):
        template = (
            Path(settings.BASE_DIR) / 'templates' / 'vision' / 'task_list.html'
        ).read_text(encoding='utf-8')
        css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'app.css').read_text(
            encoding='utf-8'
        )

        self.assertIn('vision-task-table', template)
        self.assertIn('.vision-task-table thead th', css)
        self.assertIn('position: static', css)


class FoamRoiCaptureViewTests(TestCase):
    def test_capture_foam_roi_get_redirects_to_task_list(self):
        response = self.client.get(reverse('vision:capture_foam_roi'))

        self.assertRedirects(response, reverse('vision:task_list'))

    def test_task_list_shows_result_links_and_camera_buttons_in_requested_order(self):
        response = self.client.get(reverse('vision:task_list'))
        content = response.content.decode('utf-8')

        expected_order = [
            'PLC序号',
            '泡棉检测结果',
            '料架定位结果',
            '2D相机拍照检测ROI',
            '深度相机拍照检测ROI',
        ]
        positions = [content.index(label) for label in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertContains(response, reverse('vision:foam_results'))
        self.assertContains(response, reverse('vision:rack_results'))
        self.assertContains(response, reverse('vision:capture_foam_roi'))
        self.assertContains(response, reverse('vision:capture_depth_roi'))
        self.assertContains(response, 'name="plc_sequence"')
        self.assertContains(response, 'PLC序号')
        self.assertContains(response, '用于模拟PLC触发的拍照序号')
        self.assertContains(response, 'form="foam-capture-form"')
        self.assertContains(response, '2D相机拍照检测ROI')

    @override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': True})
    def test_capture_foam_roi_creates_task_from_plc_sequence_and_redirects(self):
        response = self.client.post(
            reverse('vision:capture_foam_roi'),
            {'plc_sequence': '3'},
        )

        result = FoamInspectionResult.objects.get()
        task = result.vision_task
        self.assertEqual(result.position_index, 3)
        self.assertEqual(task.task_type, VisionTaskType.FOAM_INSPECTION)
        self.assertIn(task.status, {ResultStatus.SUCCESS, ResultStatus.FAILED})
        self.assertRedirects(response, reverse('vision:task_detail', args=[task.pk]))

    def test_capture_foam_roi_camera_error_redirects_to_task_list(self):
        with patch('apps.vision.views.VisionService') as service_cls:
            service_cls.return_value.inspect_foam.side_effect = RuntimeError(
                'Unable to import chg_hik.'
            )

            response = self.client.post(
                reverse('vision:capture_foam_roi'),
                {'plc_sequence': '3'},
            )

        self.assertRedirects(response, reverse('vision:task_list'))
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('2D相机拍照失败' in str(message) for message in messages))


class DepthRoiDebugViewTests(TestCase):
    def setUp(self):
        self.source_task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )

    def test_task_detail_does_not_show_manual_depth_roi_capture_form(self):
        response = self.client.get(
            reverse('vision:task_detail', args=[self.source_task.pk])
        )

        self.assertNotContains(response, '深度相机拍照检测ROI')

    def test_capture_depth_roi_creates_debug_rack_task_and_redirects(self):
        response = self.client.post(reverse('vision:capture_depth_roi'))

        task = VisionTask.objects.exclude(pk=self.source_task.pk).get()
        self.assertEqual(task.task_type, VisionTaskType.RACK_LOCATING)
        self.assertEqual(task.rack.rack_code, 'DEBUG-RACK')
        self.assertEqual(task.rack_results.count(), 2)
        self.assertGreaterEqual(task.images.count(), 1)
        self.assertRedirects(response, reverse('vision:task_detail', args=[task.pk]))
