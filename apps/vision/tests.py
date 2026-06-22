from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.constants import ResultStatus, VisionTaskType
from apps.production.models import Product, Rack, RackRecipe
from apps.vision.algorithms.foam_inspector import FoamDefectType, FoamInspector
from apps.vision.models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionTask,
)
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

    def test_real_camera_foam_inspection_uses_configured_roi_instead_of_full_frame(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[5:35, 150:195] = 240
        image[60:90, 40:90] = 230

        result = FoamInspector().inspect(
            image=image,
            inspection_config={'roi_ratio': (0.1, 0.5, 0.6, 0.95)},
            simulated_pass=True,
        )

        self.assertEqual(result['roi'], (20, 50, 120, 95))
        foam_box = result['foam_box']
        self.assertLess(foam_box[0], 120)
        self.assertGreaterEqual(foam_box[1], 50)

    def test_real_camera_foam_inspection_uses_calibrated_left_right_rois(self):
        image = np.zeros((120, 220, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[5:35, 70:150] = 250
        image[55:85, 12:50] = 245
        image[55:85, 170:208] = 245

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.45, 0.28, 0.78),
                        'right': (0.72, 0.45, 1.0, 0.78),
                    },
                },
                'coverage_threshold': 0.3,
                'max_offset_px': 18,
            },
            simulated_pass=False,
        )

        self.assertTrue(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.NONE)
        self.assertEqual(result['result_data']['foam_target'], 'bumper')
        self.assertEqual(
            result['result_data']['decision_rule'],
            'present_means_aligned_and_not_lifted',
        )
        self.assertIn('sides', result['result_data'])
        self.assertTrue(result['result_data']['sides']['left']['is_present'])
        self.assertTrue(result['result_data']['sides']['right']['is_present'])
        self.assertLess(result['result_data']['sides']['left']['box'][2], 70)
        self.assertGreater(result['result_data']['sides']['right']['box'][0], 150)

    def test_calibrated_foam_annotation_receives_side_details(self):
        image = np.zeros((120, 220, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[55:85, 12:50] = 245
        image[55:85, 170:208] = 245
        observed = {}

        def capture_annotation(img, roi, foam, result):
            observed.update(result)
            return img

        with patch(
            'apps.vision.algorithms.foam_inspector.image_io.annotate_foam',
            side_effect=capture_annotation,
        ):
            FoamInspector().inspect(
                image=image,
                inspection_config={
                    'foam_rois': {
                        '0': {
                            'left': (0.0, 0.45, 0.28, 0.78),
                            'right': (0.72, 0.45, 1.0, 0.78),
                        },
                    },
                    'coverage_threshold': 0.3,
                    'max_offset_px': 18,
                },
                simulated_pass=False,
            )

        self.assertIn('sides', observed)
        self.assertIn('left', observed['sides'])

    def test_calibrated_foam_detection_ignores_roi_border_pixels(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[20:80, 0:70] = 245
        image[20:80, 130:200] = 245

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.4, 0.9),
                        'right': (0.6, 0.1, 1.0, 0.9),
                    },
                },
                'coverage_threshold': 0.2,
                'max_offset_px': 30,
                'ignore_border_ratio': 0.08,
            },
            simulated_pass=False,
        )

        left = result['result_data']['sides']['left']
        right = result['result_data']['sides']['right']
        self.assertGreater(left['box'][0], left['roi'][0])
        self.assertGreater(left['box'][1], left['roi'][1])
        self.assertLess(right['box'][2], right['roi'][2])
        self.assertLess(right['box'][3], right['roi'][3])

    def test_calibrated_foam_detection_can_require_dark_bumper_support(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[20:80, 12:70] = 245
        image[20:80, 130:188] = 245

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.4, 0.9),
                        'right': (0.6, 0.1, 1.0, 0.9),
                    },
                },
                'coverage_threshold': 0.2,
                'max_offset_px': 30,
                'require_dark_support': True,
            },
            simulated_pass=False,
        )

        self.assertFalse(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.MISSING)
        self.assertEqual(result['result_data']['sides']['left']['reason'], 'no_dark_support')

    def test_calibrated_foam_detection_passes_with_dark_bumper_support(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[20:80, 12:70] = 245
        image[20:80, 130:188] = 245
        image[44:58, 20:76] = 20
        image[44:58, 124:180] = 20

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.4, 0.9),
                        'right': (0.6, 0.1, 1.0, 0.9),
                    },
                },
                'coverage_threshold': 0.2,
                'max_offset_px': 30,
                'require_dark_support': True,
            },
            simulated_pass=False,
        )

        self.assertTrue(result['is_passed'])
        self.assertTrue(result['result_data']['sides']['left']['is_present'])

    def test_calibrated_foam_inspection_fails_when_one_side_missing(self):
        image = np.zeros((120, 220, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[55:85, 12:50] = 245

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.45, 0.28, 0.78),
                        'right': (0.72, 0.45, 1.0, 0.78),
                    },
                },
                'coverage_threshold': 0.3,
            },
            simulated_pass=False,
        )

        self.assertFalse(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.MISSING)
        self.assertTrue(result['result_data']['sides']['left']['is_present'])
        self.assertFalse(result['result_data']['sides']['right']['is_present'])

    def test_calibrated_foam_inspection_passes_when_foam_exists_even_if_offset(self):
        image = np.zeros((120, 220, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[55:85, 12:50] = 245
        image[55:85, 158:196] = 245

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.45, 0.28, 0.78),
                        'right': (0.72, 0.45, 1.0, 0.78),
                    },
                },
                'coverage_threshold': 0.2,
                'max_offset_px': 6,
            },
            simulated_pass=False,
        )

        self.assertTrue(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.NONE)
        self.assertTrue(result['result_data']['sides']['right']['is_present'])
        self.assertTrue(result['result_data']['sides']['right']['is_aligned'])
        self.assertFalse(result['has_lifted_edge'])

    def test_inspect_foam_uses_active_calibration_profile_for_camera_image(self):
        image = np.zeros((120, 220, 3), dtype=np.uint8)
        image[:, :] = (35, 90, 80)
        image[55:85, 12:50] = 245
        image[55:85, 170:208] = 245

        class FakeCameraAdapter:
            def __init__(self, image_path):
                self.image_path = image_path

            def capture(self, camera_code, task_type):
                return {'success': True, 'image_path': self.image_path}

        CalibrationProfile.objects.create(
            name='foam roi',
            device_code='CAM-INSPECT-FOAM-01',
            version='foam-roi-v1',
            is_active=True,
            transform_data={
                'foam_rois': {
                    '0': {
                        'left': [0.0, 0.45, 0.28, 0.78],
                        'right': [0.72, 0.45, 1.0, 0.78],
                    },
                },
                'thresholds': {'coverage_threshold': 0.3, 'max_offset_px': 18},
            },
        )

        with TemporaryDirectory() as tmpdir:
            image_path = str(Path(tmpdir) / 'camera.png')
            cv2.imwrite(image_path, image)
            service = VisionService(camera_adapter=FakeCameraAdapter(image_path))
            result = service.inspect_foam(
                self.product,
                self.rack,
                position_index=0,
                simulated_pass=False,
                use_camera=True,
            )

        self.assertTrue(result.is_passed)
        self.assertEqual(result.result_data.get('calibration_profile'), 'foam roi')
        self.assertIn('sides', result.result_data)


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
    def test_task_list_shows_result_links_without_manual_roi_debug_buttons(self):
        response = self.client.get(reverse('vision:task_list'))

        self.assertContains(response, reverse('vision:foam_results'))
        self.assertContains(response, reverse('vision:rack_results'))
        self.assertNotContains(response, 'name="plc_sequence"')
        self.assertNotContains(response, 'PLC序号')
        self.assertNotContains(response, '2D拍照ROI')
        self.assertNotContains(response, '2D相机拍照检测ROI')
        self.assertNotContains(response, '深度相机 ROI')
        self.assertNotContains(response, '深度相机拍照检测ROI')

    def test_task_list_exposes_delete_record_button(self):
        task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )

        response = self.client.get(reverse('vision:task_list'))

        self.assertContains(response, reverse('vision:delete_task', args=[task.pk]))
        self.assertContains(response, '删除记录')
        self.assertContains(response, '确定删除这条视觉记录吗')

    def test_delete_task_requires_post(self):
        task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )

        response = self.client.get(reverse('vision:delete_task', args=[task.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(VisionTask.objects.filter(pk=task.pk).exists())

    def test_delete_task_removes_task_and_related_results(self):
        task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )
        FoamInspectionResult.objects.create(
            vision_task=task,
            position_index=1,
            is_present=True,
            is_aligned=True,
            has_lifted_edge=False,
            score=0.96,
            is_passed=True,
        )

        response = self.client.post(reverse('vision:delete_task', args=[task.pk]))

        self.assertRedirects(response, reverse('vision:task_list'))
        self.assertFalse(VisionTask.objects.filter(pk=task.pk).exists())
        self.assertEqual(FoamInspectionResult.objects.count(), 0)

    def test_foam_interactive_page_exposes_roi_calibration_controls(self):
        response = self.client.get(reverse('vision:foam_inspector_interactive'))

        self.assertContains(response, '泡棉检测工作台')
        self.assertContains(response, '白色泡棉')
        self.assertContains(response, '系统判定泡棉是否存在')
        self.assertContains(response, 'btn-start-roi')
        self.assertContains(response, 'btn-save-roi')
        self.assertContains(response, 'pos-index')
        self.assertContains(response, reverse('vision:api_foam_calibration'))
        self.assertContains(response, reverse('vision:api_foam_calibration_save'))

    def test_save_foam_roi_calibration_api_persists_active_profile(self):
        response = self.client.post(
            reverse('vision:api_foam_calibration_save'),
            data={
                'device_code': 'CAM-INSPECT-FOAM-01',
                'position_index': 2,
                'left': [0.1, 0.2, 0.3, 0.4],
                'right': [0.7, 0.2, 0.9, 0.4],
                'thresholds': {'coverage_threshold': 0.35},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        profile = CalibrationProfile.objects.get(
            device_code='CAM-INSPECT-FOAM-01',
            version='foam-roi-v1',
        )
        self.assertTrue(profile.is_active)
        self.assertEqual(
            profile.transform_data['foam_rois']['2']['left'],
            [0.1, 0.2, 0.3, 0.4],
        )
        self.assertEqual(profile.transform_data['thresholds']['coverage_threshold'], 0.35)

    def test_get_foam_roi_calibration_api_returns_active_profile(self):
        CalibrationProfile.objects.create(
            name='foam roi',
            device_code='CAM-INSPECT-FOAM-01',
            version='foam-roi-v1',
            is_active=True,
            transform_data={'foam_rois': {'1': {'left': [0, 0, 0.2, 0.2]}}},
        )

        response = self.client.get(
            reverse('vision:api_foam_calibration'),
            {'device_code': 'CAM-INSPECT-FOAM-01'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(
            payload['profile']['foam_rois']['1']['left'],
            [0, 0, 0.2, 0.2],
        )


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
