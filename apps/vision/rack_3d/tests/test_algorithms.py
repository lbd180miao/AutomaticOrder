"""PositioningAlgorithm 单元测试。Requirements: 26.1, 26.2"""

import unittest
import numpy as np

from apps.vision.rack_3d.algorithms import PositioningAlgorithm
from apps.vision.rack_3d.exceptions import PositioningAlgorithmError


class TestSupportPlane(unittest.TestCase):
    def setUp(self):
        self.algo = PositioningAlgorithm()

    def _plane(self, z, noise=0.0, n=400):
        rng = np.random.default_rng(0)
        xy = rng.uniform(-100, 100, (n, 2))
        zz = np.full((n, 1), z) + rng.normal(0, noise, (n, 1))
        return np.hstack([xy, zz])

    def test_flat_surface(self):
        """Property 8: 平面拟合有效，内点比例 > 0.5。"""
        res = self.algo.detect_support_plane(self._plane(800.0))
        self.assertAlmostEqual(res['z_actual'], 800.0, delta=1.0)
        self.assertGreater(res['confidence'], 0.5)

    def test_noisy_surface(self):
        res = self.algo.detect_support_plane(self._plane(795.0, noise=2.0))
        self.assertAlmostEqual(res['z_actual'], 795.0, delta=2.0)

    def test_insufficient_points_raises(self):
        with self.assertRaises(PositioningAlgorithmError):
            self.algo.detect_support_plane(np.zeros((3, 3)))


class TestFrontEdge(unittest.TestCase):
    def setUp(self):
        self.algo = PositioningAlgorithm()

    def test_edge_median(self):
        rng = np.random.default_rng(1)
        x = rng.uniform(-100, 100, 60)
        y = np.full(60, 600.0) + rng.normal(0, 0.5, 60)
        z = rng.uniform(800, 840, 60)
        res = self.algo.detect_front_edge(np.column_stack([x, y, z]))
        self.assertAlmostEqual(res['y_actual'], 600.0, delta=1.0)
        self.assertEqual(res['edge_points_count'], 60)

    def test_insufficient_points_raises(self):
        with self.assertRaises(PositioningAlgorithmError):
            self.algo.detect_front_edge(np.zeros((2, 3)))


class TestPillar(unittest.TestCase):
    def setUp(self):
        self.algo = PositioningAlgorithm()

    def test_pillar_median(self):
        rng = np.random.default_rng(2)
        z = np.linspace(700, 900, 60)
        x = np.full(60, 200.0) + rng.normal(0, 0.5, 60)
        y = np.full(60, 0.0) + rng.normal(0, 0.5, 60)
        res = self.algo.detect_pillar(np.column_stack([x, y, z]))
        self.assertAlmostEqual(res['x_actual'], 200.0, delta=1.0)

    def test_insufficient_points_raises(self):
        with self.assertRaises(PositioningAlgorithmError):
            self.algo.detect_pillar(np.zeros((2, 3)))


if __name__ == '__main__':
    unittest.main()
