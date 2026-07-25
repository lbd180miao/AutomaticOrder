"""
定位算法模块 (Positioning Algorithms)

提取每层刚性基准并解算三轴坐标：
- Z 轴：支撑面 RANSAC 平面拟合，取内点平均高度
- Y 轴：前边缘 ROI 中位数（对噪声鲁棒）
- X 轴：立柱 ROI 中位数

每个方法返回包含坐标、点数与置信度 [0,1] 的 dict。

Requirements: 5.1-5.5, 6.1-6.4, 7.1-7.4, 25.3
"""

import logging
from typing import Dict, Any

import numpy as np

from .exceptions import RackPositioningErrorCode as EC, PositioningAlgorithmError

logger = logging.getLogger(__name__)

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except Exception:  # pragma: no cover
    OPEN3D_AVAILABLE = False


class PositioningAlgorithm:
    """料架三轴定位算法。"""

    MIN_PLANE_POINTS = 10
    MIN_EDGE_POINTS = 5
    MIN_PILLAR_POINTS = 5

    # ------------------------------------------------------------------
    # Z 轴：支撑面平面拟合
    # ------------------------------------------------------------------
    def detect_support_plane(
        self,
        pointcloud: np.ndarray,
        ransac_threshold: float = 5.0,
        max_iterations: int = 1000,
    ) -> Dict[str, Any]:
        """RANSAC 平面拟合求支撑面高度 Z。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.shape[0] < self.MIN_PLANE_POINTS:
            raise PositioningAlgorithmError(
                EC.ROI_INSUFFICIENT_POINTS,
                f"支撑面 ROI 点数不足: {pts.shape[0]} < {self.MIN_PLANE_POINTS}",
                {'point_count': int(pts.shape[0])},
            )

        if OPEN3D_AVAILABLE:
            plane_model, inliers = self._segment_plane_o3d(pts, ransac_threshold, max_iterations)
        else:
            plane_model, inliers = self._segment_plane_numpy(pts, ransac_threshold, max_iterations)

        if inliers.size < self.MIN_PLANE_POINTS:
            raise PositioningAlgorithmError(
                EC.RANSAC_FAILED, f"平面内点数不足: {inliers.size}"
            )

        inlier_pts = pts[inliers]
        z_actual = float(np.mean(inlier_pts[:, 2]))
        z_std = float(np.std(inlier_pts[:, 2]))
        confidence = float(inliers.size / pts.shape[0])
        logger.info("Z 轴: 平面 Z=%.3f±%.3f, 内点 %d/%d, 置信度=%.3f",
                    z_actual, z_std, inliers.size, pts.shape[0], confidence)
        return {
            'z_actual': z_actual,
            'z_std': z_std,
            'plane_model': list(map(float, plane_model)),
            'inlier_count': int(inliers.size),
            'point_count': int(pts.shape[0]),
            'confidence': confidence,
        }

    @staticmethod
    def _segment_plane_o3d(pts, threshold, iterations):
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        model, inliers = pcd.segment_plane(
            distance_threshold=threshold, ransac_n=3, num_iterations=iterations
        )
        return np.asarray(model), np.asarray(inliers, dtype=int)

    @staticmethod
    def _segment_plane_numpy(pts, threshold, iterations):
        # 【Bug 修复】使用固定种子 42，避免每次 RANSAC 采样结果不同导致 Z 轴定位不稳定。
        # 原代码 np.random.default_rng() 无种子，每次结果随机波动。
        rng = np.random.default_rng(42)
        best_model, best_inliers, best_score = None, np.array([], dtype=int), 0
        n = pts.shape[0]
        for _ in range(iterations):
            idx = rng.choice(n, 3, replace=False)
            p = pts[idx]
            normal = np.cross(p[1] - p[0], p[2] - p[0])
            norm = np.linalg.norm(normal)
            if norm < 1e-9:
                continue
            normal /= norm
            d = -normal.dot(p[0])
            dist = np.abs(pts @ normal + d)
            inliers = np.where(dist < threshold)[0]
            if inliers.size > best_score:
                best_score = inliers.size
                best_model = np.append(normal, d)
                best_inliers = inliers
        if best_model is None:
            best_model = np.array([0.0, 0.0, 1.0, -float(np.mean(pts[:, 2]))])
        return best_model, best_inliers

    # ------------------------------------------------------------------
    # Y 轴：前边缘
    # ------------------------------------------------------------------
    def detect_front_edge(self, pointcloud: np.ndarray) -> Dict[str, Any]:
        """前边缘 ROI Y 中位数求 Y。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.shape[0] < self.MIN_EDGE_POINTS:
            raise PositioningAlgorithmError(
                EC.EDGE_DETECTION_FAILED,
                f"前边缘 ROI 点数不足: {pts.shape[0]} < {self.MIN_EDGE_POINTS}",
                {'point_count': int(pts.shape[0])},
            )
        y = pts[:, 1]
        y_actual = float(np.median(y))
        y_std = float(np.std(y))
        confidence = float(1.0 / (1.0 + y_std / 10.0))
        logger.info("Y 轴: 前边缘 Y=%.3f±%.3f, %d 点, 置信度=%.3f",
                    y_actual, y_std, pts.shape[0], confidence)
        return {
            'y_actual': y_actual,
            'y_std': y_std,
            'edge_points_count': int(pts.shape[0]),
            'confidence': confidence,
        }

    # ------------------------------------------------------------------
    # X 轴：立柱
    # ------------------------------------------------------------------
    def detect_pillar(self, pointcloud: np.ndarray) -> Dict[str, Any]:
        """立柱 ROI X 中位数求 X。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.shape[0] < self.MIN_PILLAR_POINTS:
            raise PositioningAlgorithmError(
                EC.PILLAR_DETECTION_FAILED,
                f"立柱 ROI 点数不足: {pts.shape[0]} < {self.MIN_PILLAR_POINTS}",
                {'point_count': int(pts.shape[0])},
            )
        x = pts[:, 0]
        x_actual = float(np.median(x))
        x_std = float(np.std(x))
        confidence = float(1.0 / (1.0 + x_std / 10.0))
        logger.info("X 轴: 立柱 X=%.3f±%.3f, %d 点, 置信度=%.3f",
                    x_actual, x_std, pts.shape[0], confidence)
        return {
            'x_actual': x_actual,
            'x_std': x_std,
            'pillar_points_count': int(pts.shape[0]),
            'confidence': confidence,
        }
