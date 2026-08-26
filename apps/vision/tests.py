import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.apps import apps
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.urls import NoReverseMatch, reverse

from apps.core.constants import ResultStatus, VisionImageType, VisionTaskType
from apps.production.models import Product, Rack, RackRecipe
from apps.vision.algorithms.foam_inspector import (
    FoamDefectType,
    FoamInspector,
    StandardMaskConfigurationError,
    compute_coverage_ratio,
    compute_iou,
    compute_mask_centroid,
    generate_foam_mask,
)
from apps.vision.models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)
from apps.vision.recipe_utils import (
    build_foam_inspection_config,
    ensure_default_foam_2d_recipes,
    serialize_recipe,
)
from apps.vision.services import VisionService


class RackMasterRecipeApiTests(TestCase):
    def setUp(self):
        self.master = RackRecipe.objects.create(
            recipe_code='MES-RACK-A',
            name='A产品三层料架',
            product_code='PRODUCT-A',
            rack_type='RACK-A',
            station_position_count=2,
            layer_count=3,
            quantity_per_layer=5,
            total_quantity=15,
            layer_height=120,
            layer_spacing=150,
        )
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.vision_recipe = Recipe.objects.create(
            recipe_name='RACK-A-P1-L2',
            rack_type='RACK-A',
            position_no=1,
            layer_no=2,
            roi_config={
                'target_roi': {'x': 1, 'y': 1, 'w': 10, 'h': 10},
                'local_template_rois': {
                    'plane1': {'x': 1}, 'plane2': {'x': 2}, 'plane3': {'x': 3},
                },
            },
            local_template_std={'origin': [0, 0, 0]},
            hand_eye_config={'matrix': 'identity'},
        )

    def test_mapping_save_and_progress_resolution(self):
        mapping_response = self.client.post(
            reverse('vision:api_rack_master_mapping_save'),
            data=json.dumps({
                'rack_recipe_id': self.master.id,
                'station_position_no': 1,
                'layer_no': 2,
                'rack_location_recipe_id': self.vision_recipe.id,
                'robot_target_code': 'ROBOT-P1-L2',
            }),
            content_type='application/json',
        )
        self.assertEqual(mapping_response.status_code, 200, mapping_response.content)

        response = self.client.get(
            reverse('vision:api_rack_master_recipe_resolve', args=[self.master.id]),
            {'completed_quantity': 5, 'station_position_no': 1},
        )
        self.assertEqual(response.status_code, 200, response.content)
        resolution = response.json()['resolution']
        self.assertEqual(resolution['current'], {
            'position_index': 5, 'layer_no': 2, 'slot_no': 1,
        })
        self.assertEqual(resolution['rack_location_recipe_id'], self.vision_recipe.id)

    def test_list_does_not_create_or_rebind_mappings(self):
        response = self.client.get(reverse('vision:api_rack_master_recipes'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recipes'][0]['validation']['mapping_total_count'], 6)
        self.assertEqual(self.master.vision_mappings.count(), 0)

    def test_recipe_page_only_exposes_3d_technical_recipe_library(self):
        response = self.client.get(
            reverse('vision:recipe_management') + '?tab=rack3d'
        )

        self.assertContains(response, '3D 定位技术配方库')
        self.assertContains(response, 'rack3d-recipe-list')
        self.assertContains(response, 'recipe-card-summary')
        self.assertContains(response, '层料架配方')
        self.assertContains(response, '料架号：')
        self.assertContains(response, '修改命名')
        self.assertContains(response, '增加（复制）')
        self.assertContains(response, 'recipe-delete-button')
        self.assertContains(response, 'recipe-rename-modal')
        self.assertNotContains(response, '工位位置 <span')
        self.assertNotContains(response, '适用层号 <span')
        self.assertNotContains(response, '料架装箱配方管理')
        self.assertNotContains(response, '泡棉检测配方（2D）')
        self.assertNotContains(response, '空箱检测配方（2D）')


class RackStructureValidatorThresholdTests(SimpleTestCase):
    @staticmethod
    def _plane(inlier_ratio):
        from apps.vision.algorithms.local_template_3d import PlaneResult

        return PlaneResult(
            normal=np.array([0.0, 0.0, 1.0]),
            offset=0.0,
            centroid=np.zeros(3),
            inlier_ratio=inlier_ratio,
            point_count=100,
        )

    def test_default_inlier_threshold_is_sixty_percent_inclusive(self):
        from apps.vision.algorithms.rack_structure_validator import RackStructureValidator

        frame = SimpleNamespace(
            plane1=self._plane(0.60),
            plane2=self._plane(0.599),
            plane3=self._plane(0.75),
        )

        checks = RackStructureValidator()._check_inlier_ratios(frame)

        self.assertEqual([check.threshold for check in checks], [60.0, 60.0, 60.0])
        self.assertEqual([check.passed for check in checks], [True, False, True])
        self.assertIn('低于阈值 60%', checks[1].message)

    def test_failed_geometry_is_invalid_instead_of_diagnostic_only(self):
        from apps.vision.algorithms.local_template_3d import PlaneResult
        from apps.vision.algorithms.rack_structure_validator import RackStructureValidator

        def plane(normal):
            return PlaneResult(
                normal=np.asarray(normal, dtype=float),
                offset=0.0,
                centroid=np.zeros(3),
                inlier_ratio=0.9,
                point_count=100,
            )

        frame = SimpleNamespace(
            plane1=plane([0, 0, 1]),
            plane2=plane([0, 1, 0]),
            plane3=plane([1, 0, 0]),
            z_local=np.array([1, 0, 1], dtype=float) / np.sqrt(2),
        )

        validation = RackStructureValidator().validate(frame_cur=frame)

        self.assertFalse(validation.is_valid)
        self.assertEqual(validation.error_code.value, 'TILT')


class LocalTemplateDeterminismTests(SimpleTestCase):
    @staticmethod
    def _clouds():
        rng = np.random.default_rng(20260817)

        def horizontal(z):
            xy = rng.uniform(-200, 200, size=(800, 2))
            plane = np.column_stack([xy, rng.normal(z, 0.15, size=800)])
            outliers = rng.uniform([-200, -200, z - 80], [200, 200, z + 80], size=(120, 3))
            return np.vstack([plane, outliers])

        yz = rng.uniform([-200, 750], [200, 1050], size=(800, 2))
        vertical = np.column_stack([
            rng.normal(100, 0.15, size=800), yz[:, 0], yz[:, 1],
        ])
        vertical_outliers = rng.uniform([-20, -200, 750], [220, 200, 1050], size=(120, 3))
        return horizontal(1000), np.vstack([vertical, vertical_outliers]), horizontal(800)

    def test_repeated_fit_of_identical_cloud_is_deterministic(self):
        from apps.vision.algorithms.local_template_3d import LocalTemplate3D

        clouds = self._clouds()
        algorithm = LocalTemplate3D(ransac_num_iterations=300)

        first = algorithm.build_local_frame(*clouds)
        second = algorithm.build_local_frame(*clouds)

        np.testing.assert_allclose(first.T, second.T, atol=1e-12)
        for name in ('plane1', 'plane2', 'plane3'):
            first_plane = getattr(first, name)
            second_plane = getattr(second, name)
            np.testing.assert_allclose(first_plane.normal, second_plane.normal, atol=1e-12)
            self.assertAlmostEqual(first_plane.offset, second_plane.offset, places=12)

    def test_exact_teaching_input_is_refitted_and_returns_identity(self):
        from apps.vision.rack_positioning_algorithm import RigidBodyCompensationAlgorithm

        clouds = self._clouds()
        algorithm = RigidBodyCompensationAlgorithm(ransac_num_iterations=300)
        baseline = algorithm.build_current_template(*clouds)

        result = algorithm.production_mode_compute(
            baseline['local_template_cur'], *clouds, raise_on_invalid=False,
        )

        self.assertTrue(result['is_valid'])
        np.testing.assert_allclose(result['delta_T'], np.eye(4), atol=1e-12)
        for value in result['compensation'].values():
            self.assertAlmostEqual(value, 0.0, places=12)

    def test_orient_plane_flips_normal_and_offset_together(self):
        from apps.vision.algorithms.local_template_3d import LocalTemplate3D, PlaneResult

        plane = PlaneResult(
            normal=np.array([0.0, 0.0, -1.0]),
            offset=25.0,
            centroid=np.array([0.0, 0.0, 25.0]),
            inlier_ratio=1.0,
            point_count=100,
        )

        LocalTemplate3D._orient_plane(plane, np.array([0.0, 0.0, 1.0]))

        np.testing.assert_array_equal(plane.normal, np.array([0.0, 0.0, 1.0]))
        self.assertEqual(plane.offset, -25.0)

    def test_valid_current_frame_can_replace_an_invalid_legacy_standard(self):
        from apps.vision.rack_positioning_algorithm import RigidBodyCompensationAlgorithm

        clouds = self._clouds()
        algorithm = RigidBodyCompensationAlgorithm(ransac_num_iterations=300)
        baseline = algorithm.build_current_template(*clouds)
        invalid_standard = json.loads(json.dumps(baseline['local_template_cur']))
        invalid_standard.pop('fit_input_signature', None)
        invalid_standard.pop('fit_algorithm_version', None)
        invalid_standard['plane3']['normal'] = [1.0, 0.0, 0.0]

        result = algorithm.production_mode_compute(
            invalid_standard, *clouds, raise_on_invalid=False,
        )

        self.assertFalse(result['standard_validation']['is_valid'])
        self.assertTrue(result['current_validation']['is_valid'])
        self.assertTrue(result['is_valid'])
        self.assertFalse(result['quality_valid'])


class LayerSpacingLineMeasurementTests(SimpleTestCase):
    def test_endpoint_depth_clusters_return_robust_3d_distance(self):
        from apps.vision.rack_location import _measure_layer_spacing_line

        cloud = np.full((80, 100, 3), np.nan, dtype=np.float64)
        cloud[14:27, 14:27] = [10.0, 20.0, 1000.0]
        cloud[49:62, 64:77] = [40.0, 60.0, 1100.0]
        # A background point inside the first sample circle must be rejected by
        # the endpoint depth cluster instead of pulling the robust endpoint.
        cloud[16, 16] = [900.0, 900.0, 1500.0]

        spacing, detail = _measure_layer_spacing_line(cloud, {
            'x1': 20, 'y1': 20,
            'x2': 70, 'y2': 55,
            'sample_radius': 6,
            'depth_window_mm': 25,
        })

        self.assertAlmostEqual(spacing, np.sqrt(30 ** 2 + 40 ** 2 + 100 ** 2), places=6)
        self.assertEqual(detail['method'], 'endpoint_depth_cluster_3d_distance')
        self.assertGreater(detail['endpoints'][0]['sample_count'], 100)
        np.testing.assert_allclose(detail['endpoints'][0]['point_mm'], [10, 20, 1000])

    def test_endpoint_outside_pointcloud_is_rejected(self):
        from apps.vision.rack_location import _measure_layer_spacing_line

        cloud = np.ones((20, 30, 3), dtype=np.float64)
        with self.assertRaisesRegex(ValueError, '超出图像范围'):
            _measure_layer_spacing_line(cloud, {
                'x1': -1, 'y1': 5, 'x2': 10, 'y2': 10,
            })


class FoamPixelSegmentationTests(SimpleTestCase):
    def test_mask_excludes_overexposed_background_above_foam(self):
        roi = np.full((120, 100, 3), 255, dtype=np.uint8)
        roi[22:34, :] = (30, 110, 220)  # 车间横梁/有色背景
        roi[52:108, 10:90] = (225, 225, 225)  # 中性白色泡棉主体

        mask = generate_foam_mask(roi, {})

        self.assertLess(np.count_nonzero(mask[:45]) / mask[:45].size, 0.05)
        self.assertGreater(np.count_nonzero(mask[55:105, 12:88]) / mask[55:105, 12:88].size, 0.90)

    def test_camera_original_inside_media_is_reused_without_png_reencoding(self):
        from apps.vision.algorithms.foam_inspector import _save_or_reuse_original

        with TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=Path(tmpdir)):
            capture_dir = Path(tmpdir) / 'hik_captures'
            capture_dir.mkdir(parents=True)
            image_path = capture_dir / 'frame.bmp'
            image = np.full((40, 60, 3), 110, dtype=np.uint8)
            cv2.imwrite(str(image_path), image)

            relative_path, width, height = _save_or_reuse_original(
                image,
                'foam_raw_p0',
                str(image_path),
            )

            self.assertEqual(relative_path, 'hik_captures/frame.bmp')
            self.assertEqual((width, height), (60, 40))
            self.assertEqual(list(capture_dir.iterdir()), [image_path])

    def test_compute_mask_centroid_uses_actual_mask_pixels(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:80, 10:35] = 255
        mask[55:80, 10:90] = 255

        centroid = compute_mask_centroid(mask)

        self.assertIsNotNone(centroid)
        self.assertLess(centroid[0], 50.0)
        self.assertGreater(centroid[1], 45.0)

    def test_compute_iou_for_partial_overlap(self):
        mask1 = np.zeros((100, 100), dtype=np.uint8)
        mask1[25:75, 25:75] = 255
        mask2 = np.zeros((100, 100), dtype=np.uint8)
        mask2[50:100, 25:75] = 255

        self.assertAlmostEqual(compute_iou(mask1, mask2), 1 / 3, places=2)

    def test_coverage_is_capped_when_detection_exceeds_standard_area(self):
        detected = np.full((20, 20), 255, dtype=np.uint8)
        standard = np.zeros((20, 20), dtype=np.uint8)
        standard[5:15, 5:15] = 255

        self.assertEqual(compute_coverage_ratio(detected, standard), 1.0)

    def test_calibrated_foam_uses_standard_mask_metrics(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[:, :] = (20, 20, 20)
        image[30:70, 25:65] = 245
        image[30:70, 125:165] = 245
        standard = generate_foam_mask(image[10:90, 0:80], {})
        standard[:, :2] = 0
        standard[:, 78:] = 0
        standard[:2, :] = 0
        standard[78:, :] = 0

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.4, 0.9),
                        'right': (0.5, 0.1, 0.9, 0.9),
                    },
                },
                'coverage_threshold': 0.90,
                'iou_threshold': 0.70,
                'standard_masks': {'left': standard, 'right': standard},
                'max_offset_px': 2,
            },
            simulated_pass=False,
        )

        self.assertTrue(result['is_passed'])
        left = result['result_data']['sides']['left']
        self.assertGreater(left['detected_pixels'], 0)
        self.assertEqual(left['detected_pixels'], left['standard_pixels'])
        self.assertAlmostEqual(left['coverage_ratio'], 1.0, places=2)
        self.assertAlmostEqual(left['iou'], 1.0, places=2)
        self.assertEqual(left['offset_distance_px'], 0.0)

    def test_configured_standard_mask_must_exist(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[30:70, 25:65] = 245
        image[30:70, 125:165] = 245

        with self.assertRaises(StandardMaskConfigurationError):
            FoamInspector().inspect(
                image=image,
                inspection_config={
                    'foam_rois': {
                        '0': {
                            'left': (0.0, 0.1, 0.4, 0.9),
                            'right': (0.5, 0.1, 0.9, 0.9),
                        },
                    },
                    'standard_mask_paths': {'left': 'missing-standard-mask.png'},
                },
            )

    def test_mm_calibration_fails_alignment_when_axis_offset_exceeds_limit(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[30:70, 29:69] = 245
        image[30:70, 129:169] = 245
        standard = np.zeros((80, 80), dtype=np.uint8)
        standard[20:60, 25:65] = 255

        result = FoamInspector().inspect(
            image=image,
            inspection_config={
                'foam_rois': {
                    '0': {
                        'left': (0.0, 0.1, 0.4, 0.9),
                        'right': (0.5, 0.1, 0.9, 0.9),
                    },
                },
                'coverage_threshold': 0.8,
                'iou_threshold': 0.5,
                'standard_masks': {'left': standard, 'right': standard},
                'max_offset_px': 100,
                'max_offset_mm': 2,
                'mm_per_pixel_x': 1,
                'mm_per_pixel_y': 1,
            },
        )

        self.assertFalse(result['is_aligned'])
        self.assertEqual(result['sides']['left']['alignment_metric'], 'mm')
        self.assertGreater(result['sides']['left']['offset_distance_mm'], 2)


class FoamStandardMaskApiTests(TestCase):
    def test_standard_sample_upload_creates_mask_and_updates_recipe(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='标准模板测试',
            pos=0,
            camera_side='both',
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={'minCoverage': 0.5},
        )
        image = np.full((100, 200, 3), 20, dtype=np.uint8)
        image[30:70, 20:60] = 245
        ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(ok)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('vision:api_foam_standard_mask_upload'),
                data={
                    'recipe_id': recipe.id,
                    'side': 'left',
                    'image': SimpleUploadedFile(
                        'qualified-sample.png',
                        encoded.tobytes(),
                        content_type='image/png',
                    ),
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload['success'])
            mask_path = payload['mask']['path']
            self.assertTrue((Path(media_root) / mask_path).is_file())

        recipe.refresh_from_db()
        self.assertEqual(recipe.threshold_config['standardMaskPaths']['left'], mask_path)

    def test_teach_standard_template_builds_both_sides_from_one_image(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='左右同图示教',
            pos=0,
            is_active=False,
            camera_side='both',
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={'minCoverage': 0.5, 'requireStandardTemplate': True},
        )
        image = np.full((100, 200, 3), 20, dtype=np.uint8)
        image[30:70, 20:60] = 245
        image[30:70, 120:160] = 245
        ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(ok)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('vision:api_foam_standard_template_teach', args=[recipe.id]),
                data={
                    'image': SimpleUploadedFile(
                        'qualified-both.png', encoded.tobytes(), content_type='image/png'
                    ),
                },
            )

            self.assertEqual(response.status_code, 200, response.content)
            payload = response.json()
            self.assertTrue(payload['success'])
            self.assertTrue(payload['recipe']['standard_template_status']['ready'])
            for side in ('left', 'right'):
                path = payload['template']['sides'][side]['path']
                self.assertTrue((Path(media_root) / path).is_file())

            status_response = self.client.get(
                reverse('vision:api_foam_standard_mask_status', args=[recipe.id])
            )
            self.assertEqual(status_response.status_code, 200)
            self.assertTrue(status_response.json()['ready'])

        recipe.refresh_from_db()
        self.assertTrue(recipe.standard_template_version.startswith('v'))
        self.assertEqual(set(recipe.standard_template_config['sides']), {'left', 'right'})
        self.assertEqual(
            set(recipe.threshold_config['standardMaskPaths']), {'left', 'right'}
        )

    def test_detection_result_can_be_promoted_to_standard_template(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='检测结果转模板',
            pos=0,
            camera_side='both',
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={'minCoverage': 0.5, 'requireStandardTemplate': True},
        )
        image = np.full((100, 200, 3), 20, dtype=np.uint8)
        image[30:70, 20:60] = 225
        image[30:70, 120:160] = 225
        ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(ok)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            task = VisionTask.objects.create(task_type='FOAM_INSPECTION', status='SUCCESS')
            inspection = FoamInspectionResult.objects.create(
                vision_task=task,
                position_index=0,
                is_present=True,
                is_aligned=True,
                is_passed=True,
                result_data={
                    'recipe': {'id': recipe.id},
                    'sides': {
                        'left': {'is_present': True},
                        'right': {'is_present': True},
                    },
                },
            )
            VisionImage.objects.create(
                vision_task=task,
                image_type='ORIGINAL',
                file=SimpleUploadedFile(
                    'inspection-source.png', encoded.tobytes(), content_type='image/png'
                ),
            )

            response = self.client.post(
                reverse(
                    'vision:api_foam_standard_template_from_result',
                    args=[recipe.id, inspection.id],
                )
            )

            self.assertEqual(response.status_code, 200, response.content)
            payload = response.json()
            self.assertTrue(payload['success'])
            self.assertTrue(payload['recipe']['standard_template_status']['ready'])
            self.assertEqual(payload['template']['source']['result_id'], inspection.id)
            for side in ('left', 'right'):
                side_template = payload['template']['sides'][side]
                self.assertGreater(side_template['pixels'], 0)
                self.assertIn('centroid_x', side_template)
                self.assertIn('bounding_box', side_template)

        recipe.refresh_from_db()
        self.assertEqual(
            recipe.standard_template_config['source']['type'],
            'inspection_result',
        )

    def test_recipe_detection_requires_left_and_right_standard_templates(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='未示教模板',
            pos=0,
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={'requireStandardTemplate': True},
        )
        image = np.full((100, 200, 3), 20, dtype=np.uint8)
        image[30:70, 20:60] = 245
        image[30:70, 120:160] = 245

        with self.assertRaisesMessage(StandardMaskConfigurationError, '缺少左侧、右侧标准模板'):
            FoamInspector().inspect(
                image=image,
                inspection_config=build_foam_inspection_config(recipe),
                simulated_pass=False,
            )

    def test_legacy_mask_path_without_position_metadata_is_not_shown_as_taught(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='旧版单侧模板',
            pos=1,
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={
                'standardMaskPaths': {'left': 'standard_masks/legacy-left.png'},
            },
        )
        legacy_mask = np.full((80, 80), 255, dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', legacy_mask)
        self.assertTrue(ok)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            mask_path = Path(media_root) / 'standard_masks' / 'legacy-left.png'
            mask_path.parent.mkdir(parents=True)
            mask_path.write_bytes(encoded.tobytes())

            response = self.client.get(
                reverse('vision:api_foam_standard_mask_status', args=[recipe.id])
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(payload['ready'])
            self.assertFalse(payload['sides']['left']['exists'])
            self.assertTrue(payload['sides']['left']['file_exists'])
            self.assertFalse(payload['sides']['left']['metadata_complete'])
            self.assertIn('缺少面积、中心或边界框', payload['sides']['left']['error'])

    def test_roi_change_invalidates_taught_template(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='ROI变更失效',
            pos=0,
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            standard_template_config={
                'roi_config': {
                    'leftFoamROI': {'x': 1, 'y': 10, 'width': 80, 'height': 80},
                    'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
                },
                'image_width': 200,
                'image_height': 100,
                'sides': {
                    'left': {'path': 'standard_masks/left.png'},
                    'right': {'path': 'standard_masks/right.png'},
                },
            },
        )

        payload = serialize_recipe(recipe)

        self.assertFalse(payload['standard_template_status']['ready'])
        self.assertIn('ROI', payload['standard_template_status']['reason'])


class Rack3DSemanticMappingTests(SimpleTestCase):
    def test_normalize_locate_type_accepts_global_and_layer(self):
        from apps.vision.rack_location import normalize_locate_type

        self.assertEqual(normalize_locate_type('global'), 'GLOBAL')
        self.assertEqual(normalize_locate_type('LAYER'), 'LAYER')

    def test_normalize_locate_type_rejects_unknown_values(self):
        from apps.vision.rack_location import normalize_locate_type

        with self.assertRaisesMessage(ValueError, 'locate_type must be GLOBAL or LAYER'):
            normalize_locate_type('SIDE')

    def test_normalize_layer_index_enforces_global_zero_and_layers_one_to_three(self):
        from apps.vision.rack_location import normalize_layer_index

        self.assertEqual(normalize_layer_index(0, 'GLOBAL'), 0)
        self.assertEqual(normalize_layer_index('3', 'LAYER'), 3)

        with self.assertRaisesMessage(ValueError, 'GLOBAL locate_type requires layer_index=0'):
            normalize_layer_index(1, 'GLOBAL')
        with self.assertRaisesMessage(ValueError, 'LAYER locate_type requires layer_index 1, 2, or 3'):
            normalize_layer_index(0, 'LAYER')

    def test_locate_semantics_map_to_existing_roi_fields(self):
        from apps.vision.rack_location import locate_semantics

        self.assertEqual(
            locate_semantics(locate_type='GLOBAL', layer_index=0),
            {'locate_type': 'GLOBAL', 'layer_index': 0, 'roi_mode': 'global', 'layer_no': 0},
        )
        self.assertEqual(
            locate_semantics(locate_type='LAYER', layer_index=2),
            {'locate_type': 'LAYER', 'layer_index': 2, 'roi_mode': 'local', 'layer_no': 2},
        )


class Rack3DSerializationSemanticsTests(TestCase):
    def setUp(self):
        self.recipe = apps.get_model('vision', 'RackLocationRecipe').objects.create(
            recipe_name='SER-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            hand_eye_config={'matrix': 'identity'},
        )
        self.task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            status=ResultStatus.SUCCESS,
        )

    def test_recipe_serializer_exposes_locate_type_and_layer_index(self):
        from apps.vision.views import _serialize_3d_recipe

        payload = _serialize_3d_recipe(self.recipe)

        self.assertEqual(payload['locate_type'], 'GLOBAL')
        self.assertEqual(payload['layer_index'], 0)
        self.assertEqual(payload['total_layers'], 3)
        self.assertEqual(payload['photo_pose_name'], '')

    def test_result_payload_exposes_overall_layer_and_final_offsets(self):
        from apps.vision.rack_location import result_payload as rack_location_result_payload

        result = RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=2,
            offset_x=1,
            offset_y=2,
            offset_z=3,
            offset_rz=0.4,
            confidence=0.91,
            is_success=True,
            result_data={
                'locate_type': 'LAYER',
                'layer_index': 2,
                'overall_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 1.5},
                'layer_offset': {'x': 1, 'y': 2, 'z': 3, 'rz': 0.4},
                'final_offset': {'x': 11, 'y': 22, 'z': 33, 'rz': 1.9},
            },
        )

        payload = rack_location_result_payload(result)

        self.assertEqual(payload['locate_type'], 'LAYER')
        self.assertEqual(payload['layer_index'], 2)
        self.assertEqual(payload['overall_offset_x'], 10.0)
        self.assertEqual(payload['layer_offset_x'], 1.0)
        self.assertEqual(payload['final_offset_x'], 11.0)
        self.assertEqual(payload['rack_compensation']['meaning'], 'standard_rack_to_current_rack')
        self.assertEqual(len(payload['compensation_matrix']), 4)

    def test_result_payload_exposes_robot_translation_from_matrix(self):
        from apps.vision.rack_location import result_payload as rack_location_result_payload

        result = RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=1,
            is_success=True,
            result_data={
                'robot_rack_compensation': {
                    'matrix': [
                        [1.0, 0.0, 0.0, -19.541617],
                        [0.0, 1.0, 0.0, -11.105309],
                        [0.0, 0.0, 1.0, 61.350851],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                },
            },
        )

        payload = rack_location_result_payload(result)

        self.assertAlmostEqual(payload['robot_delta_x'], -19.541617, places=6)
        self.assertAlmostEqual(payload['robot_delta_y'], -11.105309, places=6)
        self.assertAlmostEqual(payload['robot_delta_z'], 61.350851, places=6)

    def test_result_payload_falls_back_when_legacy_spacing_is_null(self):
        from apps.vision.rack_location import result_payload as rack_location_result_payload

        result = RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=1,
            measured_layer_spacing=123.456,
            is_success=True,
            result_data={'measured_layer_spacing': None},
        )

        payload = rack_location_result_payload(result)

        self.assertAlmostEqual(payload['measured_layer_spacing'], 123.456, places=3)

    def test_results_api_returns_legacy_record_with_null_spacing(self):
        result = RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=1,
            measured_layer_spacing=0,
            is_success=True,
            result_data={'measured_layer_spacing': None},
        )

        response = self.client.get(reverse('vision:api_rack_location_results'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        payload = response.json()
        self.assertTrue(payload['success'])
        returned = next(item for item in payload['results'] if item['id'] == result.id)
        self.assertEqual(returned['measured_layer_spacing'], 0.0)

    def test_results_api_returns_json_for_invalid_filters(self):
        response = self.client.get(
            reverse('vision:api_rack_location_results'),
            {'position_no': 'not-a-number'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertFalse(response.json()['success'])


@override_settings(MEDIA_ROOT=mkdtemp())
class Rack3DCurrentRecipeAndRoiApiTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.global_recipe = Recipe.objects.create(
            recipe_name='CUR-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            hand_eye_config={'matrix': 'identity'},
        )
        self.layer_recipe = Recipe.objects.create(
            recipe_name='CUR-L2',
            rack_side='BOTH',
            position_no=1,
            layer_no=2,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=900,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_current_recipe_api_uses_locate_type_and_layer_index(self):
        response = self.client.get(
            reverse('vision:api_vision_3d_recipe_current'),
            {'locate_type': 'GLOBAL', 'layer_index': '0'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['recipe']['id'], self.global_recipe.id)
        self.assertEqual(payload['data']['recipe']['locate_type'], 'GLOBAL')
        self.assertEqual(payload['data']['recipe']['layer_index'], 0)

    def test_save_roi_requires_alignment_token(self):
        response = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.layer_recipe.id,
                'locate_type': 'LAYER',
                'layer_index': 2,
                'x_min': -10,
                'x_max': 10,
                'y_min': -10,
                'y_max': 10,
                'z_min': 700,
                'z_max': 950,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertIn('请先自动对齐', response.json()['error'])

    def test_save_roi_accepts_alignment_token_and_maps_layer_semantics(self):
        token = 'vision/rack_workbench/aligned.npy'
        path = Path(settings.MEDIA_ROOT) / token
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, np.zeros((2, 2, 3), dtype=np.float32))

        response = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.layer_recipe.id,
                'alignment_token': token,
                'locate_type': 'LAYER',
                'layer_index': 2,
                'roi_name': '第2层ROI',
                'x_min': -10,
                'x_max': 10,
                'y_min': -10,
                'y_max': 10,
                'z_min': 700,
                'z_max': 950,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        roi = ROI.objects.get(recipe=self.layer_recipe)
        self.assertEqual(roi.mode, ROI.MODE_LOCAL)
        self.assertEqual(roi.layer_no, 2)
        self.assertEqual(response.json()['data']['roi']['locate_type'], 'LAYER')


@override_settings(MEDIA_ROOT=mkdtemp(), VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class Rack3DFormalApiFlowTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='FLOW-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
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

    def test_camera_test_api_returns_online_boolean(self):
        response = self.client.post(reverse('vision:api_vision_3d_camera_test'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('online', payload['data'])

    def test_align_alias_accepts_capture_token(self):
        capture = self.client.post(
            reverse('vision:api_vision_3d_capture'),
            data=json.dumps({'recipe_id': self.recipe.id, 'locate_type': 'GLOBAL', 'layer_index': 0}),
            content_type='application/json',
        ).json()

        response = self.client.post(
            reverse('vision:api_vision_3d_align'),
            data=json.dumps({'pointcloud_token': capture['data']['pointcloud_token'], 'recipe_id': self.recipe.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['data']['aligned_pointcloud_token'])

    def test_results_latest_api_returns_latest_result(self):
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS)
        RackLocationResult.objects.create(
            vision_task=task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=0,
            confidence=0.9,
            is_success=True,
            result_data={'locate_type': 'GLOBAL', 'layer_index': 0},
        )

        response = self.client.get(reverse('vision:api_vision_3d_results_latest'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['result']['locate_type'], 'GLOBAL')


@override_settings(MEDIA_ROOT=mkdtemp(), VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class Rack3DGlobalLayerCompensationTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        self.global_recipe = Recipe.objects.create(
            recipe_name='COMP-GLOBAL',
            rack_side='LEFT',
            position_no=7,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=0,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )
        self.layer_recipe = Recipe.objects.create(
            recipe_name='COMP-LAYER-1',
            rack_side='LEFT',
            position_no=7,
            layer_no=1,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=0,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )
        ROI.objects.create(
            recipe=self.global_recipe,
            roi_name='global',
            mode='global',
            x_min=-1,
            x_max=1,
            y_min=-1,
            y_max=1,
            z_min=-1,
            z_max=1,
        )
        ROI.objects.create(
            recipe=self.layer_recipe,
            roi_name='layer-1',
            mode='local',
            layer_no=1,
            x_min=-1,
            x_max=1,
            y_min=-1,
            y_max=1,
            z_min=-1,
            z_max=1,
        )

    def _locate_with_offsets(self, recipe, layer_no, offsets):
        from apps.vision.rack_location import Rack3DLocator, RackLocationOutput

        locator = Rack3DLocator()
        output = RackLocationOutput(
            rack_side='LEFT',
            position_no=recipe.position_no,
            layer_no=layer_no,
            locate_ok=True,
            actual_x=100,
            actual_y=200,
            actual_z=300,
            offset_x=offsets['x'],
            offset_y=offsets['y'],
            offset_z=offsets['z'],
            offset_rz=offsets.get('rz', 0),
            confidence=0.95,
        )
        with (
            patch.object(locator, 'capture', return_value={'pointcloud_token': 'mock.npy'}),
            patch.object(locator, '_load_pointcloud', return_value=np.zeros((2, 2, 3))),
            patch.object(locator.processor, 'crop_by_roi_3d', return_value=np.ones((8, 3))),
            patch.object(locator, '_output_from_points', return_value=output),
        ):
            return locator.locate(
                rack_side='LEFT',
                layer_no=layer_no,
                recipe_id=recipe.id,
                write_plc=False,
            )

    def test_global_locate_records_overall_and_final_offsets(self):
        result = self._locate_with_offsets(
            self.global_recipe,
            0,
            {'x': 10, 'y': 20, 'z': 30, 'rz': 0.5},
        )

        self.assertEqual(result.result_data['locate_type'], 'GLOBAL')
        self.assertEqual(result.result_data['layer_index'], 0)
        self.assertEqual(result.result_data['overall_offset']['x'], 10)
        self.assertEqual(result.result_data['layer_offset']['x'], 0)
        self.assertEqual(result.result_data['final_offset']['x'], 10)
        self.assertEqual(float(result.offset_z), 30)

    def test_layer_locate_combines_latest_global_and_layer_offsets(self):
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS)
        RackLocationResult.objects.create(
            vision_task=task,
            recipe=self.global_recipe,
            side='LEFT',
            position_no=7,
            layer_no=0,
            offset_x=10,
            offset_y=20,
            offset_z=30,
            offset_rz=0.5,
            confidence=0.9,
            is_success=True,
            result_data={
                'locate_type': 'GLOBAL',
                'layer_index': 0,
                'overall_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 0.5},
                'final_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 0.5},
            },
        )

        result = self._locate_with_offsets(
            self.layer_recipe,
            1,
            {'x': 1, 'y': 2, 'z': 3, 'rz': 0.4},
        )

        self.assertEqual(result.result_data['locate_type'], 'LAYER')
        self.assertEqual(result.result_data['layer_index'], 1)
        self.assertEqual(result.result_data['overall_offset']['x'], 10)
        self.assertEqual(result.result_data['layer_offset']['z'], 3)
        self.assertEqual(result.result_data['final_offset'], {'x': 11.0, 'y': 22.0, 'z': 33.0, 'rz': 0.9})
        self.assertEqual(float(result.offset_x), 11)
        self.assertEqual(result.result_data['plc_payload']['offset_z'], 33.0)


class Rack3DPlcSafetyTests(TestCase):
    class RejectingAdapter:
        def __init__(self):
            self.called = False

        def send_rack_offsets(self, payload):
            self.called = True
            return {'success': True, 'echo': payload}

    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='PLC-SAFETY',
            rack_side='LEFT',
            position_no=3,
            layer_no=1,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
        )
        self.task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS)

    def _result(self, plc_payload):
        return RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='LEFT',
            position_no=3,
            layer_no=1,
            offset_x=1,
            offset_y=2,
            offset_z=3,
            confidence=0.9,
            is_success=True,
            result_data={'plc_payload': plc_payload},
        )

    def test_writer_rejects_invalid_compensation_without_calling_adapter(self):
        from apps.vision.rack_location import PlcVisionResultWriter

        adapter = self.RejectingAdapter()
        result = self._result({
            'compensation_valid': False,
            'offset_x': 1,
            'offset_y': 2,
            'offset_z': 3,
            'offset_rz': 0,
        })

        with patch('apps.vision.rack_location.AlarmService'):
            response = PlcVisionResultWriter(adapter=adapter).write(result)

        result.refresh_from_db()
        self.assertFalse(response['success'])
        self.assertTrue(response['rejected'])
        self.assertFalse(adapter.called)
        self.assertEqual(result.plc_write_status, 'REJECTED')

    def test_result_payload_normalizes_plc_payload_from_final_offset(self):
        from apps.vision.rack_location import result_payload

        result = self._result({
            'compensation_valid': True,
        })
        result.result_data.update({
            'locate_type': 'LAYER',
            'layer_index': 1,
            'overall_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 0},
            'layer_offset': {'x': 1, 'y': 2, 'z': 3, 'rz': 0},
            'final_offset': {'x': 11, 'y': 22, 'z': 33, 'rz': 0},
        })
        result.save(update_fields=['result_data'])

        payload = result_payload(result)

        self.assertEqual(payload['plc_payload']['locate_type'], 'LAYER')
        self.assertEqual(payload['plc_payload']['layer_index'], 1)
        self.assertEqual(payload['plc_payload']['offset_z'], 33.0)
        self.assertTrue(payload['plc_payload']['compensation_valid'])


class Rack3DWorkbenchStateSourceTests(SimpleTestCase):
    def test_javascript_contains_semantic_state_machine_controls(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')

        for marker in (
            'alignmentToken',
            'lastResultOk',
            'function currentLocateType()',
            'function currentLayerIndex()',
            'function refreshActionState()',
            'locate_type: currentLocateType()',
            'layer_index: currentLayerIndex()',
            'alignment_token: state.alignmentToken',
            'aligned_pointcloud_token',
            'CFG.currentRecipeUrl',
            'CFG.locateUrl',
            'CFG.results3dUrl',
        ):
            self.assertIn(marker, script)

    def test_each_pointcloud_is_consumed_after_one_calculation(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')

        self.assertIn('pointcloudConsumed: false', script)
        self.assertIn('if (!state.token || state.pointcloudConsumed)', script)
        self.assertIn('state.pointcloudConsumed = true', script)
        self.assertIn('再次计算将重新采集点云', script)

    def test_template_exposes_formal_3d_workbench_urls(self):
        template_path = Path(settings.BASE_DIR) / 'templates' / 'vision' / 'rack_locator_panel.html'
        template = template_path.read_text(encoding='utf-8')

        for marker in (
            'api_vision_3d_recipe_current',
            'api_vision_3d_locate',
            'api_vision_3d_results',
            'api_vision_3d_results_latest',
        ):
            self.assertIn(marker, template)

    def test_workbench_calculation_sends_three_regions_and_keeps_recipe_selected(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')
        template_path = Path(settings.BASE_DIR) / 'templates' / 'vision' / 'rack_locator_panel.html'
        template = template_path.read_text(encoding='utf-8')

        self.assertNotIn('function localTemplateRegions(targetRoi)', script)
        self.assertIn('function hasAllLocalTemplateRois()', script)
        self.assertIn('function cleanLocalTemplateRois()', script)
        self.assertIn("const measurementConfig = measurementConfigPatch('all')", script)
        self.assertIn('roi_config: measurementConfig', script)
        self.assertIn('btn-roi-plane1', template)
        self.assertIn('btn-roi-plane2', template)
        self.assertIn('btn-roi-plane3', template)
        self.assertIn('btn-layer-spacing-line', template)
        self.assertIn('id="measured-layer-spacing"', template)
        self.assertIn('function cleanLayerSpacingLine()', script)
        self.assertIn("return line ? { layer_spacing_line: line } : {}", script)
        self.assertIn('endpoint_depth_cluster_3d_distance', script)
        self.assertIn("canvas.style.inset = 'auto'", script)
        self.assertIn('(e.clientY - rect.top) * canvas.height / rect.height', script)
        self.assertIn('let roiSaveChain = Promise.resolve()', script)
        self.assertIn("autoSaveRoiToRecipe({ changedKey: key })", script)
        self.assertIn("autoSaveRoiToRecipe({ changedKey: 'layerSpacingLine' })", script)
        self.assertIn("autoSaveRoiToRecipe({ changedKey: 'ransacThreshold' })", script)
        self.assertIn('ransac_inlier_ratio_comparison', script)
        self.assertIn('id="roi-config-progress"', template)
        self.assertIn('id="ransac-distance-threshold"', template)
        self.assertIn('id="ransac-inlier-comparison"', template)
        self.assertIn('function renderLayerSpacing(result)', script)
        self.assertNotIn('selectNextRecipe();', script)

    def test_direct_detection_hides_quality_gate_warnings(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')
        template_path = Path(settings.BASE_DIR) / 'templates' / 'vision' / 'rack_locator_panel.html'
        template = template_path.read_text(encoding='utf-8')

        self.assertIn('const qualityGateEnabled = Boolean(', script)
        self.assertIn("status.textContent = '已计算 · 直检'", script)
        self.assertIn("validationMessage.style.display = 'none'", script)
        self.assertIn('qualityGateEnabled ? invalidRoiKeysFromValidation', script)
        self.assertIn('template-validation-message', template)
        self.assertIn('ransac-inlier-comparison', template)

class RackMeasurementConfigPersistenceTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='ROI-FIVE-ITEMS',
            rack_side='BOTH',
            position_no=1,
            layer_no=1,
            roi_config={
                'coordinate_system': 'robot',
                'camera_roi': {'x_min': -10, 'x_max': 10},
                'target_roi': {'x': 10, 'y': 20, 'w': 300, 'h': 200},
                'local_template_rois': {
                    'plane2': {'x': 30, 'y': 40, 'w': 50, 'h': 60},
                    'plane3': {'x': 70, 'y': 80, 'w': 90, 'h': 100},
                },
            },
        )

    def _patch_recipe(self, roi_config):
        return self.client.patch(
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({'id': self.recipe.id, 'roi_config': roi_config}),
            content_type='application/json',
        )

    def test_incremental_plane_and_line_patches_complete_five_item_config(self):
        plane1 = {'x': 110, 'y': 120, 'w': 130, 'h': 40}
        line = {
            'x1': 120, 'y1': 140, 'x2': 125, 'y2': 330,
            'sample_radius': 10, 'depth_window_mm': 25,
        }

        first = self._patch_recipe({'local_template_rois': {'plane1': plane1}})
        second = self._patch_recipe({'layer_spacing_line': line})
        third = self._patch_recipe({'ransac_distance_threshold_mm': 3.0})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 200)
        self.recipe.refresh_from_db()
        config = self.recipe.roi_config
        self.assertEqual(config['local_template_rois']['plane1'], plane1)
        self.assertIn('plane2', config['local_template_rois'])
        self.assertIn('plane3', config['local_template_rois'])
        self.assertEqual(config['layer_spacing_line'], line)
        self.assertEqual(config['ransac_distance_threshold_mm'], 3.0)
        self.assertIn('camera_roi', config)
        self.assertTrue(config['roi_teaching_updated_at'])

        detail = self.client.get(
            reverse('vision:api_rack_location_recipe_detail', args=[self.recipe.id]),
        )
        self.assertEqual(detail.status_code, 200)
        roi_info = detail.json()['recipe']['roi_info']
        self.assertEqual(roi_info['configured_count'], 5)
        self.assertTrue(roi_info['is_complete'])
        self.assertEqual(roi_info['layer_spacing_line'], line)

    def test_other_recipe_update_endpoint_preserves_taught_measurements(self):
        original = json.loads(json.dumps(self.recipe.roi_config))

        response = self.client.post(
            reverse('vision:api_rack_location_recipe_update', args=[self.recipe.id]),
            data=json.dumps({'roi_config': {'x_min': -500, 'x_max': 500}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config['target_roi'], original['target_roi'])
        self.assertEqual(
            self.recipe.roi_config['local_template_rois'],
            original['local_template_rois'],
        )
        self.assertEqual(self.recipe.roi_config['x_min'], -500)


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

        self.assertIn('clearPendingFile();', source)
        self.assertIn('setPreviewImage(data.image_url);', source)
        self.assertNotIn('clearPendingFile();   // 检测完成后清除暂存', source)

    def test_live_preview_frame_is_reused_for_detection(self):
        source = self._template_source()

        self.assertIn("let lastCameraCaptureToken = '';", source)
        self.assertIn("lastCameraCaptureToken = data.capture_token || '';", source)
        self.assertIn('await waitForCameraPreviewIdle();', source)
        self.assertIn('previewWasActive ? lastCameraCaptureToken', source)
        self.assertIn('preview_capture_token: previewCaptureToken,', source)

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

    def test_removed_score_fields_are_not_rendered(self):
        source = self._template_source()

        self.assertNotIn('id="left-score"', source)
        self.assertNotIn('id="right-score"', source)
        self.assertNotIn('id="d-score"', source)
        self.assertNotIn('`${prefix}-score`', source)

    def test_detection_errors_distinguish_request_and_render_failures(self):
        source = self._template_source()

        self.assertIn('async function requestDetection(url, options)', source)
        self.assertIn('function renderDetectionResultSafely(result)', source)
        self.assertIn("kind: 'network'", source)
        self.assertIn("kind: 'response'", source)
        self.assertIn("kind: 'detection'", source)
        self.assertIn('检测已完成，但结果显示失败', source)
        self.assertIn('Math.max(0, Math.min(1, Number(r.coverage_ratio) || 0))', source)
        self.assertIn('Math.max(0, Math.min(1, Number(data.coverage_ratio) || 0))', source)


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
    def test_camera_preview_uses_rack_camera_in_empty_rack_mode(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            image_path = Path(media_root) / 'rack-preview.png'
            cv2.imwrite(str(image_path), np.full((60, 100, 3), 128, dtype=np.uint8))
            with patch('apps.devices.adapters.camera.CameraAdapter.capture') as capture:
                capture.return_value = {
                    'image_path': str(image_path),
                    'timestamp': '2026-08-18T12:00:00',
                }
                response = self.client.post(
                    reverse('vision:api_camera_preview'),
                    data={'camera_code': 'CAM-INSPECT-RACK-01'},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['image_width'], 100)
        self.assertEqual(response.json()['image_height'], 60)
        capture.assert_called_once_with(
            camera_code='CAM-INSPECT-RACK-01',
            task_type='EMPTY_RACK_RECIPE_PREVIEW',
        )

    def test_empty_rack_recipe_api_saves_and_reloads_multiple_rois(self):
        image = np.full((120, 200, 3), 180, dtype=np.uint8)
        encoded_ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(encoded_ok)
        regions = [
            {'id': 'layer-1', 'name': '第1层', 'x': 10, 'y': 12, 'width': 80, 'height': 30, 'enabled': True},
            {'id': 'layer-2', 'name': '第2层', 'x': 20, 'y': 60, 'width': 120, 'height': 35, 'enabled': True},
        ]

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('vision:api_empty_rack_recipe_save'),
                data={
                    'name': 'A型料架空箱配方',
                    'teaching_image': SimpleUploadedFile('empty.png', encoded.tobytes(), content_type='image/png'),
                    'image_width': 1,
                    'image_height': 1,
                    'regions': json.dumps(regions),
                    'foam_brightness_threshold': '0.6',
                    'min_foam_area_ratio': '0.08',
                    'remark': '现场空料架基准',
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()['recipe']
            self.assertEqual(payload['recipe_type'], 'EMPTY_RACK_2D')
            self.assertEqual(payload['image_width'], 200)
            self.assertEqual(payload['image_height'], 120)
            self.assertEqual(payload['roi_config']['regions'], regions)
            self.assertTrue(payload['teaching_image_url'])

            get_response = self.client.get(reverse('vision:api_empty_rack_recipe'))
            self.assertEqual(get_response.status_code, 200)
            loaded = get_response.json()['recipe']
            self.assertEqual(loaded['name'], 'A型料架空箱配方')
            self.assertEqual(len(loaded['roi_config']['regions']), 2)
            self.assertEqual(loaded['threshold_config']['foam_brightness_threshold'], 0.6)

    def test_empty_rack_recipe_api_rejects_roi_outside_image(self):
        image = np.zeros((50, 100, 3), dtype=np.uint8)
        encoded_ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(encoded_ok)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('vision:api_empty_rack_recipe_save'),
                data={
                    'teaching_image': SimpleUploadedFile('empty.png', encoded.tobytes(), content_type='image/png'),
                    'regions': json.dumps([
                        {'name': '越界区域', 'x': 90, 'y': 10, 'width': 20, 'height': 20},
                    ]),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('超出示教图边界', response.json()['error'])

    def test_empty_rack_inspection_detects_empty_and_occupied_regions(self):
        reference = np.full((100, 120, 3), 40, dtype=np.uint8)
        occupied = reference.copy()
        occupied[20:60, 20:70] = 230
        ok_reference, encoded_reference = cv2.imencode('.png', reference)
        ok_occupied, encoded_occupied = cv2.imencode('.png', occupied)
        self.assertTrue(ok_reference and ok_occupied)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            reference_path = default_storage.save(
                'vision/empty_rack_recipes/test-reference.png',
                ContentFile(encoded_reference.tobytes()),
            )
            recipe = VisionRecipe.objects.create(
                recipe_type='EMPTY_RACK_2D', name='运行空箱配方', is_active=True,
                image_width=120, image_height=100,
                roi_config={'regions': [
                    {'id': 'layer-1', 'name': '第1层', 'x': 10, 'y': 10, 'width': 70, 'height': 60},
                ]},
                threshold_config={'difference_threshold': 0.1, 'min_changed_area_ratio': 0.05},
                algorithm_config={'reference_image_path': reference_path},
            )
            empty_response = self.client.post(
                reverse('vision:api_empty_rack_inspect'),
                data={'recipe_id': recipe.id, 'image': SimpleUploadedFile(
                    'empty.png', encoded_reference.tobytes(), content_type='image/png'
                )},
            )
            occupied_response = self.client.post(
                reverse('vision:api_empty_rack_inspect'),
                data={'recipe_id': recipe.id, 'image': SimpleUploadedFile(
                    'occupied.png', encoded_occupied.tobytes(), content_type='image/png'
                )},
            )
            reference_response = self.client.post(
                reverse('vision:api_empty_rack_inspect'),
                data={'recipe_id': recipe.id, 'use_teaching_image': '1'},
            )
            inline_response = self.client.post(
                reverse('vision:api_empty_rack_inspect'),
                data={
                    'image': SimpleUploadedFile(
                        'inline-reference.png', encoded_reference.tobytes(),
                        content_type='image/png',
                    ),
                    'regions': json.dumps([
                        {'id': 'live-roi', 'name': '当前ROI', 'x': 5, 'y': 5,
                         'width': 50, 'height': 40},
                    ]),
                    'foam_brightness_threshold': '0.6',
                    'min_foam_area_ratio': '0.08',
                },
            )

        self.assertEqual(empty_response.status_code, 200, empty_response.content)
        self.assertTrue(empty_response.json()['result']['is_empty'])
        self.assertEqual(occupied_response.status_code, 200, occupied_response.content)
        self.assertEqual(reference_response.status_code, 200, reference_response.content)
        self.assertTrue(reference_response.json()['result']['is_empty'])
        self.assertEqual(inline_response.status_code, 200, inline_response.content)
        self.assertTrue(inline_response.json()['result']['is_empty'])
        self.assertEqual(inline_response.json()['result']['regions'][0]['name'], '当前ROI')
        occupied_result = occupied_response.json()['result']
        self.assertFalse(occupied_result['is_empty'])
        self.assertEqual(occupied_result['occupied_count'], 1)
        self.assertGreater(occupied_result['regions'][0]['foam_area_ratio'], 0.05)

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

    def test_recipe_edit_preserves_standard_template_and_internal_threshold_fields(self):
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='保留模板数据',
            pos=0,
            image_width=200,
            image_height=100,
            roi_config={
                'leftFoamROI': {'x': 0, 'y': 10, 'width': 80, 'height': 80},
                'rightFoamROI': {'x': 100, 'y': 10, 'width': 80, 'height': 80},
            },
            threshold_config={
                'minCoverage': 0.7,
                'mmPerPixelX': 0.1,
                'standardMaskPaths': {
                    'left': 'standard_masks/left.png',
                    'right': 'standard_masks/right.png',
                },
                'requireStandardTemplate': True,
            },
            standard_template_config={
                'version': 'v-position-data',
                'sides': {
                    'left': {'pixels': 100, 'centroid_x': 20, 'centroid_y': 30},
                    'right': {'pixels': 120, 'centroid_x': 25, 'centroid_y': 35},
                },
            },
            standard_template_version='v-position-data',
        )
        original_template = recipe.standard_template_config

        response = self.client.post(
            reverse('vision:api_foam_recipe_save'),
            data={
                'id': recipe.id,
                'name': recipe.name,
                'pos': recipe.pos,
                'image_width': recipe.image_width,
                'image_height': recipe.image_height,
                'roi_config': recipe.roi_config,
                'threshold_config': {'minCoverage': 0.8},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        recipe.refresh_from_db()
        self.assertEqual(recipe.standard_template_config, original_template)
        self.assertEqual(recipe.standard_template_version, 'v-position-data')
        self.assertEqual(recipe.threshold_config['minCoverage'], 0.8)
        self.assertEqual(recipe.threshold_config['mmPerPixelX'], 0.1)
        self.assertEqual(
            set(recipe.threshold_config['standardMaskPaths']),
            {'left', 'right'},
        )

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

    def test_capture_inspect_api_accepts_a_signed_recent_preview_frame(self):
        task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )
        foam_result = FoamInspectionResult.objects.create(
            vision_task=task,
            position_index=0,
            is_present=True,
            is_aligned=True,
            has_lifted_edge=False,
            score=0.95,
            is_passed=True,
        )

        with TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / 'preview.bmp'
            cv2.imwrite(str(image_path), np.full((40, 60, 3), 110, dtype=np.uint8))
            camera_settings = {
                **settings.AUTOMATIC_ORDER,
                'HIK_CAMERA': {
                    **settings.AUTOMATIC_ORDER.get('HIK_CAMERA', {}),
                    'OUTPUT_DIR': Path(tmpdir),
                },
            }
            token = signing.dumps(
                {'image_path': str(image_path.resolve())},
                salt='foam-camera-preview',
                compress=True,
            )
            with override_settings(AUTOMATIC_ORDER=camera_settings), patch(
                'apps.vision.views.VisionService'
            ) as service_cls:
                service_cls.return_value.inspect_foam.return_value = foam_result
                response = self.client.post(
                    reverse('vision:api_foam_capture_inspect'),
                    data={'position_index': 0, 'preview_capture_token': token},
                    content_type='application/json',
                )

        self.assertEqual(response.status_code, 200)
        kwargs = service_cls.return_value.inspect_foam.call_args.kwargs
        self.assertEqual(kwargs['captured_image_path'], str(image_path.resolve()))

    def test_upload_inspect_rejects_recipe_without_standard_template(self):
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

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('标准模板', payload['error'])


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

    def test_inspect_foam_reuses_a_supplied_preview_frame_without_recapturing(self):
        class UnexpectedCameraAdapter:
            def capture(self, camera_code, task_type):
                raise AssertionError('camera should not capture again')

        with TemporaryDirectory() as tmpdir:
            image_path = str(Path(tmpdir) / 'preview-frame.bmp')
            cv2.imwrite(image_path, np.full((120, 160, 3), 110, dtype=np.uint8))
            service = VisionService(camera_adapter=UnexpectedCameraAdapter())

            result = service.inspect_foam(
                self.product,
                self.rack,
                position_index=2,
                use_camera=True,
                captured_image_path=image_path,
            )

        self.assertEqual(result.result_data.get('camera_image_path'), image_path)
        self.assertEqual(result.result_data['timings_ms']['camera_request'], 0.0)
        self.assertEqual(result.result_data['timings_ms']['preview_frame_reused'], 1)
        self.assertIn('algorithm_and_archive', result.result_data['timings_ms'])
        self.assertIn('total', result.result_data['timings_ms'])

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

    def test_calibrated_foam_inspection_fails_when_foam_is_offset(self):
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

        self.assertFalse(result['is_passed'])
        self.assertEqual(result['defect_type'], FoamDefectType.MISALIGNED)
        self.assertTrue(result['result_data']['sides']['right']['is_present'])
        self.assertFalse(result['result_data']['sides']['right']['is_aligned'])

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

    def create_task_with_related_records(self, *, created_at, position_index):
        task = VisionTask.objects.create(
            task_type=VisionTaskType.FOAM_INSPECTION,
            status=ResultStatus.SUCCESS,
        )
        VisionTask.objects.filter(pk=task.pk).update(created_at=created_at)
        FoamInspectionResult.objects.create(
            vision_task=task,
            position_index=position_index,
            is_present=True,
            is_aligned=True,
            has_lifted_edge=False,
            score=0.96,
            is_passed=True,
        )
        VisionImage.objects.create(
            vision_task=task,
            image_type=VisionImageType.RESULT,
            file=f'vision/result-{position_index}.jpg',
            width=100,
            height=80,
        )
        return task

    def test_clean_vision_records_dry_run_reports_cleanup_without_deleting_records(self):
        base_time = timezone.now()
        self.create_task_with_related_records(
            created_at=base_time - timezone.timedelta(minutes=2),
            position_index=1,
        )
        self.create_task_with_related_records(
            created_at=base_time,
            position_index=2,
        )

        output = StringIO()
        call_command('clean_vision_records', '--dry-run', '--keep=1', stdout=output)

        self.assertEqual(VisionTask.objects.count(), 2)
        self.assertEqual(FoamInspectionResult.objects.count(), 2)
        self.assertEqual(VisionImage.objects.count(), 2)
        self.assertIn('VisionTask', output.getvalue())

    def test_clean_vision_records_deletes_old_tasks_and_cascaded_records(self):
        base_time = timezone.now()
        old_task = self.create_task_with_related_records(
            created_at=base_time - timezone.timedelta(minutes=2),
            position_index=1,
        )
        latest_task = self.create_task_with_related_records(
            created_at=base_time,
            position_index=2,
        )

        call_command('clean_vision_records', '--keep=1', stdout=StringIO())

        self.assertFalse(VisionTask.objects.filter(pk=old_task.pk).exists())
        self.assertTrue(VisionTask.objects.filter(pk=latest_task.pk).exists())
        self.assertEqual(FoamInspectionResult.objects.count(), 1)
        self.assertEqual(VisionImage.objects.count(), 1)

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
    def test_empty_rack_editor_supports_resize_move_and_dynamic_progress(self):
        source = (
            Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'empty_rack_recipe_editor.js'
        ).read_text(encoding='utf-8')

        self.assertIn('function handleAt(point, roi)', source)
        self.assertIn("type: 'resize'", source)
        self.assertIn("type: 'move'", source)
        self.assertIn('data-roi-field="width"', source)
        self.assertIn('function updateProgress()', source)

    def test_recipe_teaching_can_select_existing_recipes_and_trial_empty_rack(self):
        template = (
            Path(settings.BASE_DIR) / 'templates' / 'vision' / 'foam_inspector_interactive.html'
        ).read_text(encoding='utf-8')
        empty_script = (
            Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'empty_rack_recipe_editor.js'
        ).read_text(encoding='utf-8')

        self.assertIn('id="foam-recipe-select"', template)
        self.assertIn('id="empty-rack-recipe-select"', template)
        self.assertIn('id="empty-rack-calculate-btn"', template)
        self.assertIn('id="empty-rack-save-btn"', template)
        self.assertNotIn('id="empty-rack-trial-upload-btn"', template)
        self.assertNotIn('id="empty-rack-trial-record-btn"', template)
        self.assertIn('function selectFoamRecipeForEdit(recipeId)', template)
        self.assertIn('function renderFoamRecipeSelect()', template)
        self.assertIn('function renderRecipeSelect()', empty_script)
        self.assertIn('async function applyRecipe(recipe)', empty_script)
        self.assertIn('async function runTrial(', empty_script)
        self.assertIn("form.append('recipe_id', state.recipe.id)", empty_script)
        self.assertIn("form.append('use_teaching_image', '1')", empty_script)
        self.assertIn('await runTrial()', empty_script)
        self.assertNotIn("saveRecipe('draft'", empty_script)
        self.assertIn("saveRecipe('publish')", empty_script)
        self.assertIn('state.trialCompleted = false', empty_script)

    def test_shared_2d_workbench_exposes_run_and_recipe_authoring_modes(self):
        run_response = self.client.get(reverse('vision:foam_inspector_interactive'))
        empty_run_response = self.client.get(
            reverse('vision:foam_inspector_interactive'), {'inspection': 'empty_rack'}
        )
        foam_response = self.client.get(
            reverse('vision:foam_inspector_interactive'),
            {'mode': 'foam_recipe', 'new': '1'},
        )

        self.assertContains(run_response, '运行检测')
        self.assertContains(run_response, '＋ 新建泡棉配方')
        self.assertContains(run_response, '＋ 新建空箱配方')
        self.assertContains(empty_run_response, '空箱运行检测')
        self.assertContains(empty_run_response, '开始空箱检测')
        self.assertContains(empty_run_response, 'api/empty-rack/inspect')
        self.assertContains(foam_response, '配方示教')
        self.assertContains(foam_response, '新建泡棉检测配方')
        self.assertContains(foam_response, 'foam-recipe-guide')
        self.assertContains(foam_response, '保存草稿')
        self.assertContains(foam_response, '验证并发布')

    def test_new_foam_draft_does_not_replace_published_recipe_until_publish(self):
        published = VisionRecipe.objects.create(
            recipe_type='FOAM_2D', name='生产配方', pos=0, is_active=True,
            roi_config={
                'leftFoamROI': {'x': 10, 'y': 10, 'width': 20, 'height': 20},
                'rightFoamROI': {'x': 50, 'y': 10, 'width': 20, 'height': 20},
            },
        )
        payload = {
            'create_new': True,
            'save_mode': 'draft',
            'pos': 0,
            'name': '换型草稿',
            'roi_config': {
                'leftFoamROI': {'x': 15, 'y': 12, 'width': 22, 'height': 22},
                'rightFoamROI': {'x': 55, 'y': 12, 'width': 22, 'height': 22},
            },
            'threshold_config': {'coverage_threshold': 0.7},
        }

        draft_response = self.client.post(
            reverse('vision:api_foam_recipe_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(draft_response.status_code, 200)
        draft = VisionRecipe.objects.get(pk=draft_response.json()['recipe']['id'])
        published.refresh_from_db()
        self.assertFalse(draft.is_active)
        self.assertTrue(published.is_active)

        payload.update({'id': draft.id, 'create_new': False, 'save_mode': 'publish'})
        publish_response = self.client.post(
            reverse('vision:api_foam_recipe_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(publish_response.status_code, 200)
        draft.refresh_from_db()
        published.refresh_from_db()
        self.assertTrue(draft.is_active)
        self.assertFalse(published.is_active)

    def test_new_empty_rack_draft_does_not_replace_published_recipe_until_publish(self):
        published = VisionRecipe.objects.create(
            recipe_type='EMPTY_RACK_2D', name='生产空箱配方', pos=0,
            image_width=100, image_height=100, is_active=True,
            roi_config={'regions': [{'id': 'old', 'x': 5, 'y': 5, 'width': 20, 'height': 20}]},
            algorithm_config={'reference_image_path': 'vision/empty_rack_recipes/old.jpg'},
        )
        image = np.full((100, 100, 3), 30, dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', image)
        self.assertTrue(ok)
        regions = json.dumps([
            {'id': 'layer-1', 'name': '第1层', 'x': 10, 'y': 10, 'width': 40, 'height': 30},
        ])

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            draft_response = self.client.post(
                reverse('vision:api_empty_rack_recipe_save'),
                data={
                    'create_new': '1', 'save_mode': 'draft', 'name': '换型空箱草稿',
                    'regions': regions, 'foam_brightness_threshold': '0.55',
                    'min_foam_area_ratio': '0.03',
                    'teaching_source': json.dumps({
                        'type': 'foam_inspection_record', 'record_id': '88',
                        'captured_at': '2026-08-19 10:20:30', 'position_index': 2,
                    }),
                    'teaching_image': SimpleUploadedFile(
                        'empty-rack.png', encoded.tobytes(), content_type='image/png'
                    ),
                },
            )
            self.assertEqual(draft_response.status_code, 200, draft_response.content)
            draft = VisionRecipe.objects.get(pk=draft_response.json()['recipe']['id'])
            published.refresh_from_db()
            self.assertFalse(draft.is_active)
            self.assertTrue(published.is_active)
            self.assertEqual(
                draft.algorithm_config['teaching_source']['record_id'], '88'
            )

            publish_response = self.client.post(
                reverse('vision:api_empty_rack_recipe_save'),
                data={
                    'id': draft.id, 'save_mode': 'publish', 'name': draft.name,
                    'regions': regions, 'foam_brightness_threshold': '0.55',
                    'min_foam_area_ratio': '0.03',
                },
            )
            self.assertEqual(publish_response.status_code, 200, publish_response.content)

        draft.refresh_from_db()
        published.refresh_from_db()
        self.assertTrue(draft.is_active)
        self.assertFalse(published.is_active)

    def test_recipe_page_does_not_expose_empty_rack_summary(self):
        response = self.client.get(reverse('vision:recipe_management'))

        self.assertNotContains(response, '空箱检测配方（2D）')
        self.assertNotContains(response, 'empty-rack-recipe-summary')
        self.assertNotContains(response, '进入 2D 空箱工作台')
        self.assertNotContains(response, 'empty-rack-canvas')

    def test_shared_2d_workbench_exposes_empty_rack_mode(self):
        response = self.client.get(
            reverse('vision:foam_inspector_interactive'),
            {'mode': 'empty_rack'},
        )

        self.assertContains(response, '2D 视觉工作台')
        self.assertContains(response, 'SHARED 2D VISION WORKBENCH')
        self.assertContains(response, '空箱检查配方')
        self.assertContains(response, 'empty-rack-canvas')
        self.assertContains(response, 'empty-rack-progress')
        self.assertContains(response, 'empty-rack-recipe-select')
        self.assertContains(response, '配方计算与保存')
        self.assertContains(response, '开始计算')
        self.assertContains(response, '保存配方')
        self.assertContains(response, 'api/empty-rack/inspect')
        self.assertContains(response, 'empty_rack_recipe_editor.js')
        self.assertContains(response, '料架相机拍照')
        self.assertContains(response, '从泡棉记录导入')
        self.assertContains(response, 'importRecordImage')
        self.assertContains(response, '开始计算')
        self.assertContains(response, '保存配方')
        self.assertContains(response, 'CAM-INSPECT-RACK-01')

    def test_legacy_rack_recipe_page_redirects_to_unified_3d_tab(self):
        response = self.client.get(reverse('vision:rack_location_recipes'))

        self.assertRedirects(
            response,
            reverse('vision:recipe_management') + '?tab=rack3d',
            fetch_redirect_response=False,
        )

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
        self.assertContains(response, 'btn-teach-standard')
        self.assertContains(response, 'ROI 是固定搜索范围，模板是合格泡棉')
        self.assertContains(response, '首次检测无模板时')
        self.assertContains(response, 'ensureStandardTemplateForDetection')
        self.assertContains(response, 'foam-max-offset-x-mm')
        self.assertContains(response, 'standard-template/teach')
        self.assertContains(response, 'btn-save-result-standard')
        self.assertContains(response, '保存本次结果为标准模板')
        self.assertContains(response, 'standard-template/from-result')

    def test_2d_recipe_page_displays_and_preserves_template_position_data(self):
        response = self.client.get(reverse('vision:recipe_management'))

        self.assertContains(response, '泡棉标准模板位置（只读同步）')
        self.assertContains(response, '标准模板位置已保存到配方')
        self.assertContains(response, 'foamTemplateSummaryHtml')
        self.assertContains(response, 'centroid_x')
        self.assertContains(response, 'bounding_box')
        self.assertContains(response, 'editedRoiOrOriginal')
        self.assertContains(response, '...(recipe.threshold_config || {})')

    def test_recipe_page_omits_2d_recipe_navigation(self):
        response = self.client.get(reverse('vision:recipe_management'))

        self.assertNotContains(response, 'LEVEL 1 · 料架规格')
        self.assertNotContains(response, 'LEVEL 2 · 产品分类')
        self.assertNotContains(response, 'LEVEL 3 · 位置配方')
        self.assertNotContains(response, 'A 产品 · 每层 5 个')
        self.assertNotContains(response, '3 × 5 = 15')


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
        Config = apps.get_model('dm_camera', 'DMCameraConfig')

        recipe = self._recipe()
        active_config = Config.objects.create(
            name='Rack Locator SDK',
            device_sn='SDK-SN-001',
            frame_rate=12,
            exposure_time=1500,
            is_active=True,
        )

        class FakeDMCameraService:
            calls = []

            def __init__(self):
                self.is_connected = False
                self.is_streaming = False

            def connect(self, device_sn=None, config_id=None):
                self.calls.append(('connect', device_sn, config_id))
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

        self.assertEqual(FakeDMCameraService.calls, [
            ('connect', 'SDK-SN-001', active_config.id),
            ('POINTCLOUD', False),
        ])
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

    def test_provider_propagates_dm_camera_configuration_error(self):
        from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError
        from apps.vision.rack_location import DMCameraRackFrameProvider

        class MisconfiguredDMCameraService:
            is_connected = False
            is_streaming = False

            def connect(self, device_sn=None, config_id=None):
                raise DMCameraConfigurationError('tofconfig JSON error')

        with patch('apps.dm_camera.services.DMCameraService', MisconfiguredDMCameraService):
            with self.assertRaisesRegex(DMCameraConfigurationError, 'tofconfig JSON error'):
                DMCameraRackFrameProvider().capture(self._recipe('Bad-Config'), 1, 1)

    def test_provider_still_falls_back_for_non_configuration_error(self):
        from apps.vision.rack_location import DMCameraRackFrameProvider

        class OfflineDMCameraService:
            is_connected = False
            is_streaming = False

            def connect(self, device_sn=None, config_id=None):
                raise RuntimeError('camera offline')

        with patch('apps.dm_camera.services.DMCameraService', OfflineDMCameraService):
            payload = DMCameraRackFrameProvider().capture(self._recipe('Offline'), 1, 1)

        self.assertEqual(payload['source'], 'sample_fallback')
        self.assertEqual(payload['fallback_reason'], 'camera offline')


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
            rack_type='RACK-03',
            rack_side='BOTH',
            position_no=3,
            layer_no=1,
            layer_count=3,
            standard_x=100,
            standard_y=200,
            standard_z=300,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_rack_locator_panel_exposes_3d_roi_workbench_controls(self):
        response = self.client.get(reverse('vision:rack_locator_panel'))

        self.assertContains(response, '3D 料架定位工作台')
        self.assertContains(response, 'API-POS-03-L1｜3 层料架配方｜料架号：RACK-03')
        self.assertContains(response, 'selected-recipe-info')
        self.assertContains(response, '管理 3D 配方')
        self.assertNotContains(response, 'POS3 · L1 - API-POS-03-L1')
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
        self.assertContains(response, '标准料架建模')
        self.assertContains(response, 'model-left-upright')
        self.assertContains(response, 'model-top-crossbeam')
        self.assertContains(response, 'model-right-upright')
        self.assertContains(response, 'model-front-plane')
        self.assertContains(response, 'model-step-frame')
        self.assertContains(response, '建立标准料架模型')
        self.assertNotContains(response, 'btn-sdk-debug')
        self.assertNotContains(response, 'sdk-debug-drawer')
        self.assertNotContains(response, 'sdk-frame-rate')
        self.assertNotContains(response, 'sdk-exposure-time')
        self.assertNotContains(response, 'sdk-trigger-mode')
        self.assertNotContains(response, 'sdk-confidence-threshold')
        self.assertNotContains(response, 'btn-sdk-save-config')
        self.assertNotContains(response, 'btn-sdk-save-test')
        self.assertNotContains(response, 'btn-sdk-test-capture')
        self.assertNotContains(response, 'btn-sdk-open-demo')
        self.assertNotContains(response, 'sdk-console-strip')
        self.assertNotContains(response, 'sdk-drawer-shell')
        self.assertNotContains(response, 'sdk-device-panel')
        self.assertNotContains(response, 'sdk-params-panel')
        self.assertNotContains(response, 'sdk-test-panel')
        self.assertNotContains(response, 'sdk-preview-panel')
        self.assertNotContains(response, 'sdk-status-camera')
        self.assertNotContains(response, 'sdk-status-config')
        self.assertNotContains(response, 'sdk-status-source')
        self.assertNotContains(response, 'btn-sdk-recover')
        self.assertNotContains(response, 'sdk-action-primary')
        self.assertNotContains(response, 'apiSdkFindDevicesUrl')
        self.assertNotContains(response, 'sdkConfigUrl')
        self.assertNotContains(response, 'apiSdkDiagnosticsUrl')
        self.assertNotContains(response, 'apiSdkRecoverUrl')
        self.assertContains(response, 'api_vision_3d_capture')
        self.assertContains(response, 'api_vision_3d_test_locate')
        self.assertNotContains(response, 'btn-sdk-connect')
        self.assertNotContains(response, 'btn-sdk-start-stream')
        self.assertNotContains(response, 'apiSdkConnectUrl')
        self.assertNotContains(response, 'apiSdkCaptureUrl')

    def test_workbench_javascript_preserves_unified_api_success_flag(self):
        script_path = Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js'
        script = script_path.read_text(encoding='utf-8')

        self.assertIn('success: data.success', script)
        self.assertIn("error: data.error || ''", script)
        for sdk_marker in (
            'sdkConfigId',
            'loadSdkConfig',
            'saveSdkConfig',
            'refreshSdkDiagnostics',
            'runSdkCaptureTest',
            'btn-sdk-',
            'apiSdk',
            'sdkConfigUrl',
        ):
            self.assertNotIn(sdk_marker, script)

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
                'organized_pointcloud': build_sample_pointcloud(
                    side='LEFT', layer_count=3, local_template_geometry=True,
                ),
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
            hand_eye_config={'matrix': 'identity', 'skip_validation': True},  # 添加skip_validation以跳过手眼标定验证
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

    def test_capture_projects_recipe_3d_roi_to_pixel_bounds(self):
        bounds = {
            'x_min': -100, 'x_max': 100,
            'y_min': -80, 'y_max': 80,
            'z_min': 800, 'z_max': 1000,
        }
        self.recipe.roi_config = {
            'coordinate_system': 'robot',
            **bounds,
            'target_roi': bounds,
            'camera_roi': bounds,
        }
        self.recipe.save(update_fields=['roi_config'])

        payload = self._service().capture_workbench(recipe_id=self.recipe.id)

        self.assertEqual(payload['recipe_pixel_roi']['projection_source'], 'camera_roi')
        self.assertEqual(
            {key: payload['recipe_pixel_roi'][key] for key in ('x', 'y', 'w', 'h')},
            {'x': 244, 'y': 179, 'w': 152, 'h': 122},
        )

    def test_robot_recipe_roi_uses_coordinate_snapshot_for_projection(self):
        bounds = {
            'x_min': -100, 'x_max': 100,
            'y_min': -80, 'y_max': 80,
            'z_min': 800, 'z_max': 1000,
        }
        self.recipe.roi_config = {
            'coordinate_system': 'robot',
            **bounds,
            'target_roi': bounds,
            'transform_snapshot': np.eye(4).tolist(),
        }
        cloud = self.CloudFrameProvider().capture(self.recipe, 1, 1)['organized_pointcloud']

        pixel_roi = self._service().project_recipe_roi_to_pixels(cloud, self.recipe)

        self.assertEqual(pixel_roi['projection_source'], 'robot_roi')
        self.assertEqual(
            {key: pixel_roi[key] for key in ('x', 'y', 'w', 'h')},
            {'x': 244, 'y': 179, 'w': 152, 'h': 122},
        )

    @patch('apps.vision.rack_location._load_docs_pic_pointcloud', return_value=None)
    def test_capture_workbench_falls_back_to_sample_when_camera_unavailable(self, _offline_cloud):
        from apps.vision.rack_location import RackLocationService

        class BrokenProvider:
            def capture(self, recipe, position_no, layer_no):
                raise RuntimeError('camera offline')

        payload = RackLocationService(frame_provider=BrokenProvider()).capture_workbench(
            recipe_id=self.recipe.id
        )
        self.assertEqual(payload['source'], 'sample')
        self.assertTrue((Path(settings.MEDIA_ROOT) / payload['pointcloud_token']).exists())

    def test_capture_workbench_propagates_dm_camera_configuration_error(self):
        from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError
        from apps.vision.rack_location import RackLocationService

        class MisconfiguredProvider:
            def capture(self, recipe, position_no, layer_no):
                raise DMCameraConfigurationError('tofconfig missing')

        with self.assertRaisesRegex(DMCameraConfigurationError, 'tofconfig missing'):
            RackLocationService(frame_provider=MisconfiguredProvider()).capture_workbench(
                recipe_id=self.recipe.id
            )

    def test_calculate_workbench_crops_persisted_cloud_without_db_write(self):
        """测试禁用保存记录时不写入数据库"""
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config={'target_roi': self.roi},
            recipe_id=self.recipe.id,
            save_record=False,  # 明确指定不保存
        )
        self.assertTrue(result['locate_ok'])
        self.assertLess(abs(result['offset_x']), 20)
        self.assertTrue(result['result_image_url'].endswith('.png') or 'rack_workbench' in result['result_image_url'])
        self.assertEqual(RackLocationResult.objects.count(), 0)
    
    def test_calculate_workbench_saves_record_when_requested(self):
        """测试仅明确请求时保存到数据库"""
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config={'target_roi': self.roi},
            recipe_id=self.recipe.id,
            save_record=True,
        )
        
        # 如果定位失败，打印错误信息帮助调试
        if not result.get('locate_ok'):
            print(f"定位失败: {result.get('error_code')} - {result.get('error_message')}")
        
        self.assertTrue(result['locate_ok'])
        self.assertLess(abs(result['offset_x']), 20)
        # 验证已保存到数据库
        self.assertEqual(RackLocationResult.objects.count(), 1)
        self.assertEqual(VisionTask.objects.count(), 1)
        
        # 验证保存的记录内容
        saved_result = RackLocationResult.objects.first()
        self.assertEqual(saved_result.recipe, self.recipe)
        self.assertEqual(saved_result.layer_no, 1)
        self.assertEqual(saved_result.position_no, 1)
        self.assertTrue(saved_result.is_success)
        
        saved_task = VisionTask.objects.first()
        self.assertEqual(saved_task.task_type, VisionTaskType.RACK_LOCATING)
        self.assertEqual(saved_task.status, ResultStatus.SUCCESS)

    def test_calculate_workbench_fits_all_three_local_template_regions(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        full_roi = {'x': 0, 'y': 0, 'w': 640, 'h': 480, 'feature_type': 'rack_reference'}
        local_rois = {
            'plane1': {'x': 190, 'y': 105, 'w': 250, 'h': 45},
            'plane2': {'x': 135, 'y': 105, 'w': 45, 'h': 270},
            'plane3': {'x': 190, 'y': 330, 'w': 250, 'h': 45},
        }

        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config={
                'target_roi': full_roi,
                'local_template_rois': local_rois,
                'ransac_distance_threshold_mm': 3.0,
            },
            recipe_id=self.recipe.id,
            save_record=True,
        )

        self.assertEqual(result['rack_compensation']['source'], 'local_template_current_baseline')
        self.assertEqual(result['compensation_coordinate_system'], 'camera')
        self.assertEqual(result['rack_compensation']['coordinate_system'], 'camera')
        self.assertFalse(result['rack_compensation']['robot_conversion_applied'])
        self.assertEqual(result['camera_rack_compensation'], result['rack_compensation'])
        self.assertEqual(result['transform_context']['context_source'], 'record_snapshot')
        self.assertEqual(
            result['transform_context']['T_flange_camera']['matrix'],
            np.eye(4, dtype=float).tolist(),
        )
        self.assertFalse(result['local_template_std_available'])
        self.assertEqual(set(result['local_template_rois']), {'plane1', 'plane2', 'plane3'})
        self.assertTrue(result['local_template_validation']['is_valid'])
        self.assertEqual(result['ransac_distance_threshold_mm'], 3.0)
        self.assertEqual(result['result_data']['ransac_distance_threshold_mm'], 3.0)
        comparison = result['ransac_inlier_ratio_comparison']
        self.assertEqual(set(comparison), {'plane1', 'plane2', 'plane3'})
        for plane in comparison.values():
            self.assertEqual(set(plane), {'2', '3', '5'})
            self.assertLessEqual(plane['2'], plane['3'])
            self.assertLessEqual(plane['3'], plane['5'])
        self.assertAlmostEqual(result['measured_layer_spacing'], 190.0, places=1)
        self.assertAlmostEqual(
            result['result_data']['measured_layer_spacing'], 190.0, places=1,
        )
        for key in ('offset_x', 'offset_y', 'offset_z', 'offset_rx', 'offset_ry', 'offset_rz'):
            self.assertEqual(result[key], 0.0)
        self.assertIsNotNone(result['result_id'])
        self.assertEqual(VisionImage.objects.count(), 2)
        self.assertEqual(
            set(VisionImage.objects.values_list('image_type', flat=True)),
            {VisionImageType.DEPTH, VisionImageType.RESULT},
        )
        current = result['local_template_cur']
        for key in ('plane1', 'plane2', 'plane3'):
            self.assertGreater(current[key]['point_count'], 50)
            self.assertGreater(current[key]['inlier_ratio'], 0.99)
        saved = RackLocationResult.objects.get(pk=result['result_id'])
        self.assertAlmostEqual(float(saved.measured_layer_spacing), 190.0, places=1)
        from apps.vision.rack_location import result_payload
        self.assertAlmostEqual(
            result_payload(saved)['measured_layer_spacing'], 190.0, places=1,
        )

    def test_direct_detection_disables_quality_gate_and_reports_layer_spacing(self):
        from apps.vision.algorithms.rack_structure_validator import (
            ValidationErrorCode,
            ValidationResult,
        )

        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        local_rois = {
            'plane1': {'x': 190, 'y': 105, 'w': 250, 'h': 45},
            'plane2': {'x': 135, 'y': 105, 'w': 45, 'h': 270},
            'plane3': {'x': 190, 'y': 330, 'w': 250, 'h': 45},
        }
        invalid = ValidationResult(
            is_valid=False,
            error_code=ValidationErrorCode.QUALITY_LOW,
            message='测试结构NG',
            checks=[],
        )

        # Force invalid diagnostics and prove direct-detection mode neither
        # raises a warning nor suppresses the measured result.
        with patch(
            'apps.vision.algorithms.rack_structure_validator.RackStructureValidator.validate',
            return_value=invalid,
        ):
            result = service.calculate_workbench(
                token=captured['pointcloud_token'],
                roi_config={
                    'target_roi': {'x': 0, 'y': 0, 'w': 640, 'h': 480},
                    'local_template_rois': local_rois,
                },
                recipe_id=self.recipe.id,
                save_record=False,
            )

        self.assertFalse(result['local_template_validation']['is_valid'])
        self.assertAlmostEqual(result['measured_layer_spacing'], 190.0, places=1)
        self.assertAlmostEqual(
            result['result_data']['measured_layer_spacing'], 190.0, places=1,
        )
        self.assertFalse(result['quality_warning'])
        self.assertFalse(result['quality_gate_enabled'])
        self.assertEqual(result['quality_gate_mode'], 'disabled')
        self.assertFalse(result['result_data']['quality_gate_enabled'])
        self.assertEqual(
            result['result_data']['layer_spacing_method'],
            'camera_z_centroid_delta',
        )
        self.assertAlmostEqual(
            result['result_data']['diagnostic_layer_spacing'], 190.0, places=1,
        )

    def test_measurement_line_owns_layer_spacing_result(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        roi_config = {
            'target_roi': {'x': 0, 'y': 0, 'w': 640, 'h': 480},
            'local_template_rois': {
                'plane1': {'x': 190, 'y': 105, 'w': 250, 'h': 45},
                'plane2': {'x': 135, 'y': 105, 'w': 45, 'h': 270},
                'plane3': {'x': 190, 'y': 330, 'w': 250, 'h': 45},
            },
            'layer_spacing_line': {
                'x1': 300, 'y1': 142,
                'x2': 300, 'y2': 336,
                'sample_radius': 6,
                'depth_window_mm': 25,
            },
        }

        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config=roi_config,
            recipe_id=self.recipe.id,
            save_record=False,
        )

        self.assertEqual(result['layer_spacing_method'], 'endpoint_depth_cluster_3d_distance')
        self.assertEqual(result['result_data']['layer_spacing_line'], roi_config['layer_spacing_line'])
        self.assertAlmostEqual(result['result_data']['diagnostic_layer_spacing'], 190.0, places=1)
        self.assertGreater(result['measured_layer_spacing'], 285.0)
        self.assertLess(result['measured_layer_spacing'], 310.0)
        self.assertEqual(len(result['layer_spacing_measurement']['endpoints']), 2)

    def test_calibrate_standard_persists_valid_local_template_result(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        local_rois = {
            'plane1': {'x': 190, 'y': 105, 'w': 250, 'h': 45},
            'plane2': {'x': 135, 'y': 105, 'w': 45, 'h': 270},
            'plane3': {'x': 190, 'y': 330, 'w': 250, 'h': 45},
        }
        result = service.calculate_workbench(
            token=captured['pointcloud_token'],
            roi_config={
                'target_roi': {'x': 0, 'y': 0, 'w': 640, 'h': 480},
                'local_template_rois': local_rois,
            },
            recipe_id=self.recipe.id,
            save_record=True,
        )

        response = self.client.post(
            reverse('vision:api_rack_location_calibrate_standard', args=[self.recipe.id]),
            data=json.dumps({'result_id': result['result_id']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['standard_template']['template_type'], 'local_template_3d')
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.local_template_std['source_result_id'], result['result_id'])
        self.assertEqual(self.recipe.local_template_std['algorithm_version'], 'v2_rigid_body')
        self.assertEqual(self.recipe.local_template_std['coordinate_system'], 'camera')
        for key in ('plane1', 'plane2', 'plane3'):
            self.assertGreater(self.recipe.local_template_std[key]['inlier_ratio'], 0.99)

    def test_calculate_workbench_uses_saved_three_plane_template_for_6dof(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        roi_config = {
            'target_roi': {'x': 0, 'y': 0, 'w': 640, 'h': 480, 'feature_type': 'rack_reference'},
            'local_template_rois': {
                'plane1': {'x': 190, 'y': 105, 'w': 250, 'h': 45},
                'plane2': {'x': 135, 'y': 105, 'w': 45, 'h': 270},
                'plane3': {'x': 190, 'y': 330, 'w': 250, 'h': 45},
            },
        }
        baseline = service.calculate_workbench(
            token=captured['pointcloud_token'], roi_config=roi_config,
            recipe_id=self.recipe.id, save_record=False,
        )
        self.recipe.local_template_std = baseline['local_template_cur']
        self.recipe.save(update_fields=['local_template_std'])

        result = service.calculate_workbench(
            token=captured['pointcloud_token'], roi_config=roi_config,
            recipe_id=self.recipe.id, save_record=False,
        )

        self.assertTrue(result['local_template_std_available'])
        self.assertEqual(result['rack_compensation']['source'], 'local_template_3d')
        self.assertEqual(result['rack_compensation']['coordinate_system'], 'camera')
        self.assertEqual(
            result['rack_compensation']['placement_formula'],
            'P_current_camera = T_camera_standard_to_current * P_standard_camera',
        )
        self.assertTrue(result['locate_ok'])
        for key in ('offset_x', 'offset_y', 'offset_z', 'offset_rx', 'offset_ry', 'offset_rz'):
            self.assertAlmostEqual(result[key], 0.0, places=4)

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
        roi_3d = {
            'x_min': -100, 'x_max': 100,
            'y_min': -80, 'y_max': 80,
            'z_min': 300, 'z_max': 900,
        }
        result = service.save_workbench_result(
            token=captured['pointcloud_token'],
            roi_config={'target_roi': self.roi},
            roi_3d=roi_3d,
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
        self.assertEqual(result.roi_data['target_roi'], self.roi)
        self.assertEqual(result.roi_data['roi_3d'], roi_3d)
        self.assertEqual(result.vision_task.images.filter(image_type=VisionImageType.DEPTH).count(), 1)
        self.assertEqual(result.vision_task.images.filter(image_type=VisionImageType.RESULT).count(), 1)

    def test_save_workbench_result_accepts_3d_roi_without_pixel_roi(self):
        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)
        roi_3d = {
            'x_min': -500, 'x_max': 500,
            'y_min': -300, 'y_max': 300,
            'z_min': 1, 'z_max': 1500,
        }
        result = service.save_workbench_result(
            token=captured['pointcloud_token'],
            roi_config={},
            roi_3d=roi_3d,
            recipe_id=self.recipe.id,
            layer_no=1,
        )
        self.assertEqual(result.roi_data['target_roi'], {})
        self.assertEqual(result.roi_data['roi_3d'], roi_3d)
        self.assertEqual(result.vision_task.images.count(), 2)

    def test_workbench_api_calculate_automatically_saves_record(self):
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
                    'roi_3d': {
                        'x_min': -500, 'x_max': 500,
                        'y_min': -300, 'y_max': 300,
                        'z_min': 1, 'z_max': 1500,
                    },
                    'recipe_id': self.recipe.id,
                    'save_record': True,
                }),
                content_type='application/json',
            ).json()
            self.assertTrue(calc['success'])
            self.assertIn('result_image_url', calc['result'])
            self.assertIsNotNone(calc['result']['result_id'])
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

    def test_formal_capture_returns_projected_recipe_pixel_roi(self):
        bounds = {
            'x_min': -100, 'x_max': 100,
            'y_min': -80, 'y_max': 80,
            'z_min': 800, 'z_max': 1000,
        }
        self.recipe.roi_config = {'camera_roi': bounds, **bounds}
        self.recipe.save(update_fields=['roi_config'])

        payload = self._locator().capture(recipe_id=self.recipe.id)

        self.assertEqual(payload['recipe_pixel_roi']['projection_source'], 'camera_roi')
        self.assertEqual(
            {key: payload['recipe_pixel_roi'][key] for key in ('x', 'y', 'w', 'h')},
            {'x': 244, 'y': 179, 'w': 152, 'h': 122},
        )

    def test_capture_propagates_dm_camera_configuration_error(self):
        from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError
        from apps.vision.rack_location import Rack3DLocator

        class MisconfiguredProvider:
            def capture(self, recipe, position_no, layer_no):
                raise DMCameraConfigurationError('tofconfig invalid')

        locator = Rack3DLocator(frame_provider=MisconfiguredProvider())
        with self.assertRaisesRegex(DMCameraConfigurationError, 'tofconfig invalid'):
            locator.capture(recipe_id=self.recipe.id)

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

    def test_vision_3d_sdk_config_url_is_not_exposed(self):
        with self.assertRaises(NoReverseMatch):
            reverse('vision:api_vision_3d_sdk_config')

    @override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=False)
    def test_vision_3d_capture_reports_configuration_error_without_sample_data(self):
        from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError
        from apps.vision.rack_location import DMCameraRackFrameProvider

        with patch.object(
            DMCameraRackFrameProvider,
            'capture',
            side_effect=DMCameraConfigurationError('tofconfig invalid JSON'),
        ):
            response = self.client.post(
                reverse('vision:api_vision_3d_capture'),
                data=json.dumps({'recipe_id': self.recipe.id}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('tofconfig invalid JSON', payload['error'])
        self.assertNotIn('sample', json.dumps(payload).lower())
        self.assertNotIn('pointcloud_token', json.dumps(payload))

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

    def test_vision_3d_recipe_can_be_copied_with_technical_data(self):
        self.recipe.rack_type = 'SOURCE-RACK'
        self.recipe.roi_config = {'target_roi': {'x': 10, 'y': 20, 'w': 30, 'h': 40}}
        self.recipe.local_template_std = {'origin': [1, 2, 3], 'plane1': {'offset': 4}}
        self.recipe.save(update_fields=['rack_type', 'roi_config', 'local_template_std'])

        response = self.client.post(
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({
                'source_recipe_id': self.recipe.id,
                'recipe_name': 'API-3D-COPY',
                'rack_type': 'COPY-RACK',
                'layer_count': 2,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        copied = apps.get_model('vision', 'RackLocationRecipe').objects.get(
            pk=response.json()['data']['recipe']['id'],
        )
        self.assertNotEqual(copied.id, self.recipe.id)
        self.assertEqual(copied.recipe_name, 'API-3D-COPY')
        self.assertEqual(copied.rack_type, 'COPY-RACK')
        self.assertEqual(copied.layer_count, 2)
        self.assertEqual(copied.roi_config, self.recipe.roi_config)
        self.assertEqual(copied.local_template_std, self.recipe.local_template_std)
        self.assertEqual(copied.standard_z, self.recipe.standard_z)

    def test_vision_3d_recipe_list_tolerates_legacy_unsupported_layer(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        legacy = Recipe.objects.create(
            recipe_name='LEGACY-L5',
            rack_side='BOTH',
            position_no=1,
            layer_no=5,
            layer_count=5,
            standard_x=0,
            standard_y=0,
            standard_z=0,
        )

        response = self.client.get(reverse('vision:api_vision_3d_recipes'))

        self.assertEqual(response.status_code, 200)
        recipes = response.json()['data']['recipes']
        payload = next(item for item in recipes if item['id'] == legacy.id)
        self.assertEqual(payload['layer_index'], 5)
        self.assertIn('requires layer_index 1, 2, or 3', payload['semantic_validation_error'])

    def test_vision_3d_recipe_create_rejects_unsupported_layer_without_saving(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        count_before = Recipe.objects.count()

        response = self.client.post(
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({'recipe_name': 'INVALID-L5', 'layer_no': 5}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertEqual(Recipe.objects.count(), count_before)

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
