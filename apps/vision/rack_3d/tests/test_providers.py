"""Provider 单元测试。Requirements: 26.1, 26.2"""

import unittest
import numpy as np

from apps.vision.rack_3d.providers import (
    MockHandEyeProvider,
    MockRobotPoseProvider,
    MockDepthCameraProvider,
    RealHandEyeProvider,
    RealRobotPoseProvider,
    ProviderFactory,
)
from apps.vision.rack_3d.exceptions import ConfigurationError


class TestMockHandEyeProvider(unittest.TestCase):
    def setUp(self):
        self.provider = MockHandEyeProvider()

    def test_returns_fixed_4x4_matrix(self):
        m1 = self.provider.get_hand_eye_matrix()
        m2 = self.provider.get_hand_eye_matrix(recipe_id=99)
        self.assertEqual(m1.shape, (4, 4))
        np.testing.assert_array_equal(m1, m2)  # Property 7: 不变性

    def test_translation_matches_spec(self):
        m = self.provider.get_hand_eye_matrix()
        np.testing.assert_allclose(m[:3, 3], [30, -60, 120])
        np.testing.assert_allclose(m[3], [0, 0, 0, 1])

    def test_returned_matrix_is_a_copy(self):
        m = self.provider.get_hand_eye_matrix()
        m[0, 0] = 999
        self.assertEqual(self.provider.get_hand_eye_matrix()[0, 0], 1.0)


class TestMockRobotPoseProvider(unittest.TestCase):
    def setUp(self):
        self.provider = MockRobotPoseProvider()

    def test_three_layer_z_heights(self):
        self.assertEqual(self.provider.get_robot_pose_dict(1)['Z'], 600.0)
        self.assertEqual(self.provider.get_robot_pose_dict(2)['Z'], 900.0)
        self.assertEqual(self.provider.get_robot_pose_dict(3)['Z'], 1200.0)

    def test_pose_dict_has_required_keys(self):
        pose = self.provider.get_robot_pose_dict(1)
        for k in ('X', 'Y', 'Z', 'RX', 'RY', 'RZ'):
            self.assertIn(k, pose)

    def test_pose_matrix_translation(self):
        m = self.provider.get_robot_pose_matrix(2)
        self.assertEqual(m.shape, (4, 4))
        np.testing.assert_allclose(m[:3, 3], [1000, 500, 900])

    def test_invalid_layer_raises(self):
        with self.assertRaises(Exception):
            self.provider.get_robot_pose_dict(99)


class TestMockDepthCameraProvider(unittest.TestCase):
    def setUp(self):
        self.provider = MockDepthCameraProvider(seed=42)

    def test_structure_complete(self):
        """Property 10: 数据结构完整性。"""
        pc = self.provider.capture_pointcloud()
        for key in ('data', 'width', 'height', 'frame_index', 'confidence'):
            self.assertIn(key, pc)
        self.assertIsInstance(pc['data'], np.ndarray)
        self.assertIsInstance(pc['width'], int)
        self.assertIsInstance(pc['height'], int)

    def test_data_shape_is_hwc(self):
        pc = self.provider.capture_pointcloud()
        self.assertEqual(pc['data'].ndim, 3)
        self.assertEqual(pc['data'].shape[2], 3)
        self.assertEqual(pc['data'].shape[0], pc['height'])
        self.assertEqual(pc['data'].shape[1], pc['width'])


class TestProviderFactory(unittest.TestCase):
    def test_creates_mock_in_mock_mode(self):
        self.assertIsInstance(ProviderFactory.create_hand_eye_provider('MOCK'), MockHandEyeProvider)
        self.assertIsInstance(ProviderFactory.create_robot_pose_provider('MOCK'), MockRobotPoseProvider)
        self.assertIsInstance(ProviderFactory.create_depth_camera_provider('MOCK'), MockDepthCameraProvider)

    def test_creates_real_in_real_mode(self):
        self.assertIsInstance(ProviderFactory.create_hand_eye_provider('REAL'), RealHandEyeProvider)
        self.assertIsInstance(ProviderFactory.create_robot_pose_provider('REAL'), RealRobotPoseProvider)

    def test_case_insensitive_mode(self):
        self.assertIsInstance(ProviderFactory.create_hand_eye_provider('mock'), MockHandEyeProvider)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ConfigurationError):
            ProviderFactory.create_hand_eye_provider('BOGUS')


if __name__ == '__main__':
    unittest.main()
