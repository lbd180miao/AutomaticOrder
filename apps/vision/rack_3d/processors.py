"""
点云处理模块 (Point Cloud Processing)

负责点云坐标转换、ROI 裁剪、离群点滤波与体素下采样。
坐标转换公式：P_base = T_base_flange @ T_flange_camera @ P_camera

Requirements: 2.1-2.3, 2.5, 4.1-4.7, 21.1-21.7, 25.2, 25.4, 25.5
"""

import logging
from typing import Optional

import numpy as np

from .exceptions import RackPositioningErrorCode as EC, CoordinateTransformError

logger = logging.getLogger(__name__)

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except Exception:  # pragma: no cover - open3d 可选
    OPEN3D_AVAILABLE = False
    logger.warning("Open3D 不可用，滤波/下采样将回退到 NumPy 实现")


class PointCloudProcessor:
    """点云处理器：坐标转换、ROI 裁剪、滤波、下采样。"""

    def transform_to_robot_coords(
        self,
        pointcloud: np.ndarray,
        T_flange_camera: np.ndarray,
        T_base_flange: np.ndarray,
    ) -> np.ndarray:
        """将相机坐标系点云转换到机器人基坐标系。

        Args:
            pointcloud: 相机坐标系点云，(N,3) 或 (H,W,3)
            T_flange_camera: 4x4 手眼标定矩阵
            T_base_flange: 4x4 机器人位姿矩阵

        Returns:
            机器人基坐标系点云 (M,3)，已过滤 NaN/inf/零点
        """
        T_flange_camera = np.asarray(T_flange_camera, dtype=np.float64)
        T_base_flange = np.asarray(T_base_flange, dtype=np.float64)
        if T_flange_camera.shape != (4, 4):
            raise CoordinateTransformError(
                EC.HAND_EYE_INVALID, f"T_flange_camera 形状必须为 (4,4)，实际 {T_flange_camera.shape}"
            )
        if T_base_flange.shape != (4, 4):
            raise CoordinateTransformError(
                EC.ROBOT_POSE_MISSING, f"T_base_flange 形状必须为 (4,4)，实际 {T_base_flange.shape}"
            )

        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.ndim == 3:  # H×W×3 -> N×3
            pts = pts.reshape(-1, 3)
        elif pts.ndim == 1 and pts.shape[0] == 3:
            pts = pts.reshape(1, 3)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise CoordinateTransformError(
                EC.TRANSFORM_FAILED, f"点云形状必须为 (N,3) 或 (H,W,3)，实际 {pts.shape}"
            )

        # 过滤无效点：NaN / inf / 近零点
        valid = (
            np.isfinite(pts).all(axis=1)
            & (np.abs(pts).sum(axis=1) > 1e-6)
        )
        pts = pts[valid]
        if pts.shape[0] == 0:
            return np.empty((0, 3), dtype=np.float64)

        homo = np.hstack([pts, np.ones((pts.shape[0], 1))])
        T_combined = T_base_flange @ T_flange_camera
        robot = (T_combined @ homo.T).T[:, :3]
        logger.info("坐标转换: %d 点 -> 机器人基坐标系", robot.shape[0])
        return robot

    def crop_roi(
        self,
        pointcloud: np.ndarray,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        z_min: float, z_max: float,
    ) -> np.ndarray:
        """按 6 个边界裁剪点云，返回边界内的点 (M,3)。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.size == 0:
            return np.empty((0, 3), dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 3:
            pts = pts.reshape(-1, 3)
        mask = (
            (pts[:, 0] >= x_min) & (pts[:, 0] <= x_max)
            & (pts[:, 1] >= y_min) & (pts[:, 1] <= y_max)
            & (pts[:, 2] >= z_min) & (pts[:, 2] <= z_max)
        )
        cropped = pts[mask]
        logger.info("ROI 裁剪: %d -> %d 点", pts.shape[0], cropped.shape[0])
        return cropped

    def filter_outliers(
        self,
        pointcloud: np.ndarray,
        nb_neighbors: int = 20,
        std_ratio: float = 2.0,
    ) -> np.ndarray:
        """统计离群点滤波（Open3D，缺失时回退简单标准差滤波）。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.shape[0] < nb_neighbors:
            return pts

        if OPEN3D_AVAILABLE:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(pts)
            clean, _ = pcd.remove_statistical_outlier(nb_neighbors, std_ratio)
            filtered = np.asarray(clean.points)
        else:
            centroid = pts.mean(axis=0)
            dist = np.linalg.norm(pts - centroid, axis=1)
            thr = dist.mean() + std_ratio * dist.std()
            filtered = pts[dist <= thr]

        logger.info("离群点滤波: %d -> %d 点", pts.shape[0], filtered.shape[0])
        return filtered

    def downsample(self, pointcloud: np.ndarray, voxel_size: float = 5.0) -> np.ndarray:
        """体素下采样（Open3D，缺失时回退 NumPy 体素栅格）。"""
        pts = np.asarray(pointcloud, dtype=np.float64)
        if pts.shape[0] == 0 or voxel_size <= 0:
            return pts

        if OPEN3D_AVAILABLE:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(pts)
            down = np.asarray(pcd.voxel_down_sample(voxel_size).points)
        else:
            keys = np.floor(pts / voxel_size).astype(np.int64)
            _, idx = np.unique(keys, axis=0, return_index=True)
            down = pts[np.sort(idx)]

        logger.info("体素下采样: %d -> %d 点", pts.shape[0], down.shape[0])
        return down
