"""
料架定位算法模块

提取每层刚性基准，计算X/Y/Z偏移

核心算法：
1. 找Z - 识别层板/支撑面平面（RANSAC平面拟合）
2. 找Y - 识别前边缘/横梁边缘（梯度边缘检测）
3. 找X - 识别立柱/侧边缘（垂直边缘检测）
"""
import numpy as np
import logging
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False
    logging.warning("Open3D not available. 3D point cloud processing will be limited.")

logger = logging.getLogger(__name__)


@dataclass
class PlaneDetectionResult:
    """平面检测结果"""
    plane_model: np.ndarray  # [a, b, c, d] - 平面方程 ax + by + cz + d = 0
    inliers: np.ndarray      # 内点索引
    inlier_cloud: np.ndarray # 内点点云
    z_position: float        # Z轴位置（平面平均高度）
    z_std: float            # Z轴标准差
    confidence: float        # 置信度


@dataclass
class EdgeDetectionResult:
    """边缘检测结果"""
    edge_points: np.ndarray  # 边缘点坐标
    edge_line: np.ndarray    # 边缘线参数 [点, 方向向量]
    y_position: float        # Y轴位置（边缘位置）
    y_std: float            # Y轴标准差
    confidence: float        # 置信度


@dataclass
class PillarDetectionResult:
    """立柱检测结果"""
    pillar_points: np.ndarray  # 立柱点坐标
    pillar_line: np.ndarray    # 立柱线参数 [点, 方向向量]
    x_position: float          # X轴位置（立柱位置）
    x_std: float              # X轴标准差
    confidence: float          # 置信度


@dataclass
class RackPositioningResult:
    """料架定位结果"""
    # 实际测量值
    actual_x: float
    actual_y: float
    actual_z: float
    
    # 标准理论值
    standard_x: float
    standard_y: float
    standard_z: float
    
    # 偏移值（补偿值）
    offset_x: float  # 实际 - 标准
    offset_y: float
    offset_z: float
    
    # 置信度
    confidence_x: float
    confidence_y: float
    confidence_z: float
    
    # 详细结果
    plane_result: Optional[PlaneDetectionResult] = None
    edge_result: Optional[EdgeDetectionResult] = None
    pillar_result: Optional[PillarDetectionResult] = None
    
    # 是否成功
    is_success: bool = True
    error_message: str = ""


class RackPositioningAlgorithm:
    """料架定位算法"""
    
    def __init__(self):
        """初始化算法"""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    # ========== 1. 找Z：平面检测 ==========
    
    def detect_support_plane(
        self,
        pointcloud: np.ndarray,
        distance_threshold: float = 2.0,
        ransac_n: int = 3,
        num_iterations: int = 1000,
        min_inliers: int = 100
    ) -> PlaneDetectionResult:
        """
        检测支撑面平面，计算Z轴位置
        
        使用RANSAC算法拟合平面，提取支撑面的平均高度
        
        Args:
            pointcloud: 点云数据 (N, 3) [x, y, z]
            distance_threshold: RANSAC距离阈值（mm）
            ransac_n: RANSAC最小点数
            num_iterations: RANSAC迭代次数
            min_inliers: 最小内点数
            
        Returns:
            PlaneDetectionResult: 平面检测结果
        """
        if pointcloud.shape[0] < min_inliers:
            raise ValueError(f"点云点数({pointcloud.shape[0]})少于最小要求({min_inliers})")
        
        # 方法1: 使用Open3D的RANSAC平面拟合（推荐）
        if OPEN3D_AVAILABLE:
            return self._detect_plane_open3d(
                pointcloud, distance_threshold, ransac_n, num_iterations, min_inliers
            )
        else:
            # 方法2: 使用NumPy的简化版RANSAC
            return self._detect_plane_numpy(
                pointcloud, distance_threshold, num_iterations, min_inliers
            )
    
    def _detect_plane_open3d(
        self,
        pointcloud: np.ndarray,
        distance_threshold: float,
        ransac_n: int,
        num_iterations: int,
        min_inliers: int
    ) -> PlaneDetectionResult:
        """使用Open3D进行平面检测"""
        # 创建Open3D点云对象
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pointcloud)
        
        # RANSAC平面分割
        plane_model, inliers = pcd.segment_plane(
            distance_threshold=distance_threshold,
            ransac_n=ransac_n,
            num_iterations=num_iterations
        )
        
        if len(inliers) < min_inliers:
            raise ValueError(f"平面内点数({len(inliers)})少于最小要求({min_inliers})")
        
        # 提取内点
        inlier_cloud = pointcloud[inliers]
        
        # 计算平面平均高度（Z坐标）
        z_position = float(np.mean(inlier_cloud[:, 2]))
        z_std = float(np.std(inlier_cloud[:, 2]))
        
        # 计算置信度（基于内点比例和Z标准差）
        inlier_ratio = len(inliers) / pointcloud.shape[0]
        confidence = min(1.0, inlier_ratio * (1.0 - min(z_std / 10.0, 0.5)))
        
        self.logger.info(
            f"平面检测: {len(inliers)}/{pointcloud.shape[0]} 内点, "
            f"Z={z_position:.2f}±{z_std:.2f}mm, 置信度={confidence:.3f}"
        )
        
        return PlaneDetectionResult(
            plane_model=np.array(plane_model),
            inliers=np.array(inliers),
            inlier_cloud=inlier_cloud,
            z_position=z_position,
            z_std=z_std,
            confidence=confidence
        )
    
    def _detect_plane_numpy(
        self,
        pointcloud: np.ndarray,
        distance_threshold: float,
        num_iterations: int,
        min_inliers: int
    ) -> PlaneDetectionResult:
        """使用NumPy实现简化的RANSAC平面检测"""
        best_plane = None
        best_inliers = None
        best_score = 0

        # 【Bug 修复】使用本地固定种子 RNG，避免全局 np.random 状态污染导致每次结果不同。
        # 原代码使用全局 np.random.choice，受进程中其他随机操作影响，结果不可复现。
        rng = np.random.default_rng(42)

        for _ in range(num_iterations):
            # 随机选择3个点
            sample_indices = rng.choice(pointcloud.shape[0], 3, replace=False)
            sample_points = pointcloud[sample_indices]
            
            # 计算平面方程 ax + by + cz + d = 0
            # 使用两个向量的叉积得到法向量
            v1 = sample_points[1] - sample_points[0]
            v2 = sample_points[2] - sample_points[0]
            normal = np.cross(v1, v2)
            
            # 归一化法向量
            normal_length = np.linalg.norm(normal)
            if normal_length < 1e-6:
                continue
            normal = normal / normal_length
            
            # 计算d
            d = -np.dot(normal, sample_points[0])
            plane_model = np.append(normal, d)
            
            # 计算所有点到平面的距离
            distances = np.abs(
                pointcloud[:, 0] * plane_model[0] +
                pointcloud[:, 1] * plane_model[1] +
                pointcloud[:, 2] * plane_model[2] +
                plane_model[3]
            )
            
            # 找到内点
            inliers = np.where(distances < distance_threshold)[0]
            
            # 评分（内点数量）
            score = len(inliers)
            
            if score > best_score:
                best_score = score
                best_plane = plane_model
                best_inliers = inliers
        
        if best_inliers is None or len(best_inliers) < min_inliers:
            raise ValueError(f"平面检测失败，内点数({len(best_inliers) if best_inliers is not None else 0})不足")
        
        # 提取内点
        inlier_cloud = pointcloud[best_inliers]
        
        # 计算平面平均高度
        z_position = float(np.mean(inlier_cloud[:, 2]))
        z_std = float(np.std(inlier_cloud[:, 2]))
        
        # 计算置信度
        inlier_ratio = len(best_inliers) / pointcloud.shape[0]
        confidence = min(1.0, inlier_ratio * (1.0 - min(z_std / 10.0, 0.5)))
        
        self.logger.info(
            f"平面检测(NumPy): {len(best_inliers)}/{pointcloud.shape[0]} 内点, "
            f"Z={z_position:.2f}±{z_std:.2f}mm, 置信度={confidence:.3f}"
        )
        
        return PlaneDetectionResult(
            plane_model=best_plane,
            inliers=best_inliers,
            inlier_cloud=inlier_cloud,
            z_position=z_position,
            z_std=z_std,
            confidence=confidence
        )
    
    # ========== 2. 找Y：前边缘检测 ==========
    
    def detect_front_edge(
        self,
        pointcloud: np.ndarray,
        gradient_threshold: float = 50.0,
        min_edge_points: int = 50,
        bin_size: float = 5.0
    ) -> EdgeDetectionResult:
        """
        检测前边缘，计算Y轴位置
        
        通过Y方向的梯度变化检测边缘
        
        Args:
            pointcloud: 点云数据 (N, 3) [x, y, z]
            gradient_threshold: 梯度阈值（用于判断边缘）
            min_edge_points: 最小边缘点数
            bin_size: 分箱大小（mm）
            
        Returns:
            EdgeDetectionResult: 边缘检测结果
        """
        if pointcloud.shape[0] < min_edge_points:
            raise ValueError(f"点云点数({pointcloud.shape[0]})少于最小要求({min_edge_points})")
        
        # 按Y方向分箱统计点密度
        y_coords = pointcloud[:, 1]
        y_min, y_max = y_coords.min(), y_coords.max()
        
        # 创建分箱
        bins = np.arange(y_min, y_max + bin_size, bin_size)
        hist, bin_edges = np.histogram(y_coords, bins=bins)
        
        # 计算梯度（密度变化率）
        gradient = np.gradient(hist.astype(float))
        
        # 找到梯度最大的位置（边缘）
        # 前边缘通常是从少到多（正梯度）或从多到少（负梯度）
        abs_gradient = np.abs(gradient)
        
        if abs_gradient.max() < gradient_threshold:
            raise ValueError(f"未检测到明显边缘，最大梯度={abs_gradient.max():.1f}")
        
        # 找到梯度最大的bin
        edge_bin_idx = np.argmax(abs_gradient)
        edge_y = (bin_edges[edge_bin_idx] + bin_edges[edge_bin_idx + 1]) / 2
        
        # 提取边缘附近的点
        edge_tolerance = bin_size * 2
        edge_mask = np.abs(y_coords - edge_y) < edge_tolerance
        edge_points = pointcloud[edge_mask]
        
        if edge_points.shape[0] < min_edge_points:
            raise ValueError(f"边缘点数({edge_points.shape[0]})不足")
        
        # 计算Y位置和标准差
        y_position = float(np.mean(edge_points[:, 1]))
        y_std = float(np.std(edge_points[:, 1]))
        
        # 拟合边缘线（使用PCA找主方向）
        edge_center = edge_points.mean(axis=0)
        edge_centered = edge_points - edge_center
        
        # PCA：找主方向（应该是X方向）
        cov_matrix = np.cov(edge_centered.T)
        eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
        # 主方向是最大特征值对应的特征向量
        main_direction = eigenvectors[:, np.argmax(eigenvalues)]
        
        edge_line = np.vstack([edge_center, main_direction])
        
        # 计算置信度（基于边缘点数和Y标准差）
        point_ratio = edge_points.shape[0] / pointcloud.shape[0]
        confidence = min(1.0, point_ratio * 2.0 * (1.0 - min(y_std / 20.0, 0.5)))
        
        self.logger.info(
            f"前边缘检测: {edge_points.shape[0]} 边缘点, "
            f"Y={y_position:.2f}±{y_std:.2f}mm, 置信度={confidence:.3f}"
        )
        
        return EdgeDetectionResult(
            edge_points=edge_points,
            edge_line=edge_line,
            y_position=y_position,
            y_std=y_std,
            confidence=confidence
        )
    
    # ========== 3. 找X：立柱检测 ==========
    
    def detect_pillar(
        self,
        pointcloud: np.ndarray,
        vertical_tolerance: float = 10.0,
        min_pillar_points: int = 50,
        bin_size: float = 5.0
    ) -> PillarDetectionResult:
        """
        检测立柱/侧边，计算X轴位置
        
        通过X方向的密度变化检测垂直立柱
        
        Args:
            pointcloud: 点云数据 (N, 3) [x, y, z]
            vertical_tolerance: 垂直度容差（度）
            min_pillar_points: 最小立柱点数
            bin_size: 分箱大小（mm）
            
        Returns:
            PillarDetectionResult: 立柱检测结果
        """
        if pointcloud.shape[0] < min_pillar_points:
            raise ValueError(f"点云点数({pointcloud.shape[0]})少于最小要求({min_pillar_points})")
        
        # 按X方向分箱统计点密度
        x_coords = pointcloud[:, 0]
        x_min, x_max = x_coords.min(), x_coords.max()
        
        # 创建分箱
        bins = np.arange(x_min, x_max + bin_size, bin_size)
        hist, bin_edges = np.histogram(x_coords, bins=bins)
        
        # 计算梯度（密度变化率）
        gradient = np.gradient(hist.astype(float))
        abs_gradient = np.abs(gradient)
        
        # 找到梯度最大的位置（立柱边缘）
        if abs_gradient.max() < 10:  # 梯度阈值
            raise ValueError(f"未检测到明显立柱边缘，最大梯度={abs_gradient.max():.1f}")
        
        # 找到梯度最大的bin
        pillar_bin_idx = np.argmax(abs_gradient)
        pillar_x = (bin_edges[pillar_bin_idx] + bin_edges[pillar_bin_idx + 1]) / 2
        
        # 提取立柱附近的点
        pillar_tolerance = bin_size * 3
        pillar_mask = np.abs(x_coords - pillar_x) < pillar_tolerance
        pillar_points = pointcloud[pillar_mask]
        
        if pillar_points.shape[0] < min_pillar_points:
            raise ValueError(f"立柱点数({pillar_points.shape[0]})不足")
        
        # 计算X位置和标准差
        x_position = float(np.mean(pillar_points[:, 0]))
        x_std = float(np.std(pillar_points[:, 0]))
        
        # 拟合立柱线（垂直线）
        pillar_center = pillar_points.mean(axis=0)
        pillar_centered = pillar_points - pillar_center
        
        # PCA：找主方向（应该是Z方向，垂直）
        cov_matrix = np.cov(pillar_centered.T)
        eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
        # 主方向是最大特征值对应的特征向量
        main_direction = eigenvectors[:, np.argmax(eigenvalues)]
        
        # 检查垂直度（主方向应该接近[0, 0, 1]）
        vertical_vector = np.array([0, 0, 1])
        angle = np.arccos(np.abs(np.dot(main_direction, vertical_vector))) * 180 / np.pi
        
        pillar_line = np.vstack([pillar_center, main_direction])
        
        # 计算置信度
        point_ratio = pillar_points.shape[0] / pointcloud.shape[0]
        vertical_score = 1.0 - min(angle / vertical_tolerance, 1.0)
        confidence = min(1.0, point_ratio * 3.0 * (vertical_score + 0.5) * (1.0 - min(x_std / 20.0, 0.5)))
        
        self.logger.info(
            f"立柱检测: {pillar_points.shape[0]} 立柱点, "
            f"X={x_position:.2f}±{x_std:.2f}mm, "
            f"垂直度={angle:.1f}°, 置信度={confidence:.3f}"
        )
        
        return PillarDetectionResult(
            pillar_points=pillar_points,
            pillar_line=pillar_line,
            x_position=x_position,
            x_std=x_std,
            confidence=confidence
        )
    
    # ========== 4. 综合定位计算 ==========
    
    def calculate_rack_position(
        self,
        support_plane_cloud: np.ndarray,
        front_edge_cloud: np.ndarray,
        pillar_cloud: np.ndarray,
        standard_x: float,
        standard_y: float,
        standard_z: float,
        plane_params: Optional[Dict] = None,
        edge_params: Optional[Dict] = None,
        pillar_params: Optional[Dict] = None
    ) -> RackPositioningResult:
        """
        综合计算料架定位结果
        
        Args:
            support_plane_cloud: 支撑面点云
            front_edge_cloud: 前边缘点云
            pillar_cloud: 立柱点云
            standard_x: 标准X位置
            standard_y: 标准Y位置
            standard_z: 标准Z位置
            plane_params: 平面检测参数
            edge_params: 边缘检测参数
            pillar_params: 立柱检测参数
            
        Returns:
            RackPositioningResult: 定位结果
        """
        plane_params = plane_params or {}
        edge_params = edge_params or {}
        pillar_params = pillar_params or {}
        
        result = RackPositioningResult(
            actual_x=0, actual_y=0, actual_z=0,
            standard_x=standard_x,
            standard_y=standard_y,
            standard_z=standard_z,
            offset_x=0, offset_y=0, offset_z=0,
            confidence_x=0, confidence_y=0, confidence_z=0
        )
        
        try:
            # 1. 检测支撑面平面 → Z
            if support_plane_cloud.shape[0] > 0:
                try:
                    plane_result = self.detect_support_plane(support_plane_cloud, **plane_params)
                    result.plane_result = plane_result
                    result.actual_z = plane_result.z_position
                    result.offset_z = result.actual_z - standard_z
                    result.confidence_z = plane_result.confidence
                    self.logger.info(f"✓ Z轴定位: 实际={result.actual_z:.2f}mm, 偏移={result.offset_z:.2f}mm")
                except Exception as e:
                    self.logger.warning(f"Z轴检测失败: {e}")
                    result.confidence_z = 0
            
            # 2. 检测前边缘 → Y
            if front_edge_cloud.shape[0] > 0:
                try:
                    edge_result = self.detect_front_edge(front_edge_cloud, **edge_params)
                    result.edge_result = edge_result
                    result.actual_y = edge_result.y_position
                    result.offset_y = result.actual_y - standard_y
                    result.confidence_y = edge_result.confidence
                    self.logger.info(f"✓ Y轴定位: 实际={result.actual_y:.2f}mm, 偏移={result.offset_y:.2f}mm")
                except Exception as e:
                    self.logger.warning(f"Y轴检测失败: {e}")
                    result.confidence_y = 0
            
            # 3. 检测立柱 → X
            if pillar_cloud.shape[0] > 0:
                try:
                    pillar_result = self.detect_pillar(pillar_cloud, **pillar_params)
                    result.pillar_result = pillar_result
                    result.actual_x = pillar_result.x_position
                    result.offset_x = result.actual_x - standard_x
                    result.confidence_x = pillar_result.confidence
                    self.logger.info(f"✓ X轴定位: 实际={result.actual_x:.2f}mm, 偏移={result.offset_x:.2f}mm")
                except Exception as e:
                    self.logger.warning(f"X轴检测失败: {e}")
                    result.confidence_x = 0
            
            # 判断定位是否成功
            min_confidence = 0.3
            result.is_success = (
                result.confidence_x >= min_confidence and
                result.confidence_y >= min_confidence and
                result.confidence_z >= min_confidence
            )
            
            if not result.is_success:
                result.error_message = (
                    f"定位置信度不足: "
                    f"X={result.confidence_x:.2f}, "
                    f"Y={result.confidence_y:.2f}, "
                    f"Z={result.confidence_z:.2f}"
                )
            
        except Exception as e:
            self.logger.exception("料架定位计算失败")
            result.is_success = False
            result.error_message = str(e)
        
        return result
    
    def to_dict(self, result: RackPositioningResult) -> Dict:
        """将定位结果转换为字典格式"""
        return {
            'is_success': result.is_success,
            'error_message': result.error_message,
            
            # 实际测量值
            'actual_x': float(result.actual_x),
            'actual_y': float(result.actual_y),
            'actual_z': float(result.actual_z),
            
            # 标准理论值
            'standard_x': float(result.standard_x),
            'standard_y': float(result.standard_y),
            'standard_z': float(result.standard_z),
            
            # 偏移值（补偿值）
            'offset_x': float(result.offset_x),
            'offset_y': float(result.offset_y),
            'offset_z': float(result.offset_z),
            
            # 置信度
            'confidence_x': float(result.confidence_x),
            'confidence_y': float(result.confidence_y),
            'confidence_z': float(result.confidence_z),
            
            # 详细结果
            'plane_result': {
                'z_position': float(result.plane_result.z_position),
                'z_std': float(result.plane_result.z_std),
                'inliers_count': int(result.plane_result.inliers.shape[0]),
                'confidence': float(result.plane_result.confidence)
            } if result.plane_result else None,
            
            'edge_result': {
                'y_position': float(result.edge_result.y_position),
                'y_std': float(result.edge_result.y_std),
                'edge_points_count': int(result.edge_result.edge_points.shape[0]),
                'confidence': float(result.edge_result.confidence)
            } if result.edge_result else None,
            
            'pillar_result': {
                'x_position': float(result.pillar_result.x_position),
                'x_std': float(result.pillar_result.x_std),
                'pillar_points_count': int(result.pillar_result.pillar_points.shape[0]),
                'confidence': float(result.pillar_result.confidence)
            } if result.pillar_result else None,
        }
