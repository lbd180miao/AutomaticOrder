"""
料架结构健康度校验器
====================

在计算刚体变换 ΔT 之前，对三个基准面的几何一致性进行校验，
防止料架变形、布面干扰、点云质量不足等异常情况导致错误补偿。

校验项目：
  1. 区域1 与 区域3 法向量平行性（料架上下水平面应平行）
  2. 区域1 与 区域3 高度差变化量一致性（两区域 ΔZ 差异应小于阈值）
  3. 区域2 法向量与 Z_local 的正交性（竖直面应垂直于水平面）
  4. 三个区域各自的点云拟合内点率（点云质量保障）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from .local_template_3d import LocalFrameResult, PlaneResult

logger = logging.getLogger(__name__)


class ValidationErrorCode(str, Enum):
    """校验错误码"""
    NORMAL = "NORMAL"                   # 正常
    DEFORM = "DEFORM"                   # 料架局部变形（上下水平面高度差异过大）
    TILT = "TILT"                       # 料架倾斜异常（上下水平面法向量不平行）
    SIDE_WALL_ERROR = "SIDE_WALL_ERROR" # 竖直面异常（法向量与Z轴不正交）
    QUALITY_LOW = "QUALITY_LOW"         # 点云质量不足（拟合内点率过低）
    INSUFFICIENT_POINTS = "INSUFFICIENT_POINTS"  # 点数不足


@dataclass
class SingleCheckResult:
    """单项校验结果"""
    name: str           # 校验项名称
    passed: bool        # 是否通过
    value: float        # 实测值
    threshold: float    # 阈值
    unit: str           # 单位
    message: str        # 说明信息


@dataclass
class ValidationResult:
    """完整校验结果"""
    is_valid: bool                              # 总体是否通过
    error_code: ValidationErrorCode            # 主要错误码（NORMAL=正常）
    message: str                               # 总体说明
    checks: list[SingleCheckResult] = field(default_factory=list)  # 各项明细

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "error_code": self.error_code.value,
            "message": self.message,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "value": round(c.value, 4),
                    "threshold": round(c.threshold, 4),
                    "unit": c.unit,
                    "message": c.message,
                }
                for c in self.checks
            ],
        }


class RackStructureValidator:
    """
    料架结构健康度校验器。

    使用示例：
        validator = RackStructureValidator()
        result = validator.validate(frame_std, frame_cur)
        if not result.is_valid:
            raise RackStructureError(result.message)
    """

    def __init__(
        self,
        angle_tolerance_deg: float = 3.0,
        z_diff_tolerance_mm: float = 5.0,
        orthogonal_tolerance_deg: float = 5.0,
        min_inlier_ratio: float = 0.60,
        min_point_count: int = 50,
        reference_angle_tolerance_deg: float = 5.0,
    ):
        """
        Args:
            angle_tolerance_deg: 区域1与区域3法向量夹角容差 (°)
            z_diff_tolerance_mm: 上下水平面高度差变化量容差 (mm)
            orthogonal_tolerance_deg: 竖直面与水平面正交误差容差 (°)
            min_inlier_ratio: 最低可接受内点率 (0~1)
            min_point_count: 最低可接受点数
            reference_angle_tolerance_deg: 当前各平面相对标准法向的最大夹角
        """
        self.angle_tolerance_deg = angle_tolerance_deg
        self.z_diff_tolerance_mm = z_diff_tolerance_mm
        self.orthogonal_tolerance_deg = orthogonal_tolerance_deg
        self.min_inlier_ratio = min_inlier_ratio
        self.min_point_count = min_point_count
        self.reference_angle_tolerance_deg = reference_angle_tolerance_deg

    def validate(
        self,
        frame_cur: LocalFrameResult,
        frame_std: Optional[LocalFrameResult] = None,
    ) -> ValidationResult:
        """
        执行全部校验项目。

        Args:
            frame_cur: 当前局部坐标系（生产阶段拟合结果）
            frame_std: 标准局部坐标系（可选，用于高度差变化量校验）

        Returns:
            ValidationResult
        """
        checks: list[SingleCheckResult] = []
        failed_code = ValidationErrorCode.NORMAL

        # --- 校验1：点云质量（内点率）---
        quality_check = self._check_inlier_ratios(frame_cur)
        checks.extend(quality_check)
        if any(not c.passed for c in quality_check):
            failed_code = ValidationErrorCode.QUALITY_LOW

        # --- 校验2：区域1与区域3法向量平行性 ---
        tilt_check = self._check_parallel(frame_cur.plane1, frame_cur.plane3)
        checks.append(tilt_check)
        if not tilt_check.passed and failed_code == ValidationErrorCode.NORMAL:
            failed_code = ValidationErrorCode.TILT

        # --- 校验3：竖直面正交性 ---
        orth_check = self._check_orthogonal(frame_cur.plane2, frame_cur.z_local)
        checks.append(orth_check)
        if not orth_check.passed and failed_code == ValidationErrorCode.NORMAL:
            failed_code = ValidationErrorCode.SIDE_WALL_ERROR

        # --- 校验4：当前三个平面必须分别匹配标准模板法向 ---
        if frame_std is not None:
            reference_checks = self._check_reference_normals(frame_std, frame_cur)
            checks.extend(reference_checks)
            if any(not c.passed for c in reference_checks) and failed_code == ValidationErrorCode.NORMAL:
                failed_code = ValidationErrorCode.TILT

        # --- 校验5：上下水平面 ΔZ 差异（需要标准模板对比）---
        if frame_std is not None:
            deform_check = self._check_z_diff(frame_std, frame_cur)
            checks.append(deform_check)
            if not deform_check.passed and failed_code == ValidationErrorCode.NORMAL:
                failed_code = ValidationErrorCode.DEFORM

        # --- 汇总 ---
        geom_passed = all(c.passed for c in checks)
        if geom_passed:
            message = "所有基准面校验通过，料架结构正常"
        else:
            failed_items = [c.name for c in checks if not c.passed]
            message = f"校验失败（{failed_code.value}）：{', '.join(failed_items)}"
            logger.warning("料架结构校验失败，结果将被拦截 | %s", message)

        return ValidationResult(
            is_valid=geom_passed,
            error_code=failed_code,
            message=message,
            checks=checks,
        )

    # ------------------------------------------------------------------
    # 私有校验方法
    # ------------------------------------------------------------------

    def _check_inlier_ratios(self, frame: LocalFrameResult) -> list[SingleCheckResult]:
        """校验三个区域的点云拟合内点率"""
        results = []
        planes = [
            ("区域1(上水平面)内点率", frame.plane1),
            ("区域2(左竖直面)内点率", frame.plane2),
            ("区域3(下水平面)内点率", frame.plane3),
        ]
        for name, plane in planes:
            passed = plane.inlier_ratio >= self.min_inlier_ratio
            results.append(SingleCheckResult(
                name=name,
                passed=passed,
                value=plane.inlier_ratio * 100,
                threshold=self.min_inlier_ratio * 100,
                unit="%",
                message="通过" if passed else f"内点率 {plane.inlier_ratio*100:.1f}% 低于阈值 {self.min_inlier_ratio*100:.0f}%，请检查点云采集质量或布面遮挡",
            ))
        return results

    def _check_parallel(self, plane1: PlaneResult, plane3: PlaneResult) -> SingleCheckResult:
        """
        校验区域1与区域3法向量平行性（夹角应 < angle_tolerance_deg）。
        cos_angle = |n1 · n3|（取绝对值，因为两板面朝向相同）
        """
        cos_angle = float(np.clip(abs(np.dot(plane1.normal, plane3.normal)), 0, 1))
        angle_deg = float(np.degrees(np.arccos(cos_angle)))
        passed = angle_deg < self.angle_tolerance_deg
        return SingleCheckResult(
            name="上下水平面平行性",
            passed=passed,
            value=angle_deg,
            threshold=self.angle_tolerance_deg,
            unit="°",
            message="通过" if passed else f"区域1与区域3法向量夹角 {angle_deg:.2f}° 超过阈值 {self.angle_tolerance_deg}°，可能料架严重倾斜或法向量方向异常",
        )

    def _check_orthogonal(self, plane2: PlaneResult, z_local: np.ndarray) -> SingleCheckResult:
        """
        校验竖直面（区域2）法向量与 Z_local 的正交性。
        |n2 · Z_local| 应接近 0（正交时点积为0）。
        """
        dot = float(abs(np.dot(plane2.normal, z_local)))
        angle_from_ortho = float(np.degrees(np.arcsin(np.clip(dot, 0, 1))))
        passed = angle_from_ortho < self.orthogonal_tolerance_deg
        return SingleCheckResult(
            name="竖直面正交性",
            passed=passed,
            value=angle_from_ortho,
            threshold=self.orthogonal_tolerance_deg,
            unit="°",
            message="通过" if passed else f"区域2法向量偏离水平面 {angle_from_ortho:.2f}°，超过阈值 {self.orthogonal_tolerance_deg}°，竖直面拟合可能异常",
        )

    def _check_reference_normals(
        self,
        frame_std: LocalFrameResult,
        frame_cur: LocalFrameResult,
    ) -> list[SingleCheckResult]:
        """Ensure each current ROI still represents its taught physical plane."""
        results = []
        for label, standard, current in (
            ("区域1标准法向一致性", frame_std.plane1, frame_cur.plane1),
            ("区域2标准法向一致性", frame_std.plane2, frame_cur.plane2),
            ("区域3标准法向一致性", frame_std.plane3, frame_cur.plane3),
        ):
            cosine = float(np.clip(abs(np.dot(standard.normal, current.normal)), 0.0, 1.0))
            angle_deg = float(np.degrees(np.arccos(cosine)))
            passed = angle_deg <= self.reference_angle_tolerance_deg
            results.append(SingleCheckResult(
                name=label,
                passed=passed,
                value=angle_deg,
                threshold=self.reference_angle_tolerance_deg,
                unit="°",
                message="通过" if passed else (
                    f"当前平面与标准法向夹角 {angle_deg:.2f}° 超过阈值 "
                    f"{self.reference_angle_tolerance_deg:.2f}°，ROI 可能拟合到了错误表面"
                ),
            ))
        return results

    def _check_z_diff(
        self,
        frame_std: LocalFrameResult,
        frame_cur: LocalFrameResult,
    ) -> SingleCheckResult:
        """
        校验上下水平面高度差的一致性。

        ΔZ_1 = frame_cur.plane1的Z质心 - frame_std.plane1的Z质心
        ΔZ_3 = frame_cur.plane3的Z质心 - frame_std.plane3的Z质心
        |ΔZ_1 - ΔZ_3| 应 < z_diff_tolerance_mm

        这里使用质心 Z 分量作为代理，物理意义明确。
        """
        # 使用平面质心的Z坐标（在相机坐标系中）
        dz1 = float(frame_cur.plane1.centroid[2] - frame_std.plane1.centroid[2])
        dz3 = float(frame_cur.plane3.centroid[2] - frame_std.plane3.centroid[2])
        diff = float(abs(dz1 - dz3))
        passed = diff < self.z_diff_tolerance_mm
        return SingleCheckResult(
            name="上下水平面ΔZ一致性",
            passed=passed,
            value=diff,
            threshold=self.z_diff_tolerance_mm,
            unit="mm",
            message="通过" if passed else (
                f"|ΔZ_上({dz1:+.1f}mm) - ΔZ_下({dz3:+.1f}mm)| = {diff:.1f}mm 超过 {self.z_diff_tolerance_mm}mm，"
                "可能原因：料架局部变形、层板下垂、布面干扰或某区域拟合错误"
            ),
        )
