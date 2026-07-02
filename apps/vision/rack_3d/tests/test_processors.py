"""PointCloudProcessor 单元测试。Requirements: 26.1, 26.2"""

import unittest
import numpy as np

from apps.vision.rack_3d.processors import PointCloudProcessor


def _translation(tx, ty, tz):
    T = np.eye(4)
    T[:3, 3] = [tx, ty, tz]
    return T


class TestTransform(unittest.TestCase):
    def setUp(self):
        self.p = PointCloudProcessor()

    def test_identity(self):
        pts = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        out = self.p.transform_to_robot_coords(pts, np.eye(4), np.eye(4))
        np.testing.assert_allclose(out, pts)

    def test_translation_chain(self):
        pts = np.array([[0.0, 0.0, 10.0]])
        T_fc = _translation(30, -60, 120)
        T_bf = _translation(1000, 500, 900)
        out = self.p.transform_to_robot_coords(pts, T_fc, T_bf)
        np.testing.assert_allclose(out[0], [1030, 440, 1030])

    def test_rotation_preserves_distance(self):
        """Property 2: 刚体变换保持点间距离。"""
        pts = np.array([[0.0, 0.0, 100.0], [50.0, 0.0, 100.0]])
        theta = np.pi / 4
        T_bf = np.eye(4)
        T_bf[:3, :3] = [[np.cos(theta), -np.sin(theta), 0],
                        [np.sin(theta), np.cos(theta), 0],
                        [0, 0, 1]]
        out = self.p.transform_to_robot_coords(pts, np.eye(4), T_bf)
        d_in = np.linalg.norm(pts[0] - pts[1])
        d_out = np.linalg.norm(out[0] - out[1])
        self.assertAlmostEqual(d_in, d_out, places=6)

    def test_handles_hwc_format(self):
        cloud = np.ones((4, 5, 3)) * 10.0
        out = self.p.transform_to_robot_coords(cloud, np.eye(4), np.eye(4))
        self.assertEqual(out.shape, (20, 3))

    def test_filters_nan_and_zero(self):
        pts = np.array([[1.0, 1.0, 1.0], [np.nan, 0, 0], [0, 0, 0]])
        out = self.p.transform_to_robot_coords(pts, np.eye(4), np.eye(4))
        self.assertEqual(out.shape[0], 1)


class TestCrop(unittest.TestCase):
    def setUp(self):
        self.p = PointCloudProcessor()

    def test_keeps_inside_removes_outside(self):
        """Property 3: 裁剪后所有点在边界内。"""
        pts = np.array([[5, 5, 5], [50, 50, 50], [-10, 5, 5]], dtype=float)
        out = self.p.crop_roi(pts, 0, 10, 0, 10, 0, 10)
        self.assertEqual(out.shape[0], 1)
        self.assertTrue(np.all(out[:, 0] >= 0) and np.all(out[:, 0] <= 10))

    def test_empty_input(self):
        out = self.p.crop_roi(np.empty((0, 3)), 0, 1, 0, 1, 0, 1)
        self.assertEqual(out.shape[0], 0)

    def test_no_points_in_roi(self):
        pts = np.array([[100, 100, 100]], dtype=float)
        out = self.p.crop_roi(pts, 0, 1, 0, 1, 0, 1)
        self.assertEqual(out.shape[0], 0)


class TestFilterDownsample(unittest.TestCase):
    def setUp(self):
        self.p = PointCloudProcessor()

    def test_filter_removes_outlier(self):
        cluster = np.random.default_rng(0).normal(0, 1, (200, 3))
        pts = np.vstack([cluster, [[1000, 1000, 1000]]])
        out = self.p.filter_outliers(pts)
        self.assertLess(out.shape[0], pts.shape[0])

    def test_downsample_reduces_count(self):
        pts = np.random.default_rng(0).uniform(0, 100, (5000, 3))
        out = self.p.downsample(pts, voxel_size=10.0)
        self.assertLess(out.shape[0], pts.shape[0])


if __name__ == '__main__':
    unittest.main()
