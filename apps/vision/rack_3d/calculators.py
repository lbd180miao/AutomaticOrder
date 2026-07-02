"""
补偿计算模块 (Compensation Calculation)

比较实际测量坐标与配方理论坐标，计算三轴偏移/补偿值并校验。

约定（依据交付文档示例）：
  offset = actual - standard
  compensation = offset * sign_convention（默认 sign_convention = 1.0，即补偿值等于偏移值）
例如：标准 Z=800，实际 Z=795 → offset_z=-5 → 补偿 -5mm。

Requirements: 8.1-8.5, 9.1-9.6
"""

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CompensationCalculator:
    """补偿值计算器。"""

    def __init__(self, sign_convention: float = 1.0):
        # 1.0: 补偿值 = 偏移值；-1.0: 负反馈补偿
        self.sign_convention = float(sign_convention)

    def calculate_actual_values(
        self,
        x_coordinate: float, y_coordinate: float, z_coordinate: float,
        x_confidence: float, y_confidence: float, z_confidence: float,
    ) -> Dict[str, float]:
        """打包实际坐标与置信度。"""
        return {
            'actual_x': float(x_coordinate),
            'actual_y': float(y_coordinate),
            'actual_z': float(z_coordinate),
            'confidence_x': float(x_confidence),
            'confidence_y': float(y_confidence),
            'confidence_z': float(z_confidence),
        }

    def calculate_offsets(
        self,
        actual_x: float, actual_y: float, actual_z: float,
        standard_x: float, standard_y: float, standard_z: float,
    ) -> Dict[str, float]:
        """offset = actual - standard（保留精度到 0.001mm 由调用方处理）。"""
        offsets = {
            'offset_x': float(actual_x) - float(standard_x),
            'offset_y': float(actual_y) - float(standard_y),
            'offset_z': float(actual_z) - float(standard_z),
        }
        logger.info("补偿计算: ΔX=%.3f ΔY=%.3f ΔZ=%.3f",
                    offsets['offset_x'], offsets['offset_y'], offsets['offset_z'])
        return offsets

    def calculate_compensations(
        self, offset_x: float, offset_y: float, offset_z: float
    ) -> Dict[str, float]:
        """补偿 = 偏移 * sign_convention。"""
        s = self.sign_convention
        return {
            'compensation_x': s * float(offset_x),
            'compensation_y': s * float(offset_y),
            'compensation_z': s * float(offset_z),
        }

    def validate_offsets(
        self,
        offset_x: float, offset_y: float, offset_z: float,
        max_offset_x: float, max_offset_y: float, max_offset_z: float,
    ) -> bool:
        """校验各轴偏移是否在允许范围内。"""
        in_range = (
            abs(offset_x) <= max_offset_x
            and abs(offset_y) <= max_offset_y
            and abs(offset_z) <= max_offset_z
        )
        if not in_range:
            logger.warning(
                "补偿超限: ΔX=%.3f(max %.3f) ΔY=%.3f(max %.3f) ΔZ=%.3f(max %.3f)",
                offset_x, max_offset_x, offset_y, max_offset_y, offset_z, max_offset_z,
            )
        return in_range

    def validate_result(
        self,
        offset_x: float, offset_y: float, offset_z: float,
        max_offset_x: float, max_offset_y: float, max_offset_z: float,
        confidence: float, confidence_threshold: float,
    ) -> Tuple[bool, Optional[str]]:
        """综合校验偏移范围与置信度，返回 (是否有效, 错误信息)。"""
        if not self.validate_offsets(
            offset_x, offset_y, offset_z, max_offset_x, max_offset_y, max_offset_z
        ):
            return False, (
                f"补偿值超出允许范围 (ΔX={offset_x:.3f}, ΔY={offset_y:.3f}, ΔZ={offset_z:.3f})"
            )
        if confidence < confidence_threshold:
            return False, (
                f"置信度不足: {confidence:.3f} < 阈值 {confidence_threshold:.3f}"
            )
        return True, None

    def calculate_overall_confidence(
        self, confidence_x: float, confidence_y: float, confidence_z: float
    ) -> float:
        """综合置信度取三轴最小值（最保守）。"""
        return float(min(confidence_x, confidence_y, confidence_z))
