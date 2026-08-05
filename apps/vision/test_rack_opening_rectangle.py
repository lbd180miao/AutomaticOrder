import json

import numpy as np
from django.test import TestCase
from django.urls import reverse

from apps.core.constants import RackSide, VisionTaskType
from apps.vision.algorithms.rack_opening_rectangle import (
    RackOpeningRectangleLocator,
    RectangleLocationError,
    calculate_tcp_verification,
    normalize_reference_feature_config,
)
from apps.vision.models import RackLocationRecipe, RackLocationResult, VisionTask
from apps.vision.rack_location import Rack3DLocator


STANDARD_POINTS = np.asarray([
    [900.0, 500.0, 1200.0],
    [1500.0, 500.0, 1200.0],
    [1500.0, 500.0, 800.0],
    [900.0, 500.0, 800.0],
])


def v2_config(**threshold_overrides):
    thresholds = {
        'min_valid_points': 100,
        'min_plane_inliers': 100,
        'min_edge_points': 20,
        'width_tolerance_mm': 10.0,
        'height_tolerance_mm': 10.0,
        'require_pixel_edge_evidence': False,
        **threshold_overrides,
    }
    return {
        'algorithm_version': 'RECTANGLE_CORNERS_V2',
        'opening_rectangle': {
            'coordinate_system': 'robot_base',
            'standard_points': {
                f'p{index}': {'x': point[0], 'y': point[1], 'z': point[2]}
                for index, point in enumerate(STANDARD_POINTS, start=1)
            },
            'thresholds': thresholds,
        },
    }


def rectangle_edge_cloud(*, seed=7, noise_mm=0.2):
    rng = np.random.default_rng(seed)
    points = []
    for start, end in (
        (STANDARD_POINTS[0], STANDARD_POINTS[1]),
        (STANDARD_POINTS[1], STANDARD_POINTS[2]),
        (STANDARD_POINTS[2], STANDARD_POINTS[3]),
        (STANDARD_POINTS[3], STANDARD_POINTS[0]),
    ):
        for amount in np.linspace(0.0, 1.0, 160):
            points.append(start * (1.0 - amount) + end * amount + rng.normal(0, noise_mm, 3))
    points = np.asarray(points)
    angle = np.deg2rad(1.2)
    rotation = np.asarray([
        [np.cos(angle), -np.sin(angle), 0.0],
        [np.sin(angle), np.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ])
    translation = np.asarray([4.0, -2.0, 3.0])
    transformed = (rotation @ points.T).T + translation
    expected = (rotation @ STANDARD_POINTS.T).T + translation
    return transformed, expected


class RackOpeningRectangleAlgorithmTests(TestCase):
    def test_normalization_recomputes_center_width_and_axes(self):
        normalized = normalize_reference_feature_config(v2_config())
        opening = normalized['opening_rectangle']
        self.assertEqual(opening['standard_center'], {'x': 1200.0, 'y': 500.0, 'z': 1000.0})
        self.assertEqual(opening['standard_width_mm'], 600.0)
        self.assertEqual(opening['standard_height_mm'], 400.0)
        self.assertEqual(opening['point_order'][0], 'P1_TOP_LEFT')

    def test_recovers_four_corners_and_derives_p5(self):
        cloud, expected = rectangle_edge_cloud()
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(),
            coordinate_system='robot_base',
            confidence_threshold=0.7,
        )
        actual = np.asarray([
            [result['points'][f'p{index}'][axis] for axis in ('x', 'y', 'z')]
            for index in range(1, 5)
        ])
        center = np.asarray([result['center'][axis] for axis in ('x', 'y', 'z')])
        self.assertTrue(result['locate_ok'])
        self.assertLess(float(np.max(np.linalg.norm(actual - expected, axis=1))), 2.0)
        np.testing.assert_allclose(center, actual.mean(axis=0), atol=1e-4)
        self.assertGreater(result['quality']['confidence'], 0.7)

    def test_auto_mode_extracts_five_points_without_standard_geometry(self):
        height, width = 240, 320
        pixel_y, pixel_x = np.indices((height, width))
        depth = np.full((height, width), 1500.0)
        frame = (
            (pixel_y < 45) | (pixel_y > 195)
            | (pixel_x < 50) | (pixel_x > 270)
        )
        depth[frame] = 1000.0
        focal_length = 300.0
        camera_cloud = np.stack((
            (pixel_x - width / 2.0) / focal_length * depth,
            (pixel_y - height / 2.0) / focal_length * depth,
            depth,
        ), axis=2).reshape(-1, 3)
        pixels = np.column_stack((pixel_x.reshape(-1), pixel_y.reshape(-1)))

        result = RackOpeningRectangleLocator().locate_auto(
            camera_cloud,
            {},
            camera_points=camera_cloud,
            depth_values=camera_cloud[:, 2],
            coordinate_system='camera',
            pixel_coordinates=pixels,
            confidence_threshold=0.5,
        )

        self.assertTrue(result['locate_ok'])
        self.assertEqual(result['algorithm_version'], 'RECTANGLE_CORNERS_AUTO_V2')
        self.assertEqual(result['reference_mode'], 'roi_auto_only')
        self.assertFalse(result['standard_geometry_configured'])
        self.assertEqual(len(result['points']), 4)
        center = np.asarray([result['center'][axis] for axis in ('x', 'y', 'z')])
        corners = np.asarray([
            [result['points'][f'p{index}'][axis] for axis in ('x', 'y', 'z')]
            for index in range(1, 5)
        ])
        np.testing.assert_allclose(center, corners.mean(axis=0), atol=1e-4)
        self.assertAlmostEqual(result['pixel_points']['p1']['x'], 49.0, delta=3.0)
        self.assertAlmostEqual(result['pixel_points']['p3']['y'], 195.0, delta=3.0)

    def test_reference_plane_rejects_larger_background_plane(self):
        cloud, expected = rectangle_edge_cloud()
        actual_normal = np.cross(expected[1] - expected[0], expected[0] - expected[3])
        actual_normal /= np.linalg.norm(actual_normal)
        background = cloud[:500] + actual_normal * 150.0
        result = RackOpeningRectangleLocator().locate(
            np.vstack((cloud, background)),
            v2_config(),
            coordinate_system='robot_base',
        )
        center = np.asarray([result['center'][axis] for axis in ('x', 'y', 'z')])
        self.assertTrue(result['locate_ok'])
        np.testing.assert_allclose(center, expected.mean(axis=0), atol=1.0)

    def test_pixel_topology_uses_internal_opening_not_roi_boundary(self):
        pixel_y, pixel_x = np.indices((120, 160))
        inside_opening = (
            (pixel_x > 20) & (pixel_x < 140)
            & (pixel_y > 20) & (pixel_y < 100)
        )
        cloud = np.stack((
            800.0 + pixel_x * 5.0,
            np.where(inside_opening, 550.0, 500.0),
            1300.0 - pixel_y * 5.0,
        ), axis=2).reshape(-1, 3)
        pixels = np.column_stack((pixel_x.reshape(-1), pixel_y.reshape(-1)))
        config = v2_config(
            require_pixel_edge_evidence=True,
            edge_rmse_mm=6.0,
            rigid_fit_max_residual_mm=8.0,
        )
        result = RackOpeningRectangleLocator().locate(
            cloud,
            config,
            coordinate_system='robot_base',
            pixel_coordinates=pixels,
        )
        self.assertTrue(result['locate_ok'])
        self.assertEqual(result['quality']['edge_evidence_source'], 'internal_front_plane_contour')
        self.assertAlmostEqual(result['geometry']['width_mm'], 600.0, delta=12.0)
        self.assertAlmostEqual(result['geometry']['height_mm'], 400.0, delta=12.0)

    def test_pixel_topology_rejects_filled_roi_boundary(self):
        pixel_y, pixel_x = np.indices((80, 120))
        cloud = np.stack((
            900.0 + pixel_x * 5.0,
            np.full_like(pixel_x, 500.0, dtype=float),
            1200.0 - pixel_y * 5.0,
        ), axis=2).reshape(-1, 3)
        pixels = np.column_stack((pixel_x.reshape(-1), pixel_y.reshape(-1)))
        with self.assertRaises(RectangleLocationError) as captured:
            RackOpeningRectangleLocator().locate(
                cloud,
                v2_config(require_pixel_edge_evidence=True),
                coordinate_system='robot_base',
                pixel_coordinates=pixels,
            )
        self.assertIn('ROI', captured.exception.message)

    def test_tcp_verification_derives_q5_and_reports_error(self):
        cloud, _ = rectangle_edge_cloud()
        opening = RackOpeningRectangleLocator().locate(cloud, v2_config())
        measured = {
            f'q{index}': {
                axis: opening['points'][f'p{index}'][axis] + 0.5
                for axis in ('x', 'y', 'z')
            }
            for index in range(1, 5)
        }
        verification = calculate_tcp_verification(
            opening,
            measured,
            coordinate_system='robot_base',
            tolerance_mm=1.0,
        )
        self.assertTrue(verification['passed'])
        self.assertAlmostEqual(verification['center_error']['distance_mm'], np.sqrt(0.75), places=3)


class RackOpeningRectangleIntegrationTests(TestCase):
    def setUp(self):
        self.config = normalize_reference_feature_config(v2_config())
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='RECTANGLE-V2-L1',
            rack_side=RackSide.BOTH,
            position_no=1,
            layer_no=1,
            layer_count=3,
            standard_x=1200,
            standard_y=500,
            standard_z=1000,
            reference_feature_config=self.config,
            hand_eye_config={'matrix': 'identity', 'skip_validation': True},
            confidence_threshold=0.7,
            max_offset_x=50,
            max_offset_y=50,
            max_offset_z=50,
            max_offset_rz=5,
            enabled=True,
        )

    def test_locator_returns_v2_payload_without_median_fallback(self):
        cloud, expected = rectangle_edge_cloud()
        output = Rack3DLocator()._output_from_points(
            points=cloud,
            recipe=self.recipe,
            rack_side=RackSide.LEFT,
            layer_no=1,
            roi_source='test',
        )
        payload = output.to_payload()
        self.assertTrue(output.locate_ok)
        self.assertEqual(payload['algorithm_version'], 'RECTANGLE_CORNERS_V2')
        self.assertEqual(len(payload['opening_rectangle']['points']), 4)
        self.assertAlmostEqual(output.actual_x, float(expected.mean(axis=0)[0]), delta=1.0)
        self.assertEqual(payload['rack_compensation']['meaning'], 'standard_rack_to_current_rack')
        self.assertEqual(payload['rack_compensation']['source'], 'opening_rectangle_deviation')
        self.assertEqual(payload['plc_payload']['robot_taught_place_pose_count'], 15)
        np.testing.assert_allclose(
            np.asarray(payload['compensation_matrix']),
            np.asarray(payload['opening_rectangle']['deviation_transform']['matrix']),
            atol=1e-8,
        )

    def test_standard_template_calibration_persists_current_zero_pose(self):
        cloud, expected = rectangle_edge_cloud()
        opening = RackOpeningRectangleLocator().locate(cloud, self.config)
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING)
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=self.recipe,
            side=RackSide.BOTH,
            position_no=1,
            layer_no=1,
            actual_x=opening['center']['x'],
            actual_y=opening['center']['y'],
            actual_z=opening['center']['z'],
            confidence=opening['quality']['confidence'],
            is_success=True,
            result_data={
                'algorithm_version': 'RECTANGLE_CORNERS_V2',
                'opening_rectangle': opening,
            },
        )

        response = self.client.post(
            reverse('vision:api_rack_location_calibrate_standard', args=[self.recipe.id]),
            data=json.dumps({'result_id': result.id, 'note': 'zero pose'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()['standard_template']
        self.assertEqual(payload['robot_taught_place_pose_count'], 15)
        model = payload['standard_rack_model']
        self.assertEqual(model['model_version'], 'THREE_MEMBER_RIGID_V1')
        self.assertEqual(
            set(model['members']),
            {'left_upright', 'top_crossbeam', 'right_upright'},
        )
        self.assertIn('front_plane', model)
        self.assertIn('rack_coordinate_system', model)
        self.assertIn('pointcloud_template', model)
        self.assertEqual(model['pointcloud_template']['source_result_id'], result.id)
        self.recipe.refresh_from_db()
        self.assertEqual(
            self.recipe.reference_feature_config['standard_template']['source_result_id'],
            result.id,
        )
        self.assertEqual(
            self.recipe.reference_feature_config['standard_template']['template_type'],
            'three_member_rack_model',
        )
        self.assertAlmostEqual(float(self.recipe.standard_x), float(expected.mean(axis=0)[0]), delta=1.0)

    def test_tcp_verification_api_persists_audit_data(self):
        cloud, _ = rectangle_edge_cloud()
        opening = RackOpeningRectangleLocator().locate(cloud, self.config)
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING)
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=self.recipe,
            side=RackSide.LEFT,
            position_no=1,
            layer_no=1,
            actual_x=opening['center']['x'],
            actual_y=opening['center']['y'],
            actual_z=opening['center']['z'],
            confidence=opening['quality']['confidence'],
            is_success=True,
            result_data={
                'algorithm_version': 'RECTANGLE_CORNERS_V2',
                'opening_rectangle': opening,
            },
        )
        measured = {
            f'q{index}': {
                axis: opening['points'][f'p{index}'][axis] + 0.2
                for axis in ('x', 'y', 'z')
            }
            for index in range(1, 5)
        }
        response = self.client.post(
            reverse('vision:api_rack_location_tcp_verification', args=[result.id]),
            data=json.dumps({
                'coordinate_system': 'robot_base',
                'measured_points': measured,
                'tcp_name': 'VERIFY_PROBE_01',
                'operator': 'tester',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['tcp_verification']['passed'])
        result.refresh_from_db()
        self.assertEqual(result.result_data['tcp_verification']['tcp_name'], 'VERIFY_PROBE_01')

    def test_recipe_patch_normalizes_standard_four_points_for_workbench_editor(self):
        shifted = v2_config()
        for point in shifted['opening_rectangle']['standard_points'].values():
            point['x'] += 10.0
        response = self.client.generic(
            'PATCH',
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({
                'id': self.recipe.id,
                'reference_feature_config': shifted,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        recipe_data = response.json()['data']['recipe']
        self.assertEqual(recipe_data['reference_feature_config']['algorithm_version'], 'RECTANGLE_CORNERS_V2')
        self.assertAlmostEqual(recipe_data['standard_x'], 1210.0)
        self.recipe.refresh_from_db()
        self.assertAlmostEqual(float(self.recipe.standard_x), 1210.0)


class RackOpeningRectangleMissingEdgeTests(TestCase):
    """文档要求：某条边缺失时必须返回明确的 NG 错误码。"""

    def _cloud_without_edge(self, missing: str):
        """生成一组仅三条边有点的点云（模拟某边遮挡/缺失）。"""
        rng = np.random.default_rng(42)
        all_edges = {
            'top':    (STANDARD_POINTS[0], STANDARD_POINTS[1]),
            'right':  (STANDARD_POINTS[1], STANDARD_POINTS[2]),
            'bottom': (STANDARD_POINTS[2], STANDARD_POINTS[3]),
            'left':   (STANDARD_POINTS[3], STANDARD_POINTS[0]),
        }
        points = []
        for name, (start, end) in all_edges.items():
            if name == missing:
                continue
            for t in np.linspace(0.0, 1.0, 160):
                points.append(start * (1 - t) + end * t + rng.normal(0, 0.3, 3))
        return np.asarray(points)

    def test_missing_top_edge_returns_ng(self):
        cloud = self._cloud_without_edge('top')
        with self.assertRaises(RectangleLocationError) as ctx:
            RackOpeningRectangleLocator().locate(
                cloud,
                v2_config(min_edge_points=10),
                coordinate_system='robot_base',
            )
        self.assertEqual(ctx.exception.code, 'RECTANGLE_CONSTRAINT_FAILED')

    def test_missing_left_edge_returns_ng(self):
        cloud = self._cloud_without_edge('left')
        with self.assertRaises(RectangleLocationError) as ctx:
            RackOpeningRectangleLocator().locate(
                cloud,
                v2_config(min_edge_points=10),
                coordinate_system='robot_base',
            )
        self.assertEqual(ctx.exception.code, 'RECTANGLE_CONSTRAINT_FAILED')

    def test_three_edges_only_locate_ng_via_quality(self):
        """即使 locate() 不抛出异常，三边情况下质量检查也应使 locate_ok=False。"""
        cloud = self._cloud_without_edge('right')
        try:
            result = RackOpeningRectangleLocator().locate(
                cloud,
                v2_config(min_edge_points=10),
                coordinate_system='robot_base',
                confidence_threshold=0.01,
            )
            # 若没有抛出异常，locate_ok 应为 False 或误差很大
            if result.get('locate_ok'):
                # 允许的情况：右边有足够推断点，但 RMSE 超限
                self.assertFalse(result['locate_ok'])
        except RectangleLocationError:
            pass  # 抛出异常也是合法行为


class RackOpeningRectangleSizeToleranceTests(TestCase):
    """文档要求：宽高超出公差时返回 RECTANGLE_SIZE_OUT_OF_TOLERANCE。"""

    def test_width_out_of_tolerance_returns_ng(self):
        """生成一个宽度偏大 60mm 的矩形点云，公差设 10mm，应为 NG。"""
        rng = np.random.default_rng(11)
        # 宽度比标准宽 60mm（标准 600mm → 660mm）
        shifted = STANDARD_POINTS.copy()
        shifted[1][0] += 60.0  # P2 右移
        shifted[2][0] += 60.0  # P3 右移
        points = []
        for start, end in (
            (shifted[0], shifted[1]),
            (shifted[1], shifted[2]),
            (shifted[2], shifted[3]),
            (shifted[3], shifted[0]),
        ):
            for t in np.linspace(0.0, 1.0, 160):
                points.append(start * (1 - t) + end * t + rng.normal(0, 0.3, 3))
        cloud = np.asarray(points)
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(width_tolerance_mm=10.0),
            coordinate_system='robot_base',
            confidence_threshold=0.01,
        )
        self.assertFalse(result['locate_ok'])
        failure_codes = [f['code'] for f in result['quality']['failures']]
        self.assertIn('RECTANGLE_SIZE_OUT_OF_TOLERANCE', failure_codes)

    def test_within_tolerance_returns_ok(self):
        """在公差范围内的正常矩形应定位 OK。"""
        cloud, _ = rectangle_edge_cloud()
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(width_tolerance_mm=10.0, height_tolerance_mm=10.0),
            coordinate_system='robot_base',
            confidence_threshold=0.7,
        )
        self.assertTrue(result['locate_ok'])
        failure_codes = [f['code'] for f in result['quality']['failures']]
        self.assertNotIn('RECTANGLE_SIZE_OUT_OF_TOLERANCE', failure_codes)


class RackOpeningRectangleGeometricConsistencyTests(TestCase):
    """文档要求的几何一致性约束测试。"""

    def test_p5_always_derived_from_p1_to_p4_mean(self):
        """P5 始终等于 P1-P4 均值，不能是独立测量值。"""
        cloud, _ = rectangle_edge_cloud()
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(),
            coordinate_system='robot_base',
        )
        corners = np.asarray([
            [result['points'][f'p{i}'][axis] for axis in ('x', 'y', 'z')]
            for i in range(1, 5)
        ])
        derived_center = corners.mean(axis=0)
        reported_center = np.asarray([result['center'][axis] for axis in ('x', 'y', 'z')])
        np.testing.assert_allclose(reported_center, derived_center, atol=1e-6,
                                   err_msg='P5 必须严格等于 P1-P4 的算术均值')

    def test_kabsch_rotation_has_no_mirror(self):
        """Kabsch 刚体拟合的旋转矩阵行列式必须等于 +1（无镜像）。"""
        cloud, _ = rectangle_edge_cloud()
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(),
            coordinate_system='robot_base',
        )
        # deviation_transform 的旋转部分
        deviation_matrix = np.asarray(result['deviation_transform']['matrix'])
        rotation_3x3 = deviation_matrix[:3, :3]
        det = float(np.linalg.det(rotation_3x3))
        self.assertAlmostEqual(det, 1.0, places=5,
                               msg='刚体拟合旋转矩阵行列式必须为+1，不允许镜像变换')

    def test_deviation_and_correction_are_inverses(self):
        """deviation_transform 与 correction_transform 必须互为逆矩阵。"""
        cloud, _ = rectangle_edge_cloud()
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(),
            coordinate_system='robot_base',
        )
        deviation = np.asarray(result['deviation_transform']['matrix'])
        correction = np.asarray(result['correction_transform']['matrix'])
        product = deviation @ correction
        np.testing.assert_allclose(product, np.eye(4), atol=1e-6,
                                   err_msg='deviation_transform @ correction_transform 必须等于单位矩阵')

    def test_gaussian_noise_corner_error_within_threshold(self):
        """在 ±0.5mm 高斯噪声下，角点定位误差应在 2mm 以内。"""
        rng = np.random.default_rng(2026)
        points = []
        for start, end in (
            (STANDARD_POINTS[0], STANDARD_POINTS[1]),
            (STANDARD_POINTS[1], STANDARD_POINTS[2]),
            (STANDARD_POINTS[2], STANDARD_POINTS[3]),
            (STANDARD_POINTS[3], STANDARD_POINTS[0]),
        ):
            for t in np.linspace(0.0, 1.0, 200):
                points.append(start * (1 - t) + end * t + rng.normal(0, 0.5, 3))
        cloud = np.asarray(points)
        result = RackOpeningRectangleLocator().locate(
            cloud,
            v2_config(),
            coordinate_system='robot_base',
            confidence_threshold=0.5,
        )
        self.assertTrue(result['locate_ok'],
                        f'locate_ok=False, failures={result["quality"]["failures"]}')
        actual = np.asarray([
            [result['points'][f'p{i}'][axis] for axis in ('x', 'y', 'z')]
            for i in range(1, 5)
        ])
        max_corner_error = float(np.max(np.linalg.norm(actual - STANDARD_POINTS, axis=1)))
        self.assertLess(max_corner_error, 2.0,
                        f'高斯噪声下角点误差 {max_corner_error:.2f}mm 超过 2mm 阈值')

    def test_production_mode_no_median_fallback_for_v2_config(self):
        """生产模式下V2配方不允许静默回退到中位数算法，失败必须抛出明确错误或返回NG。"""
        # 传入一个极少点的点云，应触发 INSUFFICIENT_POINTS 而非用中位数凑数
        tiny_cloud = np.asarray([
            [900.0, 500.0, 1200.0],
            [1500.0, 500.0, 800.0],
        ])
        with self.assertRaises(RectangleLocationError) as ctx:
            RackOpeningRectangleLocator().locate(
                tiny_cloud,
                v2_config(),
                coordinate_system='robot_base',
            )
        self.assertIn(ctx.exception.code,
                      ('INSUFFICIENT_POINTS', 'OPENING_PLANE_NOT_FOUND', 'RECTANGLE_CONSTRAINT_FAILED'),
                      '点云极少时必须返回明确NG错误，不能静默回退中位数')
