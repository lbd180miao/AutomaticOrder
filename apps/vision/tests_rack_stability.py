"""Accuracy checks with known geometry, noise, outliers and moving cameras."""
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from scipy.spatial.transform import Rotation
from django.test import SimpleTestCase
from .algorithms.robust_rack_geometry import robust_plane
from .algorithms.local_template_3d import LocalTemplate3D
from .rack_location import RackLocationService
from .rack_spatial import pair_frame_from_planes
from .rack_spatial_service import reference_point_motion, robot_group_results


class RobustRackGeometryTests(SimpleTestCase):
    def cloud(self, depth, seed=4, noise=.6):
        rng = np.random.default_rng(seed)
        xy = rng.uniform([-200, -300], [200, 300], size=(3000, 2))
        z = depth + .05*xy[:, 0] - .03*xy[:, 1] + rng.normal(0, noise, len(xy))
        clean = np.column_stack((xy, z))
        outliers = rng.uniform([-200, -300, depth+20], [200, 300, depth+300], size=(750, 3))
        return np.concatenate([clean, outliers])

    def test_accuracy_at_1500_and_2000_mm_with_outliers(self):
        for depth, noise in [(1500, .6), (2000, 1.1)]:
            estimates = []
            for seed in range(6):
                plane, _ = robust_plane(self.cloud(depth, seed, noise))
                normal = np.asarray(plane['normal'])
                expected = np.array([-.05, .03, 1.]); expected /= np.linalg.norm(expected)
                self.assertLess(np.degrees(np.arccos(np.clip(normal @ expected, -1, 1))), .05)
                estimate = -plane['offset']/normal[2]
                self.assertLess(abs(estimate-depth), .12)
                estimates.append(estimate)
            self.assertLess(np.ptp(estimates), .15)

    def test_same_point_set_reordered_has_same_result(self):
        cloud = self.cloud(2000)
        first, _ = robust_plane(cloud)
        second, _ = robust_plane(cloud[np.random.default_rng(7).permutation(len(cloud))])
        self.assertEqual(first, second)

    def test_translation_is_preserved_not_smoothed_away(self):
        cloud = self.cloud(1500)
        first, _ = robust_plane(cloud)
        shift = np.array([12., -8., 500.])
        second, _ = robust_plane(cloud+shift)
        np.testing.assert_allclose(first['normal'], second['normal'], atol=1e-10)
        self.assertAlmostEqual(second['offset'], first['offset']-np.dot(first['normal'], shift), places=7)
        np.testing.assert_allclose(np.array(second['centroid'])-first['centroid'], shift, atol=1e-8)

    def test_collinear_and_missing_points_fail_explicitly(self):
        for cloud in [np.zeros((100, 3)), np.column_stack([np.arange(100), np.zeros(100), np.ones(100)]), np.full((100, 3), np.nan)]:
            with self.assertRaises(ValueError):
                robust_plane(cloud)

    def test_local_template_uses_robust_estimator(self):
        algo = LocalTemplate3D(ransac_distance_threshold=5)
        n, d, ratio = algo._ransac_numpy(self.cloud(2000))
        self.assertLess(abs(-d/n[2]-2000), .12)
        self.assertGreater(ratio, .75)

    def test_nearly_parallel_planes_report_amplification(self):
        first = {'normal':[0, 0, 1], 'offset':-1500, 'centroid':[0, 0, 1500]}
        n = [np.sin(np.deg2rad(2)), 0, np.cos(np.deg2rad(2))]
        second = {'normal':n, 'offset':-1500*n[2], 'centroid':[0, 0, 1500]}
        pair = pair_frame_from_planes(first, second)
        self.assertFalse(pair['intersection_reliable'])
        self.assertGreater(pair['intersection_amplification'], 28)
        self.assertTrue(pair['quality_warnings'])
        self.assertFalse(pair['along_line_position_observable'])


class MovingCameraTests(SimpleTestCase):
    @staticmethod
    def context(camera):
        return {'T_flange_camera': {'matrix':np.eye(4).tolist()},
                'T_base_flange': {'matrix':camera.tolist()}}

    def compare(self, motion):
        old_camera = np.eye(4)
        current_camera = np.eye(4)
        current_camera[:3,:3] = Rotation.from_euler('xyz', [3., -5., 2.], degrees=True).as_matrix()
        current_camera[:3,3] = [20., -10., -500.]
        base_frame = np.eye(4); base_frame[:3,3] = [100., 200., 1500.]
        old = np.linalg.inv(old_camera) @ base_frame
        current = np.linalg.inv(current_camera) @ motion @ base_frame
        delta = current @ np.linalg.inv(old)
        result = RackLocationService._robot_compensation_payload(
            {'matrix':delta.tolist()}, self.context(current_camera), self.context(old_camera))
        np.testing.assert_allclose(result['matrix'], motion, atol=1e-9)
        detail = reference_point_motion({'frame':current.tolist(), 'delta_T':delta.tolist()}, result)
        np.testing.assert_allclose(list(detail['reference_point_displacement_mm'].values()),
                                   (motion @ base_frame-base_frame)[:3,3], atol=1e-9)
        return result

    def test_static_rack_camera_moves_500mm_and_rotates(self):
        self.compare(np.eye(4))

    def test_rack_motion_survives_camera_motion_correction(self):
        motion = np.eye(4)
        motion[:3,:3] = Rotation.from_euler('z', .5, degrees=True).as_matrix()
        motion[:3,3] = [4, -7, 9]
        self.compare(motion)

    def test_incomplete_reference_pose_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            RackLocationService._robot_compensation_payload(
                {'matrix':np.eye(4).tolist()}, self.context(np.eye(4)), {})

    def test_group_conversion_passes_saved_reference_pose(self):
        reference = self.context(np.eye(4))
        camera = np.eye(4); camera[2,3] = -500
        current = self.context(camera)
        frame = np.eye(4); frame[2,3] = 2000
        delta = np.eye(4); delta[2,3] = 500
        service = SimpleNamespace(_recipe_transform_context=lambda recipe:current,
                                  _robot_compensation_payload=RackLocationService._robot_compensation_payload)
        recipe = SimpleNamespace(local_template_std={'transform_context':reference})
        result = robot_group_results(service, recipe, {k:{'frame':frame.tolist(),'delta_T':delta.tolist()} for k in ('A','B')})
        self.assertEqual(result['robot_conversion_error'], '')
        for group in result['robot_groups'].values():
            np.testing.assert_allclose(group['matrix'], np.eye(4), atol=1e-9)
