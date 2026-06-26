import json
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.constants import ResultStatus, VisionTaskType
from apps.production.models import Product, Rack, RackRecipe
from apps.vision.algorithms.foam_inspector import FoamDefectType, FoamInspector
from apps.vision.models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionRecipe,
    VisionTask,
)
from apps.vision.recipe_utils import (
    build_foam_inspection_config,
    ensure_default_foam_2d_recipes,
    serialize_recipe,
)
from apps.vision.services import VisionService


class FoamInspectorTemplateBehaviorTests(SimpleTestCase):
    def _template_source(self):
        template_path = Path(settings.BASE_DIR) / 'templates' / 'vision' / 'foam_inspector_interactive.html'
        return template_path.read_text(encoding='utf-8')

    def test_preview_image_lifecycle_reapplies_current_recipe_roi(self):
        source = self._template_source()

        self.assertIn('function refreshPreviewRecipeRoi()', source)
        self.assertIn("document.getElementById('preview-image').addEventListener('load'", source)
        self.assertIn("window.addEventListener('resize'", source)
        self.assertIn('refreshPreviewRecipeRoi();', source)

    def test_save_recipe_success_path_is_non_blocking_and_updates_local_state(self):
        source = self._template_source()

        self.assertIn('function upsertSavedRecipe(savedRecipe)', source)
        self.assertIn('showRecipeSaveSuccess(', source)
        self.assertNotIn("alert(`✓ 配方已成功保存", source)
        self.assertNotIn('await loadRecipes();  // 重新加载配方', source)

    def test_imported_preview_image_remains_detection_source_until_refresh_preview(self):
        source = self._template_source()

        self.assertIn('clearPendingFile();\n      setPreviewImage(data.image_url);', source)
        self.assertNotIn('clearPendingFile();   // 检测完成后清除暂存', source)

    def test_successful_detection_keeps_preview_on_result_recipe(self):
        source = self._template_source()

        self.assertIn('function currentDetectionPos()', source)
        self.assertIn('const detectionPos = currentDetectionPos();', source)
        self.assertIn('position_index: detectionPos,', source)
        self.assertNotIn('advanceRecipeAfterDetection', source)
        self.assertNotIn('nextRecipeAfterPos', source)

    def test_loaded_calibration_reapplies_current_recipe_roi(self):
        source = self._template_source()

        load_calibration_start = source.index('async function loadCalibration()')
        dom_ready_start = source.index("document.addEventListener('DOMContentLoaded'")
        load_calibration_source = source[load_calibration_start:dom_ready_start]
        self.assertIn('refreshPreviewRecipeRoi();', load_calibration_source)

    def test_foam_inspector_omits_session_detection_history(self):
        source = self._template_source()

        self.assertNotIn('history-panel', source)
        self.assertNotIn('history-list', source)
        self.assertNotIn('history-item', source)
        self.assertNotIn('addHistory(', source)
        self.assertNotIn('renderHistory(', source)

    def test_foam_inspector_omits_step_wizard_guidance(self):
        source = self._template_source()

        self.assertNotIn('step-wizard', source)
        self.assertNotIn('step-item', source)
        self.assertNotIn('step-num', source)
        self.assertNotIn('step-text', source)
        self.assertNotIn('function highlightStep(', source)
        self.assertNotIn('highlightStep(', source)
        self.assertNotIn('刷新预览，确认白色泡棉在保险杆上清晰可见', source)
        self.assertNotIn('系统判定泡棉是否存在，输出 OK / NG', source)


@override_settings(MEDIA_ROOT=mkdtemp())
class FoamInspectorCoverageTests(SimpleTestCase):
    def test_gray_foam_area_counts_toward_coverage_even_when_only_center_is_bright(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)

        for offset_x in (20, 120):
            cv2.rectangle(image, (offset_x + 5, 25), (offset_x + 55, 75), (135, 135, 135), -1)
            cv2.rectangle(image, (offset_x + 20, 40), (offset_x + 40, 60), (225, 225, 225), -1)

        result = FoamInspector(simulate=False).inspect(
            position_index=0,
            image=image,
            inspection_config={
                'enable_quality_analysis': False,
                'coverage_threshold': 0.5,
                'foam_rois': {
                    '0': {
                        'left': [0.1, 0.1, 0.4, 0.4],
                        'right': [0.6, 0.1, 0.9, 0.4],
                    },
                },
            },
        )

        self.assertTrue(result['is_present'])
        self.assertTrue(result['is_passed'])
        self.assertGreater(result['coverage_ratio'], 0.55)

    def test_sparse_right_side_interference_does_not_pass_as_foam(self):
        image = np.zeros((200, 240, 3), dtype=np.uint8)
        image[:, :] = (25, 25, 25)

        image[65:135, 30:90] = (138, 138, 138)
        image[80:120, 45:75] = (235, 235, 235)

        # Sparse bright structure in the right ROI: large envelope, little foam.
        image[65:125, 150:160] = (225, 225, 225)
        image[115:125, 150:210] = (225, 225, 225)

        result = FoamInspector(simulate=False).inspect(
            position_index=0,
            image=image,
            inspection_config={
                'enable_quality_analysis': False,
                'coverage_threshold': 0.3,
                'foam_rois': {
                    '0': {
                        'left': [0.08, 0.25, 0.42, 0.75],
                        'right': [0.58, 0.25, 0.92, 0.75],
                    },
                },
            },
        )

        self.assertFalse(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.MISSING)
        self.assertTrue(result['result_data']['sides']['left']['is_present'])
        self.assertFalse(result['result_data']['sides']['right']['is_present'])


class VisionRecipeModelTests(TestCase):
    def test_default_foam_2d_recipes_are_created_for_three_positions(self):
        recipes = ensure_default_foam_2d_recipes()

        self.assertEqual(len(recipes), 3)
        self.assertEqual(
            list(VisionRecipe.objects.filter(recipe_type='FOAM_2D').order_by('pos').values_list('pos', flat=True)),
            [0, 1, 2],
        )
        for recipe in recipes:
            self.assertIn('leftFoamROI', recipe.roi_config)
            self.assertIn('rightFoamROI', recipe.roi_config)

    def test_recipe_serialization_exposes_layer_name_and_roi(self):
        recipe = ensure_default_foam_2d_recipes()[1]

        payload = serialize_recipe(recipe)

        self.assertEqual(payload['recipe_type'], 'FOAM_2D')
        self.assertEqual(payload['pos'], 1)
        self.assertEqual(payload['layerName'], '第2层')
        self.assertIn('leftFoamROI', payload['roi_config'])

    def test_recipe_config_converts_pixel_roi_to_foam_inspector_ratio_config(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='测试配方',
            pos=0,
            image_width=1000,
            image_height=500,
            roi_config={
                'leftFoamROI': {'x': 100, 'y': 50, 'width': 200, 'height': 100},
                'rightFoamROI': {'x': 600, 'y': 50, 'width': 250, 'height': 100},
            },
            threshold_config={'minCoverage': 0.66, 'minScore': 0.88, 'maxOffsetX': 12, 'maxOffsetY': 18},
        )

        config = build_foam_inspection_config(recipe)

        self.assertEqual(config['foam_rois']['0']['left'], [0.1, 0.1, 0.3, 0.3])
        self.assertEqual(config['foam_rois']['0']['right'], [0.6, 0.1, 0.85, 0.3])
        self.assertEqual(config['coverage_threshold'], 0.66)
        self.assertEqual(config['score_threshold'], 0.88)
        self.assertEqual(config['max_offset_px'], 18)

    def test_recipe_config_accepts_algorithm_threshold_field_names(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='algorithm threshold recipe',
            pos=1,
            image_width=1280,
            image_height=720,
            roi_config={
                'leftFoamROI': {'x': 265, 'y': 428, 'width': 294, 'height': 269},
                'rightFoamROI': {'x': 726, 'y': 434, 'width': 213, 'height': 266},
            },
            threshold_config={
                'coverage_threshold': 0.3,
                'score_threshold': 0.4,
                'max_offset_px': 22,
            },
        )

        config = build_foam_inspection_config(recipe)

        self.assertEqual(config['coverage_threshold'], 0.3)
        self.assertEqual(config['score_threshold'], 0.4)
        self.assertEqual(config['max_offset_px'], 22)


class VisionRecipeServiceTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(product_code='P-RECIPE')
        self.rack_recipe = RackRecipe.objects.create(
            recipe_code='RCP-RECIPE',
            name='配方测试料架',
            rack_type='STD',
            layer_count=3,
            quantity_per_layer=6,
            total_quantity=18,
            layer_height=120,
            layer_spacing=150,
            tolerance_x=2,
            tolerance_y=2,
            tolerance_z=3,
        )
        self.rack = Rack.objects.create(
            rack_code='RK-RECIPE',
            current_recipe=self.rack_recipe,
        )

    def test_inspect_foam_uses_explicit_recipe_id_and_records_recipe_metadata(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='手动指定配方',
            pos=2,
            image_width=1000,
            image_height=500,
            roi_config={
                'leftFoamROI': {'x': 100, 'y': 50, 'width': 200, 'height': 100},
                'rightFoamROI': {'x': 600, 'y': 50, 'width': 250, 'height': 100},
            },
            threshold_config={'minCoverage': 0.61, 'minScore': 0.82, 'maxOffsetX': 11, 'maxOffsetY': 19},
            is_active=True,
        )

        result = VisionService().inspect_foam(
            self.product,
            self.rack,
            position_index=0,
            recipe_id=recipe.id,
            simulated_pass=True,
        )

        self.assertEqual(result.result_data['recipe']['id'], recipe.id)
        self.assertEqual(result.result_data['recipe']['name'], '手动指定配方')
        self.assertEqual(result.result_data['recipe']['pos'], 2)
        self.assertEqual(result.result_data['coverage_threshold'], 0.61)
        self.assertEqual(result.result_data['max_offset_px'], 19)

    def test_inspect_foam_falls_back_to_active_recipe_for_position_index(self):
        ensure_default_foam_2d_recipes()
        recipe = VisionRecipe.objects.get(recipe_type='FOAM_2D', pos=1)
        recipe.name = 'POS 1 自动配方'
        recipe.threshold_config = {'minCoverage': 0.64, 'minScore': 0.8, 'maxOffsetX': 9, 'maxOffsetY': 13}
        recipe.save()

        result = VisionService().inspect_foam(
            self.product,
            self.rack,
            position_index=1,
            simulated_pass=True,
        )

        self.assertEqual(result.result_data['recipe']['id'], recipe.id)
        self.assertEqual(result.result_data['recipe']['name'], 'POS 1 自动配方')
        self.assertEqual(result.result_data['recipe']['pos'], 1)
        self.assertEqual(result.result_data['max_offset_px'], 13)

    def test_inspect_foam_can_disable_recipe_lookup_and_keep_existing_behavior(self):
        ensure_default_foam_2d_recipes()

        result = VisionService().inspect_foam(
            self.product,
            self.rack,
            position_index=1,
            simulated_pass=True,
            use_recipe=False,
        )

        self.assertNotIn('recipe', result.result_data)
        self.assertEqual(result.position_index, 1)


class VisionRecipeApiTests(TestCase):
    def test_recipe_list_api_initializes_and_returns_default_foam_recipes(self):
        response = self.client.get(reverse('vision:api_vision_recipes'), {'recipe_type': 'FOAM_2D'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual([item['pos'] for item in payload['recipes']], [0, 1, 2])

    def test_recipe_by_pos_api_returns_matching_recipe(self):
        response = self.client.get(reverse('vision:api_foam_recipe_by_pos'), {'pos': 2})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['recipe']['pos'], 2)
        self.assertIn('leftFoamROI', payload['recipe']['roi_config'])

    def test_recipe_save_api_updates_only_requested_position(self):
        ensure_default_foam_2d_recipes()

        response = self.client.post(
            reverse('vision:api_foam_recipe_save'),
            data={
                'name': 'POS 1 微调配方',
                'pos': 1,
                'image_width': 1000,
                'image_height': 500,
                'roi_config': {
                    'leftFoamROI': {'x': 10, 'y': 20, 'width': 30, 'height': 40},
                    'rightFoamROI': {'x': 500, 'y': 20, 'width': 30, 'height': 40},
                },
                'threshold_config': {'minCoverage': 0.7, 'minScore': 0.8, 'maxOffsetX': 20, 'maxOffsetY': 20},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['recipe']['name'], 'POS 1 微调配方')
        self.assertEqual(VisionRecipe.objects.get(pos=0, recipe_type='FOAM_2D').name, '第1层泡棉检测配方')
        self.assertEqual(VisionRecipe.objects.get(pos=2, recipe_type='FOAM_2D').name, '第3层泡棉检测配方')

    def test_capture_inspect_api_passes_recipe_id_and_returns_recipe_payload(self):
        recipe = ensure_default_foam_2d_recipes()[0]
        task = VisionTask.objects.create(task_type=VisionTaskType.FOAM_INSPECTION, status=ResultStatus.SUCCESS)
        foam_result = FoamInspectionResult.objects.create(
            vision_task=task,
            position_index=0,
            is_present=True,
            is_aligned=True,
            has_lifted_edge=False,
            score=0.95,
            is_passed=True,
            result_data={'recipe': serialize_recipe(recipe)},
        )

        with patch('apps.vision.views.VisionService') as service_cls:
            service_cls.return_value.inspect_foam.return_value = foam_result
            response = self.client.post(
                reverse('vision:api_foam_capture_inspect'),
                data={'position_index': 0, 'recipe_id': recipe.id, 'use_recipe': True},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        service_cls.return_value.inspect_foam.assert_called_once()
        kwargs = service_cls.return_value.inspect_foam.call_args.kwargs
        self.assertEqual(kwargs['recipe_id'], recipe.id)
        self.assertTrue(kwargs['use_recipe'])
        self.assertEqual(response.json()['result']['recipe']['id'], recipe.id)

    def test_upload_inspect_api_accepts_recipe_id_and_returns_recipe_payload(self):
        recipe = ensure_default_foam_2d_recipes()[0]
        image = np.full((80, 120, 3), 220, dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(ok)
        upload = SimpleUploadedFile('foam.png', encoded.tobytes(), content_type='image/png')

        response = self.client.post(
            reverse('vision:api_foam_upload_inspect'),
            data={
                'image': upload,
                'position_index': 0,
                'recipe_id': str(recipe.id),
                'use_recipe': 'true',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['recipe']['id'], recipe.id)


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

    def test_missing_foam_marks_all_core_judgements_ng(self):
        result = FoamInspector().inspect(simulated_pass=False)

        self.assertFalse(result['is_present'])
        self.assertFalse(result['is_aligned'])
        self.assertTrue(result['has_lifted_edge'])
        self.assertEqual(result['defect_type'], FoamDefectType.MISSING)

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
        # 增大白色区域以满足覆盖率要求
        # 左侧泡棉：更大的白色区域
        image[55:85, 5:55] = 245  # 30x50 = 1500像素
        # 右侧泡棉：更大的白色区域  
        image[55:85, 165:215] = 245  # 30x50 = 1500像素

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
            'coverage_threshold_70_percent',  # 更新决策规则名称
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

    def test_calibrated_foam_annotation_draws_side_rois_without_union_box(self):
        from apps.vision.algorithms import image_io

        image = np.zeros((100, 220, 3), dtype=np.uint8)
        union_roi = (10, 20, 210, 80)
        left_roi = (10, 20, 60, 80)
        right_roi = (160, 20, 210, 80)
        result = {
            'is_passed': False,
            'is_present': False,
            'defect_type': FoamDefectType.MISSING,
            'score': 0.0,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'coverage_ratio': 0.0,
            'sides': {
                'left': {'roi': left_roi, 'box': None, 'is_present': False},
                'right': {'roi': right_roi, 'box': None, 'is_present': False},
            },
        }

        annotated = image_io.annotate_foam(
            image, union_roi, (10, 20, 10, 20), result
        )

        self.assertTrue(np.array_equal(annotated[50, 10], image_io.COLOR_MISSING))
        self.assertTrue(np.array_equal(annotated[50, 160], image_io.COLOR_MISSING))
        self.assertFalse(np.array_equal(annotated[20, 110], image_io.COLOR_MISSING))

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

    def test_calibrated_foam_detection_finds_low_light_gray_foam(self):
        """测试在低对比度场景下仍能检测到泡棉（使用较低的阈值配置）"""
        image = np.zeros((100, 220, 3), dtype=np.uint8)
        image[:, :] = (20, 20, 20)  # 黑色背景
        # 使用稍暗的白色泡棉（不是很亮但仍然是白色）
        image[10:90, 5:90] = (200, 200, 200)  # 左侧：80x85像素
        image[10:90, 130:215] = (200, 200, 200)  # 右侧：80x85像素

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.42, 0.9),  # 约92x80像素
                        'right': (0.58, 0.1, 1.0, 0.9),  # 约92x80像素
                    },
                },
                'coverage_threshold': 0.20,  # 20%阈值
                'max_offset_px': 30,
                'white_min_v': 150,  # 降低白色V值阈值
                'white_min_l': 150,  # 降低LAB L值阈值
                'side_min_area_ratio': 0.05,  # 降低最小面积要求
            },
            simulated_pass=False,
        )

        self.assertTrue(result['is_passed'])
        self.assertTrue(result['result_data']['sides']['left']['is_present'])
        self.assertTrue(result['result_data']['sides']['right']['is_present'])

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
        self.assertFalse(result['is_present'])
        self.assertFalse(result['is_aligned'])
        self.assertTrue(result['has_lifted_edge'])
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

    def test_task_list_shows_business_result_badges(self):
        ok_task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )
        FoamInspectionResult.objects.create(
            vision_task=ok_task,
            is_present=True,
            is_aligned=True,
            has_lifted_edge=False,
            is_passed=True,
        )
        ng_task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.FAILED,
        )
        FoamInspectionResult.objects.create(
            vision_task=ng_task,
            is_present=False,
            is_aligned=False,
            has_lifted_edge=True,
            is_passed=False,
        )

        response = self.client.get(reverse('vision:task_list'))

        self.assertContains(response, '<th>\u7ed3\u679c</th>', html=True)
        self.assertContains(response, '<span class="badge badge-ok">OK</span>', html=True)
        self.assertContains(response, '<span class="badge badge-fail">NG</span>', html=True)

    def test_task_list_falls_back_to_task_status_when_result_record_is_missing(self):
        VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )
        VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.FAILED,
        )

        response = self.client.get(reverse('vision:task_list'))

        self.assertContains(response, '<span class="badge badge-ok">OK</span>', html=True)
        self.assertContains(response, '<span class="badge badge-fail">NG</span>', html=True)

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
        self.assertContains(response, '泡棉存在')
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


class VisionRecipeWorkbenchTemplateTests(TestCase):
    def test_foam_workbench_exposes_recipe_drawer_and_recipe_state(self):
        response = self.client.get(reverse('vision:foam_inspector_interactive'))

        self.assertContains(response, '配方管理')
        self.assertContains(response, 'recipe-info-card')
        self.assertContains(response, 'btn-temp-recipe')
        self.assertContains(response, 'temp-recipe-modal')
        self.assertContains(response, 'manualSelectedRecipe')
        self.assertContains(response, 'currentDetectionRecipe')
        self.assertContains(response, 'recipes:')
        self.assertContains(response, 'recipe_id')


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


class RackLocationROI3DModelTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='ROI3D-POS-01-L1',
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            standard_x=0,
            standard_y=0,
            standard_z=0,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_global_and_local_roi_store_rack_coordinate_bounds(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')

        global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='左料架全局ROI',
            mode='global',
            layer_no=None,
            coordinate_system='rack',
            x_min=-300,
            x_max=300,
            y_min=-150,
            y_max=150,
            z_min=700,
            z_max=1100,
        )
        local_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='左料架第1层ROI',
            mode='local',
            layer_no=1,
            coordinate_system='rack',
            x_min=-120,
            x_max=120,
            y_min=-80,
            y_max=80,
            z_min=820,
            z_max=900,
        )

        self.assertEqual(global_roi.mode, 'global')
        self.assertIsNone(global_roi.layer_no)
        self.assertEqual(local_roi.layer_no, 1)
        self.assertEqual(float(local_roi.x_min), -120.0)
        self.assertEqual(float(local_roi.z_max), 900.0)

    def test_roi_rejects_invalid_spatial_bounds(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        roi = ROI(
            recipe=self.recipe,
            roi_name='无效ROI',
            mode='local',
            layer_no=1,
            x_min=10,
            x_max=10,
            y_min=0,
            y_max=20,
            z_min=0,
            z_max=20,
        )

        with self.assertRaisesMessage(ValidationError, 'x_min must be less than x_max'):
            roi.full_clean()

    def test_local_roi_requires_layer_and_global_roi_clears_layer(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')

        local_roi = ROI(
            recipe=self.recipe,
            roi_name='缺少层号',
            mode='local',
            layer_no=None,
            x_min=0,
            x_max=10,
            y_min=0,
            y_max=10,
            z_min=0,
            z_max=10,
        )
        with self.assertRaisesMessage(ValidationError, 'local ROI requires layer_no'):
            local_roi.full_clean()

        global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='自动清空层号',
            mode='global',
            layer_no=2,
            x_min=0,
            x_max=10,
            y_min=0,
            y_max=10,
            z_min=0,
            z_max=10,
        )
        self.assertIsNone(global_roi.layer_no)


class DMCameraRackFrameProviderTests(TestCase):
    def _recipe(self, name='Provider-POS-01-L1'):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        return Recipe.objects.create(
            recipe_name=name,
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            layer_count=3,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_provider_captures_pointcloud_without_dm_capture_record_side_effects(self):
        from apps.vision.rack_location import DMCameraRackFrameProvider

        recipe = self._recipe()

        class FakeDMCameraService:
            calls = []

            def __init__(self):
                self.is_connected = False
                self.is_streaming = False

            def connect(self):
                self.is_connected = True

            def start_stream(self):
                self.is_streaming = True

            def capture_frame_data(self, frame_type='DEPTH', save_record=True):
                self.calls.append((frame_type, save_record))
                return {
                    'frame_type': frame_type,
                    'data': np.zeros((2, 2, 3), dtype=float),
                    'width': 2,
                    'height': 2,
                }

        with patch('apps.dm_camera.services.DMCameraService', FakeDMCameraService):
            payload = DMCameraRackFrameProvider().capture(recipe, position_no=1, layer_no=1)

        self.assertEqual(FakeDMCameraService.calls, [('POINTCLOUD', False)])
        self.assertEqual(payload['source'], 'dm_camera')
        self.assertEqual(payload['organized_pointcloud'].shape, (2, 2, 3))

    @override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=True)
    def test_provider_can_force_sample_without_touching_dm_service(self):
        from apps.vision.rack_location import DMCameraRackFrameProvider

        class UnexpectedDMCameraService:
            def __init__(self):
                raise AssertionError('DM service should not be instantiated')

        with patch('apps.dm_camera.services.DMCameraService', UnexpectedDMCameraService):
            payload = DMCameraRackFrameProvider().capture(self._recipe('Forced-Sample'), 1, 1)

        self.assertEqual(payload['source'], 'sample_forced')
        self.assertIn('raw_data_path', payload)


class RackLocationRecipe3DModelTests(TestCase):
    def test_position_recipe_matches_enabled_position_and_layer_without_side_split(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')

        recipe = Recipe.objects.create(
            recipe_name='POS-05-L2',
            rack_type='STD',
            rack_side='BOTH',
            position_no=5,
            layer_no=2,
            standard_x=100,
            standard_y=200,
            standard_z=300,
            hand_eye_config={'matrix': 'identity'},
        )

        self.assertTrue(recipe.applies_to(position_no=5, layer_no=2))
        self.assertFalse(recipe.applies_to(position_no=5, layer_no=1))
        self.assertFalse(recipe.applies_to(position_no=6, layer_no=2))

    def test_default_thresholds_are_safe_for_3d_compensation(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')

        recipe = Recipe.objects.create(
            recipe_name='DEFAULT-3D',
            rack_side='BOTH',
            position_no=1,
            layer_no=1,
            hand_eye_config={'matrix': 'identity'},
        )

        self.assertEqual(float(recipe.max_offset_x), 10.0)
        self.assertEqual(float(recipe.max_offset_y), 10.0)
        self.assertEqual(float(recipe.max_offset_z), 10.0)
        self.assertEqual(float(recipe.confidence_threshold), 0.7)

    def test_rack_location_result_has_actual_xyz_fields_for_traceability(self):
        Result = apps.get_model('vision', 'RackLocationResult')

        field_names = {field.name for field in Result._meta.fields}

        self.assertIn('actual_x', field_names)
        self.assertIn('actual_y', field_names)
        self.assertIn('actual_z', field_names)


class RackPoseEstimator3DTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='POSE-POS-07',
            rack_side='BOTH',
            position_no=7,
            layer_no=3,
            standard_x=100,
            standard_y=200,
            standard_z=300,
            max_offset_x=5,
            max_offset_y=5,
            max_offset_z=5,
            confidence_threshold=0.8,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_calculate_rack_offset_uses_position_standard_pose_in_mm(self):
        from apps.vision.rack_location import RackPoseEstimator

        output = RackPoseEstimator().calculate_rack_offset(
            {
                'actual_x': 101.5,
                'actual_y': 198.0,
                'actual_z': 300.5,
                'offset_rz': 0.12,
                'confidence': 0.93,
                'raw_data_path': 'vision/sample/pos7.npy',
            },
            self.recipe,
            rack_side='BOTH',
            layer_no=3,
        )

        self.assertTrue(output.locate_ok)
        self.assertEqual(output.rack_side, 'BOTH')
        self.assertEqual(output.position_no, 7)
        self.assertEqual(output.layer_no, 3)
        self.assertEqual(output.offset_x, 1.5)
        self.assertEqual(output.offset_y, -2.0)
        self.assertEqual(output.offset_z, 0.5)
        self.assertEqual(output.offset_rz, 0.12)
        self.assertEqual(output.confidence, 0.93)
        self.assertEqual(output.actual_x, 101.5)
        self.assertEqual(output.actual_y, 198.0)
        self.assertEqual(output.actual_z, 300.5)

    def test_calculate_rack_offset_rejects_low_confidence(self):
        from apps.vision.rack_location import RackPoseEstimator

        output = RackPoseEstimator().calculate_rack_offset(
            {'actual_x': 100, 'actual_y': 200, 'actual_z': 300, 'confidence': 0.2},
            self.recipe,
            rack_side='BOTH',
            layer_no=3,
        )

        self.assertFalse(output.locate_ok)
        self.assertEqual(output.error_code, 'LOW_CONFIDENCE')

    def test_calculate_rack_offset_rejects_missing_hand_eye_config(self):
        from apps.vision.rack_location import RackPoseEstimator

        self.recipe.hand_eye_config = {}
        self.recipe.save(update_fields=['hand_eye_config'])

        output = RackPoseEstimator().calculate_rack_offset(
            {'actual_x': 100, 'actual_y': 200, 'actual_z': 300, 'confidence': 0.95},
            self.recipe,
            rack_side='BOTH',
            layer_no=3,
        )

        self.assertFalse(output.locate_ok)
        self.assertEqual(output.error_code, 'MISSING_HAND_EYE')


class RackLocationPointCloudProcessorTests(SimpleTestCase):
    def test_crop_by_roi_filters_invalid_points_and_calculates_median_xyz(self):
        from apps.vision.rack_location import PointCloudProcessor

        pointcloud = np.zeros((4, 5, 3), dtype=float)
        pointcloud[1, 1] = [1199.0, 348.0, 849.0]
        pointcloud[1, 2] = [1201.0, 350.0, 851.0]
        pointcloud[2, 1] = [1203.0, 352.0, 853.0]
        pointcloud[2, 2] = [np.nan, 1.0, 2.0]
        pointcloud[2, 3] = [1.0, 2.0, 0.0]

        processor = PointCloudProcessor()
        points = processor.crop_by_roi(pointcloud, {'x': 1, 'y': 1, 'w': 3, 'h': 2})
        actual_x, actual_y, actual_z = processor.calculate_median_xyz(points)

        self.assertEqual(points.shape, (3, 3))
        self.assertEqual((actual_x, actual_y, actual_z), (1201.0, 350.0, 851.0))

    def test_crop_by_roi_rejects_roi_outside_pointcloud_bounds(self):
        from apps.vision.rack_location import PointCloudProcessor

        processor = PointCloudProcessor()
        pointcloud = np.zeros((4, 5, 3), dtype=float)

        with self.assertRaisesMessage(ValueError, 'ROI 超出图像范围'):
            processor.crop_by_roi(pointcloud, {'x': 4, 'y': 1, 'w': 3, 'h': 2})

    def test_crop_by_roi_3d_filters_points_inside_spatial_box(self):
        from apps.vision.rack_location import PointCloudProcessor

        pointcloud = np.array([
            [[0, 0, 10], [5, 5, 15], [20, 0, 10]],
            [[2, 4, 12], [9, 9, 19], [np.nan, 1, 1]],
        ], dtype=float)
        processor = PointCloudProcessor()

        points = processor.crop_by_roi_3d(pointcloud, {
            'x_min': 0,
            'x_max': 10,
            'y_min': 0,
            'y_max': 10,
            'z_min': 10,
            'z_max': 20,
        })

        self.assertEqual(points.shape, (4, 3))
        self.assertTrue(np.all(points[:, 0] >= 0))
        self.assertTrue(np.all(points[:, 0] <= 10))
        self.assertTrue(np.all(points[:, 2] >= 10))
        self.assertTrue(np.all(points[:, 2] <= 20))

    def test_crop_by_roi_3d_rejects_invalid_bounds(self):
        from apps.vision.rack_location import PointCloudProcessor

        pointcloud = np.zeros((2, 2, 3), dtype=float)

        with self.assertRaisesMessage(ValueError, 'x_min must be less than x_max'):
            PointCloudProcessor().crop_by_roi_3d(pointcloud, {
                'x_min': 5,
                'x_max': 5,
                'y_min': 0,
                'y_max': 10,
                'z_min': 0,
                'z_max': 10,
            })


class RackLocationService3DTests(TestCase):
    class StaticFrameProvider:
        def capture(self, recipe, position_no, layer_no):
            return {
                'source': 'sample',
                'actual_x': 102.0,
                'actual_y': 198.5,
                'actual_z': 299.0,
                'confidence': 0.91,
                'raw_data_path': 'vision/sample_depth/pos-05-layer-02.npy',
                'result_image_path': 'vision/results/pos-05-layer-02.png',
            }

    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='SERVICE-POS-05-L2',
            rack_side='BOTH',
            position_no=5,
            layer_no=2,
            standard_x=100,
            standard_y=200,
            standard_z=300,
            max_offset_x=5,
            max_offset_y=5,
            max_offset_z=5,
            confidence_threshold=0.8,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_trigger_creates_single_position_layer_result_and_plc_payload(self):
        from apps.vision.rack_location import RackLocationService

        result = RackLocationService(frame_provider=self.StaticFrameProvider()).trigger(
            position_no=5,
            layer_no=2,
            write_plc=False,
        )

        self.assertTrue(result.is_success)
        self.assertEqual(result.side, 'BOTH')
        self.assertEqual(result.layer_no, 2)
        self.assertEqual(result.recipe, self.recipe)
        self.assertEqual(float(result.offset_x), 2.0)
        self.assertEqual(float(result.offset_y), -1.5)
        self.assertEqual(float(result.offset_z), -1.0)
        self.assertEqual(float(result.actual_x), 102.0)
        self.assertEqual(float(result.actual_y), 198.5)
        self.assertEqual(float(result.actual_z), 299.0)
        self.assertEqual(float(result.confidence), 0.91)
        self.assertEqual(result.raw_data_path, 'vision/sample_depth/pos-05-layer-02.npy')
        self.assertEqual(result.result_data['position_no'], 5)
        self.assertEqual(result.result_data['plc_payload']['position_no'], 5)
        self.assertEqual(RackLocationResult.objects.count(), 1)


@override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class RackLocation3DViewTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='API-POS-03-L1',
            rack_side='BOTH',
            position_no=3,
            layer_no=1,
            standard_x=100,
            standard_y=200,
            standard_z=300,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_rack_locator_panel_exposes_3d_roi_workbench_controls(self):
        response = self.client.get(reverse('vision:rack_locator_panel'))

        self.assertContains(response, '3D 料架定位工作台')
        self.assertContains(response, 'rack-side')
        self.assertContains(response, '左料架')
        self.assertContains(response, '右料架')
        self.assertContains(response, 'locate-mode')
        self.assertContains(response, 'roi-x-min')
        self.assertContains(response, 'roi-x-max')
        self.assertContains(response, 'roi-y-min')
        self.assertContains(response, 'roi-y-max')
        self.assertContains(response, 'roi-z-min')
        self.assertContains(response, 'roi-z-max')
        self.assertContains(response, 'btn-auto-align')
        self.assertContains(response, 'btn-save-roi')
        self.assertContains(response, 'btn-write-plc')
        self.assertContains(response, 'api_vision_3d_capture')
        self.assertContains(response, 'api_vision_3d_test_locate')

    def test_workbench_javascript_preserves_unified_api_success_flag(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')

        self.assertIn('success: data.success', script)
        self.assertIn("error: data.error || ''", script)

    def test_recipe_create_page_contains_depth_image_roi_teaching_ui(self):
        response = self.client.get(reverse('vision:rack_location_recipe_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '3D 料架定位配方')
        self.assertContains(response, '3D 深度图 / 伪彩图')
        self.assertContains(response, 'rack-location-canvas')
        self.assertContains(response, 'name="roi_config"')
        self.assertContains(response, '预计算标准坐标')
        self.assertContains(response, '保存为标准位置')

    def test_preview_calculate_api_returns_actual_xyz_offsets_from_roi_pointcloud(self):
        from apps.vision.rack_location import sample_scene_median_xyz

        roi = {'x': 250, 'y': 180, 'w': 140, 'h': 90, 'feature_type': 'rack_reference'}
        # 标准坐标取该 ROI 在同源标准场景中的中位数，因此默认偏差≈0、定位 OK。
        expected_x, expected_y, expected_z = sample_scene_median_xyz(
            {'x': roi['x'], 'y': roi['y'], 'w': roi['w'], 'h': roi['h']}
        )
        response = self.client.post(
            reverse('vision:rack_location_preview_calculate'),
            data=json.dumps({
                'recipe_id': self.recipe.id,
                'roi_config': {'target_roi': roi},
                'recipe_data': {
                    'standard_x': expected_x,
                    'standard_y': expected_y,
                    'standard_z': expected_z,
                    'confidence_threshold': 0.7,
                    'max_offset_x': 20,
                    'max_offset_y': 20,
                    'max_offset_z': 20,
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['result']['locate_ok'])
        # 实际坐标来自 ROI 裁剪点云中位数，而非写死常量。
        self.assertAlmostEqual(payload['result']['actual_x'], expected_x, places=2)
        self.assertAlmostEqual(payload['result']['actual_y'], expected_y, places=2)
        self.assertAlmostEqual(payload['result']['actual_z'], expected_z, places=2)
        self.assertAlmostEqual(payload['result']['offset_x'], 0.0, places=2)
        self.assertAlmostEqual(payload['result']['offset_y'], 0.0, places=2)
        self.assertAlmostEqual(payload['result']['offset_z'], 0.0, places=2)

    def test_preview_calculate_is_roi_responsive(self):
        """不同 ROI 位置必须裁剪到点云的不同区域，得到不同的实际坐标——
        证明 ROI 真正驱动点云计算，而不是返回写死值。"""
        def actual_for(roi):
            response = self.client.post(
                reverse('vision:rack_location_preview_calculate'),
                data=json.dumps({
                    'recipe_id': self.recipe.id,
                    'roi_config': {'target_roi': roi},
                    'recipe_data': {
                        'standard_x': 0, 'standard_y': 0, 'standard_z': 0,
                        'confidence_threshold': 0.4,
                        'max_offset_x': 9999, 'max_offset_y': 9999, 'max_offset_z': 9999,
                    },
                }),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body['success'])
            r = body['result']
            return (r['actual_x'], r['actual_y'], r['actual_z'])

        left = actual_for({'x': 50, 'y': 60, 'w': 120, 'h': 120})
        right = actual_for({'x': 450, 'y': 300, 'w': 120, 'h': 120})
        self.assertNotAlmostEqual(left[0], right[0], places=1)
        self.assertNotAlmostEqual(left[2], right[2], places=1)
        # 左上 ROI 的 X 应小于右下 ROI（像素 x 更小 → 相机坐标 X 更小）。
        self.assertLess(left[0], right[0])

    def test_task_list_has_single_3d_entry_without_new_old_labels(self):
        response = self.client.get(reverse('vision:task_list'))

        self.assertContains(response, reverse('vision:rack_locator_panel'))
        self.assertContains(response, '进入3D料架定位工作台')
        self.assertNotContains(response, '旧3D调试面板')
        self.assertNotContains(response, '旧料架定位结果')

    def test_trigger_api_returns_current_compensation_data_for_frontend(self):
        response = self.client.post(
            reverse('vision:api_rack_location_trigger'),
            data={
                'position_no': 3,
                'layer_no': 1,
                'recipe_id': self.recipe.id,
                'write_plc': 'false',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['task_kind'], 'RACK_3D_LOCATION')
        self.assertEqual(payload['result']['position_no'], 3)
        self.assertEqual(payload['result']['layer_no'], 1)
        self.assertIn('offset_x', payload['result'])
        self.assertIn('plc_payload', payload['result'])

    def test_old_trigger_endpoint_can_locate_with_3d_roi_recipe(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        ROI.objects.create(
            recipe=self.recipe,
            roi_name='兼容全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )

        response = self.client.post(
            reverse('vision:api_rack_location_trigger'),
            data={
                'position_no': 3,
                'layer_no': 1,
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'write_plc': 'false',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['rack_side'], 'LEFT')
        self.assertIn('plc_payload', payload['result'])

    def test_results_api_filters_by_position_and_layer(self):
        from apps.vision.rack_location import RackLocationService

        RackLocationService().trigger(position_no=3, layer_no=1, recipe_id=self.recipe.id)

        response = self.client.get(
            reverse('vision:api_rack_location_results'),
            {'position_no': 3, 'layer_no': 1},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['results'][0]['position_no'], 3)
        self.assertEqual(payload['results'][0]['layer_no'], 1)


@override_settings(MEDIA_ROOT=mkdtemp())
class RackLocationWorkbenchTests(TestCase):
    """3D 工作台：采集点云 → 画 ROI → 计算 → 保存。"""

    class CloudFrameProvider:
        """提供一个组织化点云帧，模拟真实 3D 相机已返回 organized_pointcloud。"""
        def capture(self, recipe, position_no, layer_no):
            from apps.vision.rack_location import build_sample_pointcloud
            return {
                'source': 'dm_camera',
                'organized_pointcloud': build_sample_pointcloud(side='LEFT', layer_count=3),
            }

    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        from apps.vision.rack_location import sample_scene_median_xyz
        self.roi = {'x': 250, 'y': 180, 'w': 140, 'h': 90, 'feature_type': 'rack_reference'}
        sx, sy, sz = sample_scene_median_xyz(
            {'x': self.roi['x'], 'y': self.roi['y'], 'w': self.roi['w'], 'h': self.roi['h']}
        )
        self.recipe = Recipe.objects.create(
            recipe_name='WB-POS-02-L1',
            rack_side='BOTH',
            position_no=2,
            layer_no=1,
            layer_count=3,
            standard_x=round(sx, 3),
            standard_y=round(sy, 3),
            standard_z=round(sz, 3),
            max_offset_x=20,
            max_offset_y=20,
            max_offset_z=20,
            confidence_threshold=0.5,
            hand_eye_config={'matrix': 'identity'},
        )

    def _service(self):
        from apps.vision.rack_location import RackLocationService
        return RackLocationService(frame_provider=self.CloudFrameProvider())

    def test_capture_workbench_persists_pointcloud_and_returns_preview(self):
        payload = self._service().capture_workbench(recipe_id=self.recipe.id)
        self.assertTrue(payload['pointcloud_token'].endswith('.npy'))
        self.assertIn('rack_workbench', payload['pointcloud_token'])
        self.assertTrue(payload['preview_image_url'])
        self.assertGreater(payload['image_width'], 0)
        self.assertGreater(payload['image_height'], 0)
        abs_path = Path(settings.MEDIA_ROOT) / payload['pointcloud_token']
        self.assertTrue(abs_path.exists())

    def test_capture_workbench_falls_back_to_sample_when_camera_unavailable(self):
        from apps.vision.rack_location import RackLocationService

        class BrokenProvider:
            def capture(self, recipe, position_no, layer_no):
                raise RuntimeError('camera offline')

        payload = RackLocationService(frame_provider=BrokenProvider()).capture_workbench(
            recipe_id=self.recipe.id
        )
        self.assertEqual(payload['source'], 'sample')
        self.assertTrue((Path(settings.MEDIA_ROOT) / payload['pointcloud_token']).exists())

    def test_calculate_workbench_crops_persisted_cloud_without_db_write(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config={'target_roi': self.roi},
            recipe_id=self.recipe.id,
        )
        self.assertTrue(result['locate_ok'])
        self.assertLess(abs(result['offset_x']), 20)
        self.assertTrue(result['result_image_url'].endswith('.png') or 'rack_workbench' in result['result_image_url'])
        self.assertEqual(RackLocationResult.objects.count(), 0)

    def test_calculate_workbench_requires_roi(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        with self.assertRaises(ValueError):
            service.calculate_workbench(
                token=captured['pointcloud_token'],
                roi_config={},
                recipe_id=self.recipe.id,
            )

    def test_calculate_workbench_rejects_stale_token(self):
        with self.assertRaises(ValueError):
            self._service().calculate_workbench(
                token='vision/rack_workbench/does/not/exist.npy',
                roi_config={'target_roi': self.roi},
                recipe_id=self.recipe.id,
            )

    def test_save_workbench_result_writes_single_row(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        result = service.save_workbench_result(
            token=captured['pointcloud_token'],
            roi_config={'target_roi': self.roi},
            recipe_id=self.recipe.id,
            position_no=2,
            layer_no=1,
        )
        self.assertEqual(RackLocationResult.objects.count(), 1)
        self.assertEqual(result.recipe, self.recipe)
        self.assertEqual(result.position_no, 2)
        self.assertEqual(result.layer_no, 1)
        self.assertEqual(result.plc_write_status, 'SKIPPED')
        self.assertTrue(result.result_image_path)

    def test_workbench_api_capture_calculate_save_roundtrip(self):
        from unittest.mock import patch
        from apps.vision.rack_location import RackLocationService

        def make_service(*args, **kwargs):
            kwargs.setdefault('frame_provider', self.CloudFrameProvider())
            return RackLocationService(**kwargs)

        with patch('apps.vision.views.RackLocationService', side_effect=make_service):
            cap = self.client.post(
                reverse('vision:api_rack_location_workbench_capture'),
                data=json.dumps({'recipe_id': self.recipe.id}),
                content_type='application/json',
            ).json()
            self.assertTrue(cap['success'])

            calc = self.client.post(
                reverse('vision:api_rack_location_workbench_calculate'),
                data=json.dumps({
                    'pointcloud_token': cap['pointcloud_token'],
                    'roi_config': {'target_roi': self.roi},
                    'recipe_id': self.recipe.id,
                }),
                content_type='application/json',
            ).json()
            self.assertTrue(calc['success'])
            self.assertIn('result_image_url', calc['result'])

            save = self.client.post(
                reverse('vision:api_rack_location_workbench_save'),
                data=json.dumps({
                    'pointcloud_token': cap['pointcloud_token'],
                    'roi_config': {'target_roi': self.roi},
                    'recipe_id': self.recipe.id,
                    'position_no': 2,
                    'layer_no': 1,
                }),
                content_type='application/json',
            ).json()
            self.assertTrue(save['success'])
        self.assertEqual(RackLocationResult.objects.count(), 1)

    def test_old_workbench_calculate_accepts_3d_roi_payload(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)

        response = self.client.post(
            reverse('vision:api_rack_location_workbench_calculate'),
            data=json.dumps({
                'pointcloud_token': captured['pointcloud_token'],
                'roi_3d': {
                    'x_min': -500,
                    'x_max': 500,
                    'y_min': -300,
                    'y_max': 300,
                    'z_min': 500,
                    'z_max': 1400,
                },
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'layer_no': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['roi_source'], 'request')


@override_settings(MEDIA_ROOT=mkdtemp())
class Rack3DLocatorServiceTests(TestCase):
    class CloudFrameProvider:
        def capture(self, recipe, position_no, layer_no):
            from apps.vision.rack_location import build_sample_pointcloud
            return {
                'source': 'dm_camera',
                'organized_pointcloud': build_sample_pointcloud(side='LEFT', layer_count=3),
            }

    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        self.recipe = Recipe.objects.create(
            recipe_name='LOCATOR-LEFT-L1',
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )
        self.global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )
        self.local_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='第1层ROI',
            mode='local',
            layer_no=1,
            x_min=-250,
            x_max=250,
            y_min=-180,
            y_max=180,
            z_min=650,
            z_max=1200,
        )

    def _locator(self):
        from apps.vision.rack_location import Rack3DLocator
        return Rack3DLocator(frame_provider=self.CloudFrameProvider())

    def test_capture_returns_token_and_observation_images(self):
        payload = self._locator().capture(recipe_id=self.recipe.id)

        self.assertTrue(payload['pointcloud_token'].endswith('.npy'))
        self.assertTrue(payload['pointcloud_preview_url'])
        self.assertIn('raw_rgb_image_url', payload)
        self.assertIn('raw_depth_image_url', payload)
        self.assertEqual(payload['source'], 'dm_camera')

    def test_auto_align_returns_rack_coordinate_system_and_corrected_views(self):
        captured = self._locator().capture(recipe_id=self.recipe.id)

        payload = self._locator().auto_align(
            token=captured['pointcloud_token'],
            recipe_id=self.recipe.id,
        )

        self.assertEqual(payload['coordinate_system']['name'], 'rack')
        self.assertEqual(payload['coordinate_system']['transform_matrix'][0], [1, 0, 0, 0])
        self.assertTrue(payload['views']['front_view_url'])
        self.assertTrue(payload['views']['top_view_url'])
        self.assertTrue(payload['views']['side_view_url'])

    def test_test_locate_uses_request_roi_without_saving(self):
        captured = self._locator().capture(recipe_id=self.recipe.id)

        payload = self._locator().test_locate(
            token=captured['pointcloud_token'],
            roi_3d={
                'x_min': -250,
                'x_max': 250,
                'y_min': -180,
                'y_max': 180,
                'z_min': 650,
                'z_max': 1200,
            },
            recipe_id=self.recipe.id,
            rack_side='LEFT',
            layer_no=1,
        )

        self.assertIn('offset_x', payload)
        self.assertIn('confidence', payload)
        self.assertEqual(payload['roi_source'], 'request')
        self.assertTrue(payload['cropped_preview_url'])
        self.assertEqual(apps.get_model('vision', 'RackLocationResult').objects.count(), 0)

    def test_locate_loads_local_roi_before_global_roi(self):
        result = self._locator().locate(
            rack_side='LEFT',
            layer_no=1,
            recipe_id=self.recipe.id,
            write_plc=False,
        )

        self.assertEqual(result.side, 'LEFT')
        self.assertEqual(result.result_data['roi_id'], self.local_roi.id)
        self.assertEqual(result.result_data['roi_source'], 'local')
        self.assertIn('plc_payload', result.result_data)


@override_settings(MEDIA_ROOT=mkdtemp(), VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class Rack3DLocatorApiTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='API-3D-LEFT-L1',
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_vision_3d_recipe_crud_uses_unified_response(self):
        create = self.client.post(
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({
                'recipe_name': 'API-3D-RIGHT-L2',
                'rack_side': 'RIGHT',
                'rack_type': 'STD',
                'position_no': 2,
                'layer_no': 2,
                'layer_count': 3,
                'standard_x': 10,
                'standard_y': 20,
                'standard_z': 900,
                'hand_eye_config': {'matrix': 'identity'},
            }),
            content_type='application/json',
        )
        self.assertEqual(create.status_code, 200)
        created = create.json()
        self.assertTrue(created['success'])
        self.assertEqual(created['error'], '')
        recipe_id = created['data']['recipe']['id']

        detail = self.client.get(reverse('vision:api_vision_3d_recipe_detail', args=[recipe_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['data']['recipe']['rack_side'], 'RIGHT')

        update = self.client.put(
            reverse('vision:api_vision_3d_recipe_detail', args=[recipe_id]),
            data=json.dumps({'enabled': False, 'rack_type': 'UPDATED'}),
            content_type='application/json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertFalse(update.json()['data']['recipe']['enabled'])

    def test_vision_3d_roi_crud(self):
        create = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.recipe.id,
                'roi_name': '第1层ROI',
                'mode': 'local',
                'layer_no': 1,
                'coordinate_system': 'rack',
                'x_min': -200,
                'x_max': 200,
                'y_min': -150,
                'y_max': 150,
                'z_min': 600,
                'z_max': 1200,
            }),
            content_type='application/json',
        )
        self.assertEqual(create.status_code, 200)
        roi_id = create.json()['data']['roi']['id']

        listing = self.client.get(reverse('vision:api_vision_3d_rois'), {'recipe_id': self.recipe.id})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['data']['rois'][0]['id'], roi_id)

        update = self.client.put(
            reverse('vision:api_vision_3d_roi_detail', args=[roi_id]),
            data=json.dumps({'x_min': -180, 'x_max': 180}),
            content_type='application/json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()['data']['roi']['x_min'], -180.0)

    def test_vision_3d_capture_align_test_locate_and_write_plc(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        ROI.objects.create(
            recipe=self.recipe,
            roi_name='全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )

        capture = self.client.post(
            reverse('vision:api_vision_3d_capture'),
            data=json.dumps({'recipe_id': self.recipe.id, 'rack_side': 'LEFT', 'layer_no': 1}),
            content_type='application/json',
        )
        self.assertEqual(capture.status_code, 200)
        token = capture.json()['data']['pointcloud_token']

        align = self.client.post(
            reverse('vision:api_vision_3d_auto_align'),
            data=json.dumps({'pointcloud_token': token, 'recipe_id': self.recipe.id}),
            content_type='application/json',
        )
        self.assertEqual(align.status_code, 200)
        self.assertEqual(align.json()['data']['coordinate_system']['name'], 'rack')

        locate = self.client.post(
            reverse('vision:api_vision_3d_test_locate'),
            data=json.dumps({
                'pointcloud_token': token,
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'layer_no': 1,
                'roi': {
                    'x_min': -500,
                    'x_max': 500,
                    'y_min': -300,
                    'y_max': 300,
                    'z_min': 500,
                    'z_max': 1400,
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(locate.status_code, 200)
        self.assertIn('offset_x', locate.json()['data']['result'])

        result = self.client.post(
            reverse('vision:api_vision_3d_write_plc'),
            data=json.dumps({'result_id': 999999}),
            content_type='application/json',
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.json()['success'])
        self.assertIn('error', result.json())
