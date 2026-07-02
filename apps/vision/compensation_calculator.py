"""
补偿值计算模块

将料架定位算法的偏移值转换为机器人补偿值

核心逻辑：
1. 偏移值 = 实际位置 - 标准位置（由定位算法输出）
2. 补偿值 = 根据机器人坐标系、装箱方向、料架侧面计算
3. PLC数据格式 = 转换为PLC可读的格式

补偿规则：
- X轴：料架左右方向偏移，直接作为X补偿
- Y轴：料架前后方向偏移，直接作为Y补偿  
- Z轴：料架高度方向偏移，直接作为Z补偿
- 可根据料架侧面（LEFT/RIGHT）调整符号
"""
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal

from apps.core.constants import RackSide

logger = logging.getLogger(__name__)


@dataclass
class OffsetData:
    """偏移值数据（从定位算法输出）"""
    offset_x: float  # X轴偏移（mm）
    offset_y: float  # Y轴偏移（mm）
    offset_z: float  # Z轴偏移（mm）
    confidence_x: float  # X轴置信度
    confidence_y: float  # Y轴置信度
    confidence_z: float  # Z轴置信度


@dataclass
class CompensationData:
    """补偿值数据（输出给机器人/PLC）"""
    compensation_x: float  # X轴补偿（mm）
    compensation_y: float  # Y轴补偿（mm）
    compensation_z: float  # Z轴补偿（mm）
    compensation_rz: float  # RZ轴补偿（度，可选）
    
    # 置信度（继承自偏移值）
    confidence_x: float
    confidence_y: float
    confidence_z: float
    
    # 是否有效
    is_valid: bool
    validation_message: str = ""
    
    # 原始偏移值（用于追溯）
    original_offset_x: float = 0.0
    original_offset_y: float = 0.0
    original_offset_z: float = 0.0


@dataclass
class CompensationRule:
    """补偿规则配置"""
    # 坐标系转换
    x_direction: int = 1  # X轴方向：1正向，-1反向
    y_direction: int = 1  # Y轴方向：1正向，-1反向
    z_direction: int = 1  # Z轴方向：1正向，-1反向
    
    # 补偿限制
    max_compensation_x: float = 50.0  # X轴最大补偿（mm）
    max_compensation_y: float = 50.0  # Y轴最大补偿（mm）
    max_compensation_z: float = 30.0  # Z轴最大补偿（mm）
    max_compensation_rz: float = 5.0  # RZ轴最大补偿（度）
    
    # 最小置信度要求
    min_confidence: float = 0.3
    
    # 料架侧面相关
    left_side_x_invert: bool = False  # 左侧X轴是否反向
    right_side_x_invert: bool = False  # 右侧X轴是否反向


class CompensationCalculator:
    """补偿值计算器"""
    
    def __init__(self, rule: Optional[CompensationRule] = None):
        """
        初始化补偿计算器
        
        Args:
            rule: 补偿规则配置（可选，使用默认规则）
        """
        self.rule = rule or CompensationRule()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def calculate_compensation(
        self,
        offset_x: float,
        offset_y: float,
        offset_z: float,
        confidence_x: float = 1.0,
        confidence_y: float = 1.0,
        confidence_z: float = 1.0,
        rack_side: str = RackSide.BOTH,
        offset_rz: float = 0.0
    ) -> CompensationData:
        """
        计算补偿值
        
        Args:
            offset_x: X轴偏移（mm）
            offset_y: Y轴偏移（mm）
            offset_z: Z轴偏移（mm）
            confidence_x: X轴置信度
            confidence_y: Y轴置信度
            confidence_z: Z轴置信度
            rack_side: 料架侧面（LEFT/RIGHT/BOTH）
            offset_rz: RZ轴偏移（度，可选）
            
        Returns:
            CompensationData: 补偿值数据
        """
        self.logger.info(
            f"计算补偿值: 偏移 X={offset_x:.2f}, Y={offset_y:.2f}, Z={offset_z:.2f}, "
            f"侧面={rack_side}"
        )
        
        # 1. 基础补偿计算（偏移值直接作为补偿值的起点）
        # 注意：补偿值通常等于偏移值，但符号可能需要调整
        compensation_x = offset_x * self.rule.x_direction
        compensation_y = offset_y * self.rule.y_direction
        compensation_z = offset_z * self.rule.z_direction
        compensation_rz = offset_rz
        
        # 2. 根据料架侧面调整X轴补偿
        if rack_side == RackSide.LEFT and self.rule.left_side_x_invert:
            compensation_x = -compensation_x
            self.logger.debug(f"左侧料架：X补偿反向 → {compensation_x:.2f}mm")
        elif rack_side == RackSide.RIGHT and self.rule.right_side_x_invert:
            compensation_x = -compensation_x
            self.logger.debug(f"右侧料架：X补偿反向 → {compensation_x:.2f}mm")
        
        # 3. 验证补偿值是否在允许范围内
        is_valid = True
        validation_messages = []
        
        # 检查置信度
        if confidence_x < self.rule.min_confidence:
            is_valid = False
            validation_messages.append(f"X轴置信度不足({confidence_x:.3f} < {self.rule.min_confidence})")
        
        if confidence_y < self.rule.min_confidence:
            is_valid = False
            validation_messages.append(f"Y轴置信度不足({confidence_y:.3f} < {self.rule.min_confidence})")
        
        if confidence_z < self.rule.min_confidence:
            is_valid = False
            validation_messages.append(f"Z轴置信度不足({confidence_z:.3f} < {self.rule.min_confidence})")
        
        # 检查补偿范围
        if abs(compensation_x) > self.rule.max_compensation_x:
            is_valid = False
            validation_messages.append(
                f"X补偿超限({abs(compensation_x):.2f} > {self.rule.max_compensation_x}mm)"
            )
        
        if abs(compensation_y) > self.rule.max_compensation_y:
            is_valid = False
            validation_messages.append(
                f"Y补偿超限({abs(compensation_y):.2f} > {self.rule.max_compensation_y}mm)"
            )
        
        if abs(compensation_z) > self.rule.max_compensation_z:
            is_valid = False
            validation_messages.append(
                f"Z补偿超限({abs(compensation_z):.2f} > {self.rule.max_compensation_z}mm)"
            )
        
        if abs(compensation_rz) > self.rule.max_compensation_rz:
            is_valid = False
            validation_messages.append(
                f"RZ补偿超限({abs(compensation_rz):.2f} > {self.rule.max_compensation_rz}°)"
            )
        
        validation_message = "; ".join(validation_messages) if validation_messages else ""
        
        # 4. 构建补偿数据
        compensation = CompensationData(
            compensation_x=compensation_x,
            compensation_y=compensation_y,
            compensation_z=compensation_z,
            compensation_rz=compensation_rz,
            confidence_x=confidence_x,
            confidence_y=confidence_y,
            confidence_z=confidence_z,
            is_valid=is_valid,
            validation_message=validation_message,
            original_offset_x=offset_x,
            original_offset_y=offset_y,
            original_offset_z=offset_z
        )
        
        self.logger.info(
            f"补偿值计算完成: X={compensation_x:.2f}mm, Y={compensation_y:.2f}mm, "
            f"Z={compensation_z:.2f}mm, RZ={compensation_rz:.3f}°, "
            f"有效={is_valid}"
        )
        
        if not is_valid:
            self.logger.warning(f"补偿值验证失败: {validation_message}")
        
        return compensation
    
    def calculate_compensation_from_offset_data(
        self,
        offset_data: OffsetData,
        rack_side: str = RackSide.BOTH,
        offset_rz: float = 0.0
    ) -> CompensationData:
        """
        从偏移值数据对象计算补偿值
        
        Args:
            offset_data: 偏移值数据对象
            rack_side: 料架侧面
            offset_rz: RZ轴偏移
            
        Returns:
            CompensationData: 补偿值数据
        """
        return self.calculate_compensation(
            offset_x=offset_data.offset_x,
            offset_y=offset_data.offset_y,
            offset_z=offset_data.offset_z,
            confidence_x=offset_data.confidence_x,
            confidence_y=offset_data.confidence_y,
            confidence_z=offset_data.confidence_z,
            rack_side=rack_side,
            offset_rz=offset_rz
        )
    
    def apply_compensation_limits(
        self,
        compensation: CompensationData,
        clip: bool = False
    ) -> CompensationData:
        """
        应用补偿限制
        
        Args:
            compensation: 补偿值数据
            clip: 是否裁剪到限制范围（True）还是标记为无效（False）
            
        Returns:
            处理后的补偿值数据
        """
        if clip:
            # 裁剪模式：将超限的补偿值裁剪到限制范围
            compensation.compensation_x = max(
                -self.rule.max_compensation_x,
                min(self.rule.max_compensation_x, compensation.compensation_x)
            )
            compensation.compensation_y = max(
                -self.rule.max_compensation_y,
                min(self.rule.max_compensation_y, compensation.compensation_y)
            )
            compensation.compensation_z = max(
                -self.rule.max_compensation_z,
                min(self.rule.max_compensation_z, compensation.compensation_z)
            )
            compensation.compensation_rz = max(
                -self.rule.max_compensation_rz,
                min(self.rule.max_compensation_rz, compensation.compensation_rz)
            )
            
            self.logger.info("补偿值已裁剪到限制范围")
        
        return compensation
    
    def to_plc_format(self, compensation: CompensationData) -> Dict:
        """
        转换为PLC数据格式
        
        Args:
            compensation: 补偿值数据
            
        Returns:
            PLC数据格式字典
        """
        # PLC通常使用整数或固定精度的浮点数
        # 这里假设PLC使用mm为单位的浮点数
        
        plc_data = {
            'x': round(compensation.compensation_x, 2),  # 保留2位小数
            'y': round(compensation.compensation_y, 2),
            'z': round(compensation.compensation_z, 2),
            'rz': round(compensation.compensation_rz, 3),  # 角度保留3位小数
            'valid': 1 if compensation.is_valid else 0,
            'confidence_x': round(compensation.confidence_x, 3),
            'confidence_y': round(compensation.confidence_y, 3),
            'confidence_z': round(compensation.confidence_z, 3),
        }
        
        self.logger.debug(f"PLC数据格式: {plc_data}")
        
        return plc_data
    
    def to_dict(self, compensation: CompensationData) -> Dict:
        """
        转换为字典格式
        
        Args:
            compensation: 补偿值数据
            
        Returns:
            字典
        """
        return {
            'compensation_x': float(compensation.compensation_x),
            'compensation_y': float(compensation.compensation_y),
            'compensation_z': float(compensation.compensation_z),
            'compensation_rz': float(compensation.compensation_rz),
            'confidence_x': float(compensation.confidence_x),
            'confidence_y': float(compensation.confidence_y),
            'confidence_z': float(compensation.confidence_z),
            'is_valid': compensation.is_valid,
            'validation_message': compensation.validation_message,
            'original_offset_x': float(compensation.original_offset_x),
            'original_offset_y': float(compensation.original_offset_y),
            'original_offset_z': float(compensation.original_offset_z),
        }
    
    def batch_calculate(
        self,
        offsets: list,
        rack_sides: list,
        offset_rzs: Optional[list] = None
    ) -> list:
        """
        批量计算补偿值
        
        Args:
            offsets: 偏移值列表 [(x, y, z, conf_x, conf_y, conf_z), ...]
            rack_sides: 料架侧面列表
            offset_rzs: RZ偏移列表（可选）
            
        Returns:
            补偿值列表
        """
        if offset_rzs is None:
            offset_rzs = [0.0] * len(offsets)
        
        compensations = []
        
        for i, (offset, rack_side, offset_rz) in enumerate(zip(offsets, rack_sides, offset_rzs)):
            if len(offset) == 3:
                # 无置信度
                x, y, z = offset
                conf_x, conf_y, conf_z = 1.0, 1.0, 1.0
            elif len(offset) == 6:
                # 有置信度
                x, y, z, conf_x, conf_y, conf_z = offset
            else:
                raise ValueError(f"偏移值格式错误: {offset}")
            
            compensation = self.calculate_compensation(
                offset_x=x,
                offset_y=y,
                offset_z=z,
                confidence_x=conf_x,
                confidence_y=conf_y,
                confidence_z=conf_z,
                rack_side=rack_side,
                offset_rz=offset_rz
            )
            
            compensations.append(compensation)
        
        self.logger.info(f"批量计算完成: {len(compensations)} 个补偿值")
        
        return compensations


class CompensationValidator:
    """补偿值验证器"""
    
    @staticmethod
    def validate_compensation(
        compensation: CompensationData,
        strict: bool = False
    ) -> Tuple[bool, str]:
        """
        验证补偿值
        
        Args:
            compensation: 补偿值数据
            strict: 是否严格模式（严格模式下任何警告都视为失败）
            
        Returns:
            (是否有效, 验证消息)
        """
        if not compensation.is_valid:
            return False, compensation.validation_message
        
        warnings = []
        
        # 检查补偿值是否过大（警告级别）
        warn_threshold_x = 30.0  # mm
        warn_threshold_y = 30.0  # mm
        warn_threshold_z = 20.0  # mm
        
        if abs(compensation.compensation_x) > warn_threshold_x:
            warnings.append(f"X补偿较大({abs(compensation.compensation_x):.2f}mm)")
        
        if abs(compensation.compensation_y) > warn_threshold_y:
            warnings.append(f"Y补偿较大({abs(compensation.compensation_y):.2f}mm)")
        
        if abs(compensation.compensation_z) > warn_threshold_z:
            warnings.append(f"Z补偿较大({abs(compensation.compensation_z):.2f}mm)")
        
        # 检查置信度是否偏低（警告级别）
        warn_confidence = 0.5
        
        if compensation.confidence_x < warn_confidence:
            warnings.append(f"X置信度偏低({compensation.confidence_x:.3f})")
        
        if compensation.confidence_y < warn_confidence:
            warnings.append(f"Y置信度偏低({compensation.confidence_y:.3f})")
        
        if compensation.confidence_z < warn_confidence:
            warnings.append(f"Z置信度偏低({compensation.confidence_z:.3f})")
        
        if warnings:
            warning_message = "警告: " + "; ".join(warnings)
            if strict:
                return False, warning_message
            else:
                return True, warning_message
        
        return True, "验证通过"
    
    @staticmethod
    def compare_compensations(
        compensation1: CompensationData,
        compensation2: CompensationData,
        tolerance: float = 5.0
    ) -> Dict:
        """
        比较两个补偿值
        
        Args:
            compensation1: 补偿值1
            compensation2: 补偿值2
            tolerance: 容差（mm）
            
        Returns:
            比较结果
        """
        diff_x = compensation1.compensation_x - compensation2.compensation_x
        diff_y = compensation1.compensation_y - compensation2.compensation_y
        diff_z = compensation1.compensation_z - compensation2.compensation_z
        
        is_similar = (
            abs(diff_x) <= tolerance and
            abs(diff_y) <= tolerance and
            abs(diff_z) <= tolerance
        )
        
        return {
            'is_similar': is_similar,
            'diff_x': float(diff_x),
            'diff_y': float(diff_y),
            'diff_z': float(diff_z),
            'max_diff': float(max(abs(diff_x), abs(diff_y), abs(diff_z))),
            'tolerance': tolerance
        }
