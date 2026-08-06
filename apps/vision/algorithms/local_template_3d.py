"""
局部三维几何模板算法核心类
============================

算法原理：
  示教阶段：采集区域1（上水平面）、区域2（左竖直面）、区域3（下水平面）的3D点云，
           拟合三个平面，建立标准局部坐标系 T_std（4x4 齐次变换矩阵）。
  生产阶段：重新拟合三个区域，建立当前局部坐标系 T_cur，
           计算刚体变换矩阵 ΔT = T_cur @ inv(T_std)，
           输出 6DoF 偏差量 [ΔX, ΔY, ΔZ, ΔRx, ΔRy, ΔRz] 发送给 PLC。

坐标轴定义（料架视角）：
  Z_local = 上/下水平面加权平均法向量（指向上方）
  X_local = 左竖直面法向量投影到与Z垂直平面（指向料架右侧）
  Y_local = Z_local × X_local（指向料架纵深方向，由右手定则确定）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class PlaneResult:
    """单个平面拟合结果"""
    normal: np.ndarray          # 单位法向量 (3,)
    offset: float               # 平面偏移量 d，满足 normal·p + offset = 0
    centroid: np.ndarray        # 点云质心 (3,)
    inlier_ratio: float         # 内点比率 0~1
    point_count: int            # 原始点数

    def to_dict(self) -> dict:
        return {
            "normal": self.normal.tolist(),
            "offset": float(self.offset),
            "centroid": self.centroid.tolist(),
            "inlier_ratio": float(self.inlier_ratio),
            "point_count": int(self.point_count),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlaneResult":
        return cls(
            normal=np.array(d["normal"]),
            offset=float(d["offset"]),
            centroid=np.array(d["centroid"]),
            inlier_ratio=float(d["inlier_ratio"]),
            point_count=int(d["point_count"]),
        )


@dataclass
class LocalFrameResult:
    """局部坐标系建立结果（4x4 齐次变换矩阵 + 三平面参数）"""
    T: np.ndarray                           # 4x4 齐次变换矩阵（相机坐标系 → 局部坐标系）
    plane1: PlaneResult                     # 上水平面
    plane2: PlaneResult                     # 左竖直面
    plane3: PlaneResult                     # 下水平面
    origin: np.ndarray                      # 局部原点 (3,)，在相机坐标系中的坐标
    x_local: np.ndarray                     # X 轴方向 (3,)
    y_local: np.ndarray                     # Y 轴方向 (3,)
    z_local: np.ndarray                     # Z 轴方向 (3,)

    def to_dict(self) -> dict:
        return {
            "T": self.T.tolist(),
            "plane1": self.plane1.to_dict(),
            "plane2": self.plane2.to_dict(),
            "plane3": self.plane3.to_dict(),
            "origin": self.origin.tolist(),
            "x_local": self.x_local.tolist(),
            "y_local": self.y_local.tolist(),
            "z_local": self.z_local.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LocalFrameResult":
        return cls(
            T=np.array(d["T"]),
            plane1=PlaneResult.from_dict(d["plane1"]),
            plane2=PlaneResult.from_dict(d["plane2"]),
            plane3=PlaneResult.from_dict(d["plane3"]),
            origin=np.array(d["origin"]),
            x_local=np.array(d["x_local"]),
            y_local=np.array(d["y_local"]),
            z_local=np.array(d["z_local"]),
        )


@dataclass
class DeltaTransformResult:
    """刚体变换结果"""
    delta_T: np.ndarray          # 4x4 刚体变换矩阵 ΔT = T_cur @ inv(T_std)
    dX: float                    # X 方向平移偏差 (mm)
    dY: float                    # Y 方向平移偏差 (mm)
    dZ: float                    # Z 方向平移偏差 (mm)
    dRx: float                   # 绕X轴旋转偏差 (°)
    dRy: float                   # 绕Y轴旋转偏差 (°)
    dRz: float                   # 绕Z轴旋转偏差 (°)

    def to_dict(self) -> dict:
        return {
            "delta_T": self.delta_T.tolist(),
            "dX": round(self.dX, 4),
            "dY": round(self.dY, 4),
            "dZ": round(self.dZ, 4),
            "dRx": round(self.dRx, 4),
            "dRy": round(self.dRy, 4),
            "dRz": round(self.dRz, 4),
        }

    @property
    def translation_magnitude(self) -> float:
        """平移偏差模长 (mm)"""
        return float(np.sqrt(self.dX**2 + self.dY**2 + self.dZ**2))

    @property
    def rotation_magnitude(self) -> float:
        """旋转偏差模长 (°)"""
        return float(np.sqrt(self.dRx**2 + self.dRy**2 + self.dRz**2))


# ---------------------------------------------------------------------------
# 核心算法类
# ---------------------------------------------------------------------------

class LocalTemplate3D:
    """
    局部三维几何模板算法类。

    使用示例：
        algo = LocalTemplate3D()

        # 示教阶段：建立标准模板
        frame_std = algo.build_local_frame(roi1_cloud, roi2_cloud, roi3_cloud)
        template_dict = frame_std.to_dict()   # 序列化存入数据库

        # 生产阶段：计算补偿矩阵
        frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
        delta = algo.compute_delta_T(frame_std, frame_cur)
        # delta.dX, delta.dY, delta.dZ, delta.dRx, delta.dRy, delta.dRz → 发给PLC
    """

    def __init__(
        self,
        w1: float = 0.5,
        w3: float = 0.5,
        ransac_distance_threshold: float = 2.0,
        ransac_num_iterations: int = 1000,
        ransac_min_inliers: int = 50,
    ):
        """
        Args:
            w1: 区域1（上水平面）法向量权重
            w3: 区域3（下水平面）法向量权重
            ransac_distance_threshold: RANSAC 平面拟合距离阈值 (mm)
            ransac_num_iterations: RANSAC 迭代次数
            ransac_min_inliers: 最小内点数，低于此值拟合失败
        """
        self.w1 = w1
        self.w3 = w3
        self.ransac_distance_threshold = ransac_distance_threshold
        self.ransac_num_iterations = ransac_num_iterations
        self.ransac_min_inliers = ransac_min_inliers

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def build_local_frame(
        self,
        roi1_cloud: np.ndarray,
        roi2_cloud: np.ndarray,
        roi3_cloud: np.ndarray,
    ) -> LocalFrameResult:
        """
        从三个区域点云建立局部坐标系。

        Args:
            roi1_cloud: 区域1（上水平面）点云，shape (N, 3)，单位 mm
            roi2_cloud: 区域2（左竖直面）点云，shape (M, 3)，单位 mm
            roi3_cloud: 区域3（下水平面）点云，shape (K, 3)，单位 mm

        Returns:
            LocalFrameResult：包含 T(4x4)、三平面参数、局部坐标轴
        """
        # 1. 拟合三个平面
        plane1 = self._fit_plane(roi1_cloud, label="区域1(上水平面)")
        plane2 = self._fit_plane(roi2_cloud, label="区域2(左竖直面)")
        plane3 = self._fit_plane(roi3_cloud, label="区域3(下水平面)")

        # 2. 统一法向量方向（约定）
        #    - 区域1、3 法向量指向上方（Z+ 方向，即法向量 Z 分量 > 0）
        #    - 区域2 法向量指向料架内侧（X+ 方向，即法向量 X 分量 > 0）
        plane1.normal = self._ensure_direction(plane1.normal, reference=np.array([0, 0, 1.0]))
        plane3.normal = self._ensure_direction(plane3.normal, reference=np.array([0, 0, 1.0]))
        plane2.normal = self._ensure_direction(plane2.normal, reference=np.array([1, 0, 0.0]))

        # 3. 计算局部坐标轴
        z_local, x_local, y_local = self._compute_axes(plane1, plane2, plane3)

        # 4. 计算局部原点（三ROI点云合并质心，投影到区域2×区域3的交线上）
        origin = self._compute_origin(roi1_cloud, roi2_cloud, roi3_cloud, plane2, plane3)

        # 5. 构造 4x4 齐次变换矩阵
        #    局部坐标系相对于相机坐标系的变换：T = [R | t]
        R = np.column_stack([x_local, y_local, z_local])   # (3, 3)
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = origin

        logger.info(
            "局部坐标系建立完成 | origin=%.1f,%.1f,%.1f | "
            "plane1 inlier=%.1f%% | plane2 inlier=%.1f%% | plane3 inlier=%.1f%%",
            *origin,
            plane1.inlier_ratio * 100,
            plane2.inlier_ratio * 100,
            plane3.inlier_ratio * 100,
        )

        return LocalFrameResult(
            T=T,
            plane1=plane1,
            plane2=plane2,
            plane3=plane3,
            origin=origin,
            x_local=x_local,
            y_local=y_local,
            z_local=z_local,
        )

    def compute_delta_T(
        self,
        frame_std: LocalFrameResult,
        frame_cur: LocalFrameResult,
    ) -> DeltaTransformResult:
        """
        计算标准模板到当前模板的刚体变换矩阵。

        ΔT = T_cur @ inv(T_std)

        Args:
            frame_std: 示教阶段建立的标准局部坐标系
            frame_cur: 生产阶段建立的当前局部坐标系

        Returns:
            DeltaTransformResult：包含 ΔT(4x4) 和分解后的 6DoF 偏差量
        """
        T_std_inv = np.linalg.inv(frame_std.T)
        delta_T = frame_cur.T @ T_std_inv

        dX, dY, dZ, dRx, dRy, dRz = self._decompose_4x4(delta_T)

        logger.info(
            "刚体变换计算完成 | ΔX=%.2fmm ΔY=%.2fmm ΔZ=%.2fmm | "
            "ΔRx=%.3f° ΔRy=%.3f° ΔRz=%.3f°",
            dX, dY, dZ, dRx, dRy, dRz,
        )

        return DeltaTransformResult(
            delta_T=delta_T,
            dX=dX, dY=dY, dZ=dZ,
            dRx=dRx, dRy=dRy, dRz=dRz,
        )

    def compute_delta_T_from_dicts(
        self,
        std_dict: dict,
        roi1_cur: np.ndarray,
        roi2_cur: np.ndarray,
        roi3_cur: np.ndarray,
    ) -> Tuple[LocalFrameResult, DeltaTransformResult]:
        """
        便捷方法：从数据库存储的标准模板字典和当前点云直接计算 ΔT。

        Args:
            std_dict: 由 LocalFrameResult.to_dict() 序列化的标准模板字典
            roi1_cur, roi2_cur, roi3_cur: 当前三区域点云

        Returns:
            (frame_cur, delta_result) 元组
        """
        frame_std = LocalFrameResult.from_dict(std_dict)
        frame_cur = self.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
        delta = self.compute_delta_T(frame_std, frame_cur)
        return frame_cur, delta

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _fit_plane(self, cloud: np.ndarray, label: str = "") -> PlaneResult:
        """
        RANSAC 平面拟合。

        Args:
            cloud: 点云 (N, 3)
            label: 日志标签

        Returns:
            PlaneResult
        """
        if cloud is None or len(cloud) < self.ransac_min_inliers:
            raise ValueError(
                f"{label} 点云点数不足（{len(cloud) if cloud is not None else 0} < {self.ransac_min_inliers}）"
            )

        cloud = np.asarray(cloud, dtype=np.float64)
        centroid = cloud.mean(axis=0)

        # 尝试使用 open3d（更快更准）
        try:
            normal, offset, inlier_ratio = self._ransac_open3d(cloud)
        except Exception:
            # 降级到纯 numpy RANSAC
            normal, offset, inlier_ratio = self._ransac_numpy(cloud)

        logger.debug("%s 平面拟合 | normal=%s | offset=%.2f | inlier=%.1f%%",
                     label, np.round(normal, 3), offset, inlier_ratio * 100)

        if inlier_ratio < 0.3:
            logger.warning("%s 平面拟合内点率过低: %.1f%%", label, inlier_ratio * 100)

        return PlaneResult(
            normal=normal,
            offset=offset,
            centroid=centroid,
            inlier_ratio=inlier_ratio,
            point_count=len(cloud),
        )

    def _ransac_open3d(self, cloud: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """使用 open3d 进行 RANSAC 平面拟合"""
        import open3d as o3d  # 按需导入

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(cloud)

        plane_model, inliers = pcd.segment_plane(
            distance_threshold=self.ransac_distance_threshold,
            ransac_n=3,
            num_iterations=self.ransac_num_iterations,
        )
        a, b, c, d = plane_model
        normal = np.array([a, b, c], dtype=np.float64)
        norm = np.linalg.norm(normal)
        normal = normal / norm
        offset = d / norm
        inlier_ratio = len(inliers) / len(cloud)
        return normal, offset, inlier_ratio

    def _ransac_numpy(self, cloud: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """纯 numpy RANSAC 平面拟合（open3d 不可用时的备选方案）"""
        best_normal = None
        best_d = 0.0
        best_inliers = 0
        n = len(cloud)
        rng = np.random.default_rng(42)

        for _ in range(self.ransac_num_iterations):
            idx = rng.choice(n, 3, replace=False)
            p0, p1, p2 = cloud[idx]
            v1 = p1 - p0
            v2 = p2 - p0
            normal = np.cross(v1, v2)
            norm = np.linalg.norm(normal)
            if norm < 1e-10:
                continue
            normal = normal / norm
            d = -np.dot(normal, p0)
            distances = np.abs(cloud @ normal + d)
            inlier_count = int((distances < self.ransac_distance_threshold).sum())
            if inlier_count > best_inliers:
                best_inliers = inlier_count
                best_normal = normal
                best_d = d

        if best_normal is None:
            raise RuntimeError("RANSAC 平面拟合失败，无法找到有效平面")

        # 用所有内点重新最小二乘拟合
        distances = np.abs(cloud @ best_normal + best_d)
        inlier_mask = distances < self.ransac_distance_threshold
        inlier_cloud = cloud[inlier_mask]
        centroid = inlier_cloud.mean(axis=0)
        cov = (inlier_cloud - centroid).T @ (inlier_cloud - centroid)
        _, _, Vt = np.linalg.svd(cov)
        refined_normal = Vt[-1]
        refined_d = -np.dot(refined_normal, centroid)

        inlier_ratio = best_inliers / n
        return refined_normal, refined_d, inlier_ratio

    def _compute_axes(
        self,
        plane1: PlaneResult,
        plane2: PlaneResult,
        plane3: PlaneResult,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        从三平面法向量计算局部坐标轴（Z, X, Y）。

        Z_local = normalize(w1*n1 + w3*n3)
        X_local = normalize(n2 - (n2·Z_local)*Z_local)
        Y_local = Z_local × X_local
        """
        # Z 轴：上下水平面加权平均
        z_raw = self.w1 * plane1.normal + self.w3 * plane3.normal
        z_norm = np.linalg.norm(z_raw)
        if z_norm < 1e-8:
            raise RuntimeError("Z 轴计算失败：区域1与区域3法向量相互抵消，请检查点云方向")
        z_local = z_raw / z_norm

        # X 轴：竖直面法向量投影到与Z垂直的平面上
        n2 = plane2.normal
        x_raw = n2 - np.dot(n2, z_local) * z_local
        x_norm = np.linalg.norm(x_raw)
        if x_norm < 1e-8:
            raise RuntimeError("X 轴计算失败：区域2法向量与Z轴平行，无法建立正交坐标系")
        x_local = x_raw / x_norm

        # Y 轴：右手定则
        y_local = np.cross(z_local, x_local)
        y_local = y_local / np.linalg.norm(y_local)

        return z_local, x_local, y_local

    def _compute_origin(
        self,
        roi1_cloud: np.ndarray,
        roi2_cloud: np.ndarray,
        roi3_cloud: np.ndarray,
        plane2: PlaneResult,
        plane3: PlaneResult,
    ) -> np.ndarray:
        """
        计算局部坐标系原点。

        策略：
          1. 将三个ROI点云合并，计算总体质心作为初始原点估计
          2. 将质心投影到区域2（竖直面）和区域3（下水平面）的交线上，
             得到稳定的局部原点（消除切向滑动的影响）
        """
        # 合并三个区域点云
        all_points = np.vstack([roi1_cloud, roi2_cloud, roi3_cloud])
        centroid = all_points.mean(axis=0)

        # 将质心投影到区域2和区域3的交线上
        # 交线方向 = n2 × n3
        n2, d2 = plane2.normal, plane2.offset
        n3, d3 = plane3.normal, plane3.offset

        line_dir = np.cross(n2, n3)
        line_norm = np.linalg.norm(line_dir)

        if line_norm < 1e-6:
            # 两平面近似平行，退化为质心直接使用
            logger.warning("区域2与区域3近似平行，无法计算交线，使用点云质心作为原点")
            return centroid

        line_dir = line_dir / line_norm

        # 求交线上离质心最近的点（质心在交线上的投影）
        # 先求两平面方程组联立求一个交线上的特定点 P0
        # n2·P = -d2, n3·P = -d3，约束 line_dir·P = line_dir·centroid
        A = np.array([n2, n3, line_dir])
        b = np.array([-d2, -d3, np.dot(line_dir, centroid)])

        try:
            P0 = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            logger.warning("交线点计算失败，使用质心作为原点")
            return centroid

        # 质心投影到交线
        origin = P0 + np.dot(centroid - P0, line_dir) * line_dir
        return origin

    @staticmethod
    def _ensure_direction(normal: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """
        确保法向量与参考方向同向（点积 > 0），
        若反向则取反，保证方向一致性。
        """
        if np.dot(normal, reference) < 0:
            return -normal
        return normal

    @staticmethod
    def _decompose_4x4(T: np.ndarray) -> Tuple[float, float, float, float, float, float]:
        """
        将 4x4 齐次变换矩阵分解为 (dX, dY, dZ, dRx, dRy, dRz)。

        旋转顺序：固定轴 XYZ（等价于欧拉角 ZYX 内旋）。
        单位：mm 和 度(°)。
        """
        # 平移部分
        dX = float(T[0, 3])
        dY = float(T[1, 3])
        dZ = float(T[2, 3])

        # 旋转矩阵部分（固定轴 XYZ 欧拉角）
        R = T[:3, :3]

        # Ry = arcsin(-R[2,0])
        sy = -R[2, 0]
        sy = np.clip(sy, -1.0, 1.0)
        ry = np.arcsin(sy)

        if np.abs(np.cos(ry)) > 1e-6:
            rx = np.arctan2(R[2, 1], R[2, 2])
            rz = np.arctan2(R[1, 0], R[0, 0])
        else:
            # Gimbal lock：Rx 与 Rz 耦合
            rx = np.arctan2(-R[1, 2], R[1, 1])
            rz = 0.0

        dRx = float(np.degrees(rx))
        dRy = float(np.degrees(ry))
        dRz = float(np.degrees(rz))

        return dX, dY, dZ, dRx, dRy, dRz
