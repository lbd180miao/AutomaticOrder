"""2D 料架层数、层高和层距测量。

手动调试 API 与 DB100.DBX50.0 自动流程都调用本模块，避免两套算法参数漂移。
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings

from apps.core.constants import DeviceType
from apps.devices.services import get_device_adapter

from .models import RackLayerMeasurement, RackMeasurementProfile


class RackMeasurementError(RuntimeError):
    pass


@dataclass
class MeasurementResult:
    success: bool
    detected_layer_count: int
    measured_layer_height: float | None
    measured_layer_spacing: float | None
    confidence: float
    candidate_lines: list[int]
    top_lines: list[int]
    bottom_lines: list[int]
    roi: dict
    annotated_image: np.ndarray
    error: str = ''


def _bounded_roi(image: np.ndarray, params: dict) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    x = max(0, min(int(params.get('roi_x', 0)), width - 1))
    y = max(0, min(int(params.get('roi_y', 0)), height - 1))
    roi_width = int(params.get('roi_width', 0))
    roi_height = int(params.get('roi_height', 0))
    right = width if roi_width <= 0 else min(width, x + roi_width)
    bottom = height if roi_height <= 0 else min(height, y + roi_height)
    if right - x < 40 or bottom - y < 40:
        raise RackMeasurementError('ROI 太小，宽高均需至少 40 像素')
    return x, y, right, bottom


def _find_projection_peaks(projection: np.ndarray, threshold: float,
                           min_distance: int, max_count: int) -> list[int]:
    maximum = float(projection.max()) if projection.size else 0.0
    if maximum <= 1e-9:
        return []
    normalized = projection.astype(np.float32) / maximum
    adaptive = max(float(threshold), float(np.percentile(normalized, 70)) * 0.70)
    maxima = np.where(
        (normalized >= adaptive)
        & (normalized >= np.roll(normalized, 1))
        & (normalized >= np.roll(normalized, -1))
    )[0]
    maxima = maxima[(maxima > 1) & (maxima < len(normalized) - 2)]
    # 一条有厚度的横梁会在上下边沿产生两个 Sobel 峰。先聚类并取加权中心，
    # 否则会把“横梁外缘距离”误当成开口层高（通常多出数个像素）。
    groups: list[list[int]] = []
    for row in sorted(maxima.tolist()):
        if not groups or row - groups[-1][-1] > min_distance:
            groups.append([row])
        else:
            groups[-1].append(row)
    centers = []
    for group in groups:
        weights = np.asarray([normalized[row] for row in group], dtype=np.float64)
        center = int(round(float(np.average(group, weights=weights))))
        centers.append(center)
    ranked = sorted(centers, key=lambda row: float(normalized[row]), reverse=True)
    return sorted(ranked[:max_count])


def _match_pattern(candidates: list[int], strengths: np.ndarray, layer_count: int,
                   expected_height_px: float, expected_spacing_px: float):
    """在候选水平边缘中寻找 N 组 top/bottom 开口边界。"""
    if layer_count < 1 or expected_height_px <= 2 or expected_spacing_px <= 2:
        return [], [], 0.0

    best = ([], [], -1.0)
    # 标定值允许约 ±30% 的现场偏差；算法只借此识别边缘组合，最终值来自像素测量。
    for scale in np.linspace(0.70, 1.30, 25):
        height_px = expected_height_px * float(scale)
        spacing_px = expected_spacing_px * float(scale)
        tolerance = max(7.0, min(height_px, spacing_px) * 0.13)
        for start in candidates:
            wanted = []
            for index in range(layer_count):
                top = start + index * spacing_px
                wanted.extend((top, top + height_px))
            used: set[int] = set()
            matched: list[int | None] = []
            distances = []
            line_strengths = []
            for target in wanted:
                options = [row for row in candidates if row not in used]
                if not options:
                    matched.append(None)
                    continue
                row = min(options, key=lambda value: abs(value - target))
                distance = abs(row - target)
                if distance > tolerance:
                    matched.append(None)
                    continue
                matched.append(row)
                used.add(row)
                distances.append(distance / tolerance)
                line_strengths.append(float(strengths[row]))
            tops = [matched[i * 2] for i in range(layer_count)]
            bottoms = [matched[i * 2 + 1] for i in range(layer_count)]
            complete = sum(t is not None and b is not None for t, b in zip(tops, bottoms))
            completeness = complete / layer_count
            match_ratio = len([m for m in matched if m is not None]) / len(wanted)
            distance_score = 1.0 - (sum(distances) / len(distances) if distances else 1.0)
            strength_score = sum(line_strengths) / len(line_strengths) if line_strengths else 0.0
            score = completeness * 0.48 + match_ratio * 0.22 + distance_score * 0.18 + strength_score * 0.12
            if score > best[2]:
                best = (tops, bottoms, score)
    return best


def analyze_rack_image(image: np.ndarray, *, layer_count: int,
                       expected_layer_height: float, expected_layer_spacing: float,
                       mm_per_pixel: float, roi_x: int = 0, roi_y: int = 0,
                       roi_width: int = 0, roi_height: int = 0,
                       edge_threshold: float = 0.18,
                       min_peak_distance: int = 8) -> MeasurementResult:
    """检测料架水平开口边界并换算层高、层距。"""
    if image is None or image.size == 0:
        raise RackMeasurementError('没有可计算的图像')
    if image.ndim not in (2, 3):
        raise RackMeasurementError('图像格式不受支持')
    if not 1 <= int(layer_count) <= 20:
        raise RackMeasurementError('层数必须在 1～20 之间')
    if not math.isfinite(mm_per_pixel) or mm_per_pixel <= 0:
        raise RackMeasurementError('毫米/像素标定值必须大于 0')
    if not 0.03 <= float(edge_threshold) <= 0.95:
        raise RackMeasurementError('边缘阈值必须在 0.03～0.95 之间')

    params = {
        'roi_x': roi_x, 'roi_y': roi_y,
        'roi_width': roi_width, 'roi_height': roi_height,
    }
    left, top, right, bottom = _bounded_roi(image, params)
    cropped = image[top:bottom, left:right]
    gray = cropped if cropped.ndim == 2 else cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    vertical_gradient = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
    projection = np.mean(np.abs(vertical_gradient), axis=1)
    projection = cv2.GaussianBlur(projection.reshape(-1, 1), (1, 9), 0).reshape(-1)
    max_projection = float(projection.max()) if projection.size else 0.0
    strengths = projection / max_projection if max_projection > 0 else projection

    candidates = _find_projection_peaks(
        projection,
        threshold=float(edge_threshold),
        min_distance=max(3, int(min_peak_distance)),
        max_count=max(20, int(layer_count) * 8),
    )
    expected_height_px = float(expected_layer_height) / mm_per_pixel
    expected_spacing_px = float(expected_layer_spacing) / mm_per_pixel
    matched_tops, matched_bottoms, pattern_score = _match_pattern(
        candidates, strengths, int(layer_count), expected_height_px, expected_spacing_px,
    )

    paired = [
        (int(t), int(b)) for t, b in zip(matched_tops, matched_bottoms)
        if t is not None and b is not None and b > t
    ]
    valid_tops = [int(value) for value in matched_tops if value is not None]
    heights_px = [bottom_row - top_row for top_row, bottom_row in paired]
    spacings_px = [b - a for a, b in zip(valid_tops, valid_tops[1:])]
    detected_count = len(paired)
    measured_height = float(np.median(heights_px) * mm_per_pixel) if heights_px else None
    measured_spacing = (
        float(np.median(spacings_px) * mm_per_pixel)
        if spacings_px else (float(expected_layer_spacing) if layer_count == 1 and paired else None)
    )

    completeness = detected_count / int(layer_count)
    regularity = 1.0
    if len(heights_px) > 1:
        regularity *= max(0.0, 1.0 - float(np.std(heights_px)) / max(float(np.mean(heights_px)), 1.0))
    if len(spacings_px) > 1:
        regularity *= max(0.0, 1.0 - float(np.std(spacings_px)) / max(float(np.mean(spacings_px)), 1.0))
    confidence = max(0.0, min(1.0, completeness * 0.55 + pattern_score * 0.30 + regularity * 0.15))
    success = (
        detected_count == int(layer_count)
        and measured_height is not None
        and measured_spacing is not None
        and confidence >= 0.65
    )
    error = '' if success else (
        f'仅识别到 {detected_count}/{layer_count} 层，或图像边缘置信度不足；'
        '请检查 ROI、毫米/像素标定和边缘阈值'
    )

    annotated = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy()
    cv2.rectangle(annotated, (left, top), (right - 1, bottom - 1), (255, 190, 40), 2)
    matched_rows = set(valid_tops + [int(v) for v in matched_bottoms if v is not None])
    for row in candidates:
        absolute_row = top + row
        color = (70, 200, 70) if row in matched_rows else (40, 190, 255)
        thickness = 2 if row in matched_rows else 1
        cv2.line(annotated, (left, absolute_row), (right - 1, absolute_row), color, thickness)
    for index, (top_row, bottom_row) in enumerate(paired, start=1):
        center_y = top + (top_row + bottom_row) // 2
        cv2.putText(annotated, f'L{index}', (left + 10, center_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 230, 80), 2, cv2.LINE_AA)
    summary = (
        f'layers={detected_count}/{layer_count}  height={measured_height or 0:.2f}mm  '
        f'spacing={measured_spacing or 0:.2f}mm  conf={confidence:.0%}'
    )
    cv2.rectangle(annotated, (left, max(0, top - 34)),
                  (min(annotated.shape[1] - 1, left + 720), top), (20, 30, 45), -1)
    cv2.putText(annotated, summary, (left + 8, max(22, top - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (240, 245, 250), 1, cv2.LINE_AA)

    return MeasurementResult(
        success=success,
        detected_layer_count=detected_count,
        measured_layer_height=measured_height,
        measured_layer_spacing=measured_spacing,
        confidence=confidence,
        candidate_lines=[top + row for row in candidates],
        top_lines=[top + row for row in valid_tops],
        bottom_lines=[top + int(row) for row in matched_bottoms if row is not None],
        roi={'x': left, 'y': top, 'width': right - left, 'height': bottom - top},
        annotated_image=annotated,
        error=error,
    )


def profile_parameters(profile: RackMeasurementProfile) -> dict:
    return {
        'roi_x': profile.roi_x,
        'roi_y': profile.roi_y,
        'roi_width': profile.roi_width,
        'roi_height': profile.roi_height,
        'mm_per_pixel': float(profile.mm_per_pixel),
        'edge_threshold': float(profile.edge_threshold),
        'min_peak_distance': profile.min_peak_distance,
    }


class RackMeasurementService:
    def __init__(self, camera_adapter=None):
        self.camera_adapter = camera_adapter

    @staticmethod
    def active_profile():
        return RackMeasurementProfile.objects.filter(is_active=True).order_by('-updated_at').first()

    def capture(self, camera_code: str) -> tuple[np.ndarray, str]:
        adapter = self.camera_adapter or get_device_adapter(device_type=DeviceType.INSPECT_CAMERA)
        response = adapter.capture(camera_code, 'RACK_RECIPE_MEASUREMENT')
        path = response.get('image_path') if response else ''
        if not response or not response.get('success') or not path:
            raise RackMeasurementError((response or {}).get('error') or '2D 相机没有返回图像')
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise RackMeasurementError(f'无法读取 2D 相机图像：{path}')
        return image, str(path)

    @staticmethod
    def _archive(image: np.ndarray, suffix: str) -> str:
        relative_dir = Path('vision') / 'rack_measurements' / date.today().strftime('%Y%m%d')
        absolute_dir = Path(settings.MEDIA_ROOT) / relative_dir
        absolute_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{uuid.uuid4().hex}_{suffix}.jpg'
        path = absolute_dir / filename
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise RackMeasurementError(f'测量图像保存失败：{path}')
        return (relative_dir / filename).as_posix()

    def measure(self, image: np.ndarray, *, source: str, recipe, cycle=None,
                profile=None, parameters=None, input_image_path='') -> tuple[MeasurementResult, RackLayerMeasurement]:
        parameters = dict(parameters or (profile_parameters(profile) if profile else {}))
        result = analyze_rack_image(
            image,
            layer_count=int(parameters.get('layer_count') or recipe.layer_count),
            expected_layer_height=float(parameters.get('expected_layer_height') or recipe.layer_height),
            expected_layer_spacing=float(parameters.get('expected_layer_spacing') or recipe.layer_spacing),
            mm_per_pixel=float(parameters.get('mm_per_pixel', 0)),
            roi_x=int(parameters.get('roi_x', 0)),
            roi_y=int(parameters.get('roi_y', 0)),
            roi_width=int(parameters.get('roi_width', 0)),
            roi_height=int(parameters.get('roi_height', 0)),
            edge_threshold=float(parameters.get('edge_threshold', 0.18)),
            min_peak_distance=int(parameters.get('min_peak_distance', 8)),
        )
        archived_input = self._archive(image, 'input')
        archived_result = self._archive(result.annotated_image, 'result')
        tolerance = Decimal(str(recipe.tolerance_z))
        passed = None
        if result.success:
            height_ok = abs(Decimal(str(result.measured_layer_height)) - recipe.layer_height) <= tolerance
            spacing_ok = abs(Decimal(str(result.measured_layer_spacing)) - recipe.layer_spacing) <= tolerance
            passed = bool(height_ok and spacing_ok)
        record = RackLayerMeasurement.objects.create(
            station_cycle=cycle,
            profile=profile,
            source=source,
            input_image_path=archived_input or input_image_path,
            result_image_path=archived_result,
            detected_layer_count=result.detected_layer_count,
            measured_layer_height=result.measured_layer_height,
            measured_layer_spacing=result.measured_layer_spacing,
            confidence=result.confidence,
            passed=passed,
            is_success=result.success,
            parameters=parameters,
            result_data={
                'candidate_lines': result.candidate_lines,
                'top_lines': result.top_lines,
                'bottom_lines': result.bottom_lines,
                'roi': result.roi,
            },
            error_message=result.error,
        )
        return result, record


def measure_rack_recipe(*, product, rack, recipe):
    """RECIPE_MEASUREMENT_CALLABLE：PLC 自动触发的真实相机测量入口。"""
    profile = RackMeasurementService.active_profile()
    if profile is None:
        raise RackMeasurementError('尚未保存 2D 料架测量自动参数，请先在 MES 页面完成标定')
    from apps.workflow.models import StationCycle

    cycle = StationCycle.objects.filter(workflow__product=product).order_by('-created_at').first()
    service = RackMeasurementService()
    image, input_path = service.capture(profile.camera_code)
    result, _record = service.measure(
        image,
        source='PLC_AUTO',
        recipe=recipe,
        cycle=cycle,
        profile=profile,
        input_image_path=input_path,
    )
    if not result.success:
        raise RackMeasurementError(result.error)
    return {
        'measured_layer_height': result.measured_layer_height,
        'measured_layer_spacing': result.measured_layer_spacing,
        'detected_layer_count': result.detected_layer_count,
        'confidence': result.confidence,
    }
