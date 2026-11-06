"""Read saved positioning history without importing retired algorithms."""
import numpy as np
from typing import Dict, Optional
from .models import RackLocationResult

class RackPositionHistory:
    def get_positioning_history(
        self,
        recipe_id: int,
        layer_no: Optional[int] = None,
        limit: int = 10
    ) -> list:
        """
        获取定位历史记录
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号（可选）
            limit: 返回记录数
            
        Returns:
            定位结果列表
        """
        queryset = RackLocationResult.objects.filter(
            recipe_id=recipe_id
        ).order_by('-created_at')
        
        if layer_no is not None:
            queryset = queryset.filter(layer_no=layer_no)
        
        return list(queryset[:limit])

    def get_average_offsets(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 10
    ) -> Dict:
        """
        获取最近N次的平均偏移值
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            平均偏移值
        """
        results = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no,
            is_success=True
        ).order_by('-created_at')[:count]
        
        if not results:
            return {
                'count': 0,
                'avg_offset_x': 0,
                'avg_offset_y': 0,
                'avg_offset_z': 0,
                'std_offset_x': 0,
                'std_offset_y': 0,
                'std_offset_z': 0
            }
        
        # 计算平均值和标准差
        offsets_x = [float(r.offset_x) for r in results]
        offsets_y = [float(r.offset_y) for r in results]
        offsets_z = [float(r.offset_z) for r in results]
        
        return {
            'count': len(results),
            'avg_offset_x': float(np.mean(offsets_x)),
            'avg_offset_y': float(np.mean(offsets_y)),
            'avg_offset_z': float(np.mean(offsets_z)),
            'std_offset_x': float(np.std(offsets_x)),
            'std_offset_y': float(np.std(offsets_y)),
            'std_offset_z': float(np.std(offsets_z))
        }

    def analyze_positioning_stability(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 20
    ) -> Dict:
        """
        分析定位稳定性
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            稳定性分析结果
        """
        results = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no,
            is_success=True
        ).order_by('-created_at')[:count]
        
        if len(results) < 5:
            return {
                'sufficient_data': False,
                'message': '数据不足，需要至少5次成功定位记录'
            }
        
        # 提取数据
        offsets_x = np.array([float(r.offset_x) for r in results])
        offsets_y = np.array([float(r.offset_y) for r in results])
        offsets_z = np.array([float(r.offset_z) for r in results])
        confidences = np.array([float(r.confidence) for r in results])
        
        # 计算统计指标
        return {
            'sufficient_data': True,
            'sample_count': len(results),
            
            # X轴稳定性
            'x_mean': float(np.mean(offsets_x)),
            'x_std': float(np.std(offsets_x)),
            'x_range': float(np.ptp(offsets_x)),  # 极差
            'x_cv': float(np.std(offsets_x) / (np.mean(np.abs(offsets_x)) + 1e-6)),  # 变异系数
            
            # Y轴稳定性
            'y_mean': float(np.mean(offsets_y)),
            'y_std': float(np.std(offsets_y)),
            'y_range': float(np.ptp(offsets_y)),
            'y_cv': float(np.std(offsets_y) / (np.mean(np.abs(offsets_y)) + 1e-6)),
            
            # Z轴稳定性
            'z_mean': float(np.mean(offsets_z)),
            'z_std': float(np.std(offsets_z)),
            'z_range': float(np.ptp(offsets_z)),
            'z_cv': float(np.std(offsets_z) / (np.mean(np.abs(offsets_z)) + 1e-6)),
            
            # 整体置信度
            'avg_confidence': float(np.mean(confidences)),
            'min_confidence': float(np.min(confidences)),
            
            # 稳定性评级（基于标准差）
            'stability_rating': self._calculate_stability_rating(
                np.std(offsets_x),
                np.std(offsets_y),
                np.std(offsets_z)
            )
        }

    def _calculate_stability_rating(
        self,
        std_x: float,
        std_y: float,
        std_z: float
    ) -> str:
        """
        计算稳定性评级
        
        Args:
            std_x, std_y, std_z: 各轴标准差
            
        Returns:
            评级字符串
        """
        # 阈值定义（mm）
        excellent_threshold = 1.0
        good_threshold = 2.0
        fair_threshold = 5.0
        
        max_std = max(std_x, std_y, std_z)
        
        if max_std < excellent_threshold:
            return 'EXCELLENT'  # 优秀
        elif max_std < good_threshold:
            return 'GOOD'       # 良好
        elif max_std < fair_threshold:
            return 'FAIR'       # 一般
        else:
            return 'POOR'       # 较差
