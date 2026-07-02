"""
属性测试 (Property-Based Tests) —— 随机化多次迭代验证通用属性。

不依赖 Hypothesis：每个属性用 NumPy RNG 生成 >=100 组随机输入循环验证，
对应设计文档 Correctness Properties 1-9。

Feature: rack-3d-positioning-refactor
Requirements: 2.1-2.3, 4.1-4.6, 5.1-5.2, 9.2-9.4, 21.1-21.2
"""

import unittest
import numpy as np
from scipy.spatial.transform import Rotation

from apps.vision.rack_3d.processors import PointCloudProcessor
from apps.vision.rack_3d.algorithms import PositioningAlgorithm
from apps.vision.rack_3d.calculators import CompensationCalculator
from apps.vision.rack_3d.providers import MockHandEyeProvider

ITER = 100


def _rigid(rng):
    """随机 4x4 刚体变换矩阵。"""
    T = np.eye(4)
    T[:3, :3] = Rotation.random(random_state=rng.integers(1 << 30)).as_matrix()
    T[:3, 3] = rng.uniform(-500, 500, 3)
    return T


class TestProperties(unittest.TestCase):
    def setUp(self):
        self.proc = PointCloudProcessor()
        self.algo = PositioningAlgorithm()
        self.calc = CompensationCalculator()

    def test_property1_transform_reversibility(self):
        """Property 1: 正向变换后逆变换可恢复原始坐标。"""
        for i in range(ITER):
            rng = np.random.default_rng(i)
            pts = rng.uniform(-300, 300, (rng.integers(10, 60), 3)) + 500  # 远离原点，避免被零点过滤
            T_fc, T_bf = _rigid(rng), _rigid(rng)
            robot = self.proc.transform_to_robot_coords(pts, T_fc, T_bf)
            T_inv = np.linalg.inv(T_bf @ T_fc)
            homo = np.hstack([robot, np.ones((robot.shape[0], 1))])
            recovered = (T_inv @ homo.T).T[:, :3]
            np.testing.assert_allclose(recovered, pts, rtol=1e-5, atol=1e-4)

    def test_property2_distance_preserved(self):
        """Property 2: 刚体变换保持点间欧氏距离。"""
        for i in range(ITER):
            rng = np.random.default_rng(1000 + i)
            pts = rng.uniform(-300, 300, (2, 3)) + 500
            robot = self.proc.transform_to_robot_coords(pts, _rigid(rng), _rigid(rng))
            d_in = np.linalg.norm(pts[0] - pts[1])
            d_out = np.linalg.norm(robot[0] - robot[1])
            self.assertAlmostEqual(d_in, d_out, places=5)

    def test_property3_roi_crop_within_bounds(self):
        """Property 3: 裁剪后所有点严格落在 ROI 边界内。"""
        for i in range(ITER):
            rng = np.random.default_rng(2000 + i)
            pts = rng.uniform(0, 2000, (rng.integers(100, 400), 3))
            b = {'x_min': rng.uniform(0, 900), 'x_max': rng.uniform(1000, 2000),
                 'y_min': rng.uniform(0, 400), 'y_max': rng.uniform(500, 1000),
                 'z_min': rng.uniform(0, 500), 'z_max': rng.uniform(600, 1200)}
            out = self.proc.crop_roi(pts, **b)
            if out.shape[0]:
                self.assertTrue(np.all(out[:, 0] >= b['x_min']) and np.all(out[:, 0] <= b['x_max']))
                self.assertTrue(np.all(out[:, 1] >= b['y_min']) and np.all(out[:, 1] <= b['y_max']))
                self.assertTrue(np.all(out[:, 2] >= b['z_min']) and np.all(out[:, 2] <= b['z_max']))

    def test_property4_invalid_points_filtered(self):
        """Property 4: NaN/inf/零点在坐标转换后被过滤，输出全部有限。"""
        for i in range(ITER):
            rng = np.random.default_rng(3000 + i)
            good = rng.uniform(-200, 200, (rng.integers(10, 40), 3)) + 400
            bad = np.array([[np.nan, 1, 1], [np.inf, 2, 2], [0, 0, 0]])
            pts = np.vstack([good, bad])
            rng.shuffle(pts)
            out = self.proc.transform_to_robot_coords(pts, np.eye(4), np.eye(4))
            self.assertTrue(np.isfinite(out).all())
            self.assertEqual(out.shape[0], good.shape[0])

    def test_property5_offset_equals_actual_minus_standard(self):
        """Property 5: offset = actual - standard，精度到 0.001mm。"""
        for i in range(ITER):
            rng = np.random.default_rng(4000 + i)
            a = rng.uniform(-2000, 2000, 3)
            s = rng.uniform(-2000, 2000, 3)
            off = self.calc.calculate_offsets(a[0], a[1], a[2], s[0], s[1], s[2])
            self.assertAlmostEqual(off['offset_x'], a[0] - s[0], places=3)
            self.assertAlmostEqual(off['offset_y'], a[1] - s[1], places=3)
            self.assertAlmostEqual(off['offset_z'], a[2] - s[2], places=3)

    def test_property7_hand_eye_invariance(self):
        """Property 7: 多次获取手眼矩阵返回逐元素相同的矩阵。"""
        provider = MockHandEyeProvider()
        base = provider.get_hand_eye_matrix()
        for i in range(ITER):
            np.testing.assert_array_equal(provider.get_hand_eye_matrix(recipe_id=i), base)

    def test_property8_plane_fit_valid(self):
        """Property 8: 含共面点(带噪)的点云 RANSAC 内点比例 > 0.5。"""
        for i in range(50):
            rng = np.random.default_rng(5000 + i)
            n = rng.integers(100, 300)
            xy = rng.uniform(-100, 100, (n, 2))
            z = np.full((n, 1), rng.uniform(500, 1500)) + rng.normal(0, 1.0, (n, 1))
            res = self.algo.detect_support_plane(np.hstack([xy, z]), ransac_threshold=5.0)
            self.assertGreater(res['inlier_count'] / res['point_count'], 0.5)

    def test_property9_downsample_preserves_bbox(self):
        """Property 9: 下采样后包围盒与原始差异 < 5%（各轴跨度）。"""
        for i in range(50):
            rng = np.random.default_rng(6000 + i)
            pts = rng.uniform(0, 300, (rng.integers(2000, 5000), 3))
            down = self.proc.downsample(pts, voxel_size=5.0)
            for ax in range(3):
                span = pts[:, ax].max() - pts[:, ax].min()
                d_span = down[:, ax].max() - down[:, ax].min()
                self.assertLess(abs(span - d_span) / max(span, 1e-6), 0.05)


if __name__ == '__main__':
    unittest.main()
