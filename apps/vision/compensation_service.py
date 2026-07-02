"""
补偿值服务

提供补偿值计算、保存、历史查询等业务逻辑
"""
import logging
from typing import Dict, Optional, List
from django.db import transaction
from decimal import Decimal

from .compensation_calculator import (
    CompensationCalculator,
    CompensationRule,
    CompensationData,
    OffsetData,
    CompensationValidator
)
from .models import RackLocationRecipe, RackLocationResult
from apps.core.constants import RackSide

logger = logging.getLogger(__name__)


class CompensationService:
    """补偿值服务"""
    
    def __init__(self, rule: Optional[CompensationRule] = None):
        """
        初始化服务
        
        Args:
            rule: 补偿规则（可选）
        """
        self.calculator = CompensationCalculator(rule)
        self.validator = CompensationValidator()
    
    def calculate_and_save_compensation(
        self,
        result_id: int,
        rack_side: Optional[str] = None,
        offset_rz: float = 0.0,
        save_to_result: bool = True
    ) -> CompensationData:
        """
        从定位结果计算补偿值并保存
        
        Args:
            result_id: RackLocationResult ID
            rack_side: 料架侧面（可选，从结果记录读取）
            offset_rz: RZ轴偏移（可选）
            save_to_result: 是否保存到结果记录
            
        Returns:
            CompensationData: 补偿值数据
        """
        # 获取定位结果
        result = RackLocationResult.objects.get(id=result_id)
        
        # 使用结果中的侧面信息
        if rack_side is None:
            rack_side = result.side
        
        # 创建偏移值数据
        offset_data = OffsetData(
            offset_x=float(result.offset_x),
            offset_y=float(result.offset_y),
            offset_z=float(result.offset_z),
            confidence_x=result.result_data.get('confidence_x', float(result.confidence)),
            confidence_y=result.result_data.get('confidence_y', float(result.confidence)),
            confidence_z=result.result_data.get('confidence_z', float(result.confidence))
        )
        
        # 计算补偿值
        compensation = self.calculator.calculate_compensation_from_offset_data(
            offset_data=offset_data,
            rack_side=rack_side,
            offset_rz=offset_rz
        )
        
        # 保存到结果记录
        if save_to_result:
            self._save_compensation_to_result(result, compensation)
        
        logger.info(
            f"补偿值已计算: 结果ID={result_id}, "
            f"X={compensation.compensation_x:.2f}mm, "
            f"Y={compensation.compensation_y:.2f}mm, "
            f"Z={compensation.compensation_z:.2f}mm"
        )
        
        return compensation
    
    @transaction.atomic
    def _save_compensation_to_result(
        self,
        result: RackLocationResult,
        compensation: CompensationData
    ):
        """
        将补偿值保存到结果记录
        
        Args:
            result: 定位结果记录
            compensation: 补偿值数据
        """
        # 更新result_data字段
        if not result.result_data:
            result.result_data = {}
        
        result.result_data['compensation'] = {
            'compensation_x': compensation.compensation_x,
            'compensation_y': compensation.compensation_y,
            'compensation_z': compensation.compensation_z,
            'compensation_rz': compensation.compensation_rz,
            'is_valid': compensation.is_valid,
            'validation_message': compensation.validation_message
        }
        
        result.save(update_fields=['result_data'])
        
        logger.debug(f"补偿值已保存到结果ID={result.id}")
    
    def calculate_compensation_from_positioning_result(
        self,
        positioning_result,  # RackPositioningResult
        rack_side: str = RackSide.BOTH,
        offset_rz: float = 0.0
    ) -> CompensationData:
        """
        从定位算法结果直接计算补偿值
        
        Args:
            positioning_result: 定位算法结果对象
            rack_side: 料架侧面
            offset_rz: RZ轴偏移
            
        Returns:
            CompensationData: 补偿值数据
        """
        offset_data = OffsetData(
            offset_x=positioning_result.offset_x,
            offset_y=positioning_result.offset_y,
            offset_z=positioning_result.offset_z,
            confidence_x=positioning_result.confidence_x,
            confidence_y=positioning_result.confidence_y,
            confidence_z=positioning_result.confidence_z
        )
        
        return self.calculator.calculate_compensation_from_offset_data(
            offset_data=offset_data,
            rack_side=rack_side,
            offset_rz=offset_rz
        )
    
    def get_compensation_from_result(self, result_id: int) -> Optional[Dict]:
        """
        从结果记录读取补偿值
        
        Args:
            result_id: 结果ID
            
        Returns:
            补偿值字典，如果不存在返回None
        """
        try:
            result = RackLocationResult.objects.get(id=result_id)
            
            if result.result_data and 'compensation' in result.result_data:
                return result.result_data['compensation']
            
            return None
        
        except RackLocationResult.DoesNotExist:
            return None
    
    def get_latest_compensation(
        self,
        recipe_id: int,
        layer_no: int,
        limit: int = 1
    ) -> List[Dict]:
        """
        获取最新的补偿值
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            limit: 返回数量
            
        Returns:
            补偿值列表
        """
        results = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            layer_no=layer_no,
            is_success=True
        ).order_by('-created_at')[:limit]
        
        compensations = []
        
        for result in results:
            comp = self.get_compensation_from_result(result.id)
            if comp:
                comp['result_id'] = result.id
                comp['created_at'] = result.created_at.isoformat()
                compensations.append(comp)
        
        return compensations
    
    def get_average_compensation(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 10
    ) -> Dict:
        """
        获取平均补偿值
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            平均补偿值字典
        """
        import numpy as np
        
        compensations = self.get_latest_compensation(recipe_id, layer_no, limit=count)
        
        if not compensations:
            return {
                'count': 0,
                'avg_compensation_x': 0,
                'avg_compensation_y': 0,
                'avg_compensation_z': 0,
                'std_compensation_x': 0,
                'std_compensation_y': 0,
                'std_compensation_z': 0
            }
        
        # 提取补偿值
        comp_x = [c['compensation_x'] for c in compensations]
        comp_y = [c['compensation_y'] for c in compensations]
        comp_z = [c['compensation_z'] for c in compensations]
        
        return {
            'count': len(compensations),
            'avg_compensation_x': float(np.mean(comp_x)),
            'avg_compensation_y': float(np.mean(comp_y)),
            'avg_compensation_z': float(np.mean(comp_z)),
            'std_compensation_x': float(np.std(comp_x)),
            'std_compensation_y': float(np.std(comp_y)),
            'std_compensation_z': float(np.std(comp_z))
        }
    
    def validate_compensation_value(
        self,
        compensation: CompensationData,
        strict: bool = False
    ) -> tuple:
        """
        验证补偿值
        
        Args:
            compensation: 补偿值数据
            strict: 是否严格模式
            
        Returns:
            (是否有效, 验证消息)
        """
        return self.validator.validate_compensation(compensation, strict)
    
    def prepare_plc_data(
        self,
        compensation: CompensationData,
        layer_no: int,
        additional_data: Optional[Dict] = None
    ) -> Dict:
        """
        准备PLC数据
        
        Args:
            compensation: 补偿值数据
            layer_no: 层号
            additional_data: 附加数据（可选）
            
        Returns:
            PLC数据字典
        """
        plc_data = self.calculator.to_plc_format(compensation)
        
        # 添加层号
        plc_data['layer_no'] = layer_no
        
        # 添加附加数据
        if additional_data:
            plc_data.update(additional_data)
        
        logger.info(f"PLC数据已准备: 层={layer_no}, X={plc_data['x']}, Y={plc_data['y']}, Z={plc_data['z']}")
        
        return plc_data
    
    def batch_calculate_compensations_for_recipe(
        self,
        recipe_id: int,
        layers: Optional[List[int]] = None
    ) -> Dict[int, CompensationData]:
        """
        批量计算配方所有层的补偿值
        
        Args:
            recipe_id: 配方ID
            layers: 层号列表（可选，默认为配方的所有层）
            
        Returns:
            {layer_no: CompensationData}
        """
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        
        if layers is None:
            layers = list(range(1, recipe.layer_count + 1))
        
        compensations = {}
        
        for layer_no in layers:
            # 获取该层最新的定位结果
            latest_result = RackLocationResult.objects.filter(
                recipe_id=recipe_id,
                layer_no=layer_no,
                is_success=True
            ).order_by('-created_at').first()
            
            if latest_result:
                compensation = self.calculate_and_save_compensation(
                    result_id=latest_result.id,
                    save_to_result=True
                )
                compensations[layer_no] = compensation
            else:
                logger.warning(f"配方ID={recipe_id} 第{layer_no}层无定位结果")
        
        logger.info(f"批量计算完成: 配方ID={recipe_id}, {len(compensations)}个层")
        
        return compensations
    
    def get_compensation_statistics(
        self,
        recipe_id: int,
        layer_no: int,
        count: int = 20
    ) -> Dict:
        """
        获取补偿值统计信息
        
        Args:
            recipe_id: 配方ID
            layer_no: 层号
            count: 统计数量
            
        Returns:
            统计信息字典
        """
        import numpy as np
        
        compensations = self.get_latest_compensation(recipe_id, layer_no, limit=count)
        
        if len(compensations) < 5:
            return {
                'sufficient_data': False,
                'message': '数据不足，需要至少5次补偿记录'
            }
        
        # 提取数据
        comp_x = np.array([c['compensation_x'] for c in compensations])
        comp_y = np.array([c['compensation_y'] for c in compensations])
        comp_z = np.array([c['compensation_z'] for c in compensations])
        valid_flags = np.array([c['is_valid'] for c in compensations])
        
        # 计算统计指标
        return {
            'sufficient_data': True,
            'sample_count': len(compensations),
            'valid_count': int(valid_flags.sum()),
            'valid_rate': float(valid_flags.mean()),
            
            # X轴统计
            'x_mean': float(comp_x.mean()),
            'x_std': float(comp_x.std()),
            'x_min': float(comp_x.min()),
            'x_max': float(comp_x.max()),
            'x_range': float(comp_x.ptp()),
            
            # Y轴统计
            'y_mean': float(comp_y.mean()),
            'y_std': float(comp_y.std()),
            'y_min': float(comp_y.min()),
            'y_max': float(comp_y.max()),
            'y_range': float(comp_y.ptp()),
            
            # Z轴统计
            'z_mean': float(comp_z.mean()),
            'z_std': float(comp_z.std()),
            'z_min': float(comp_z.min()),
            'z_max': float(comp_z.max()),
            'z_range': float(comp_z.ptp()),
            
            # 稳定性评级
            'stability_rating': self._calculate_stability_rating(
                comp_x.std(), comp_y.std(), comp_z.std()
            )
        }
    
    def _calculate_stability_rating(
        self,
        std_x: float,
        std_y: float,
        std_z: float
    ) -> str:
        """计算稳定性评级"""
        excellent_threshold = 2.0
        good_threshold = 5.0
        fair_threshold = 10.0
        
        max_std = max(std_x, std_y, std_z)
        
        if max_std < excellent_threshold:
            return 'EXCELLENT'
        elif max_std < good_threshold:
            return 'GOOD'
        elif max_std < fair_threshold:
            return 'FAIR'
        else:
            return 'POOR'
