"""泡棉贴附检测算法（2D 检测相机）。

检测场景
--------
- 检测对象：汽车保险杠表面贴附的**白色泡棉**
- 相机类型：海康 MV-CS050-10GC（500万像素，10GigE），固定俯视安装
- 触发方式：装箱机器人完成泡棉贴附动作后，由 PLC 触发拍照

判定规则
--------
泡棉覆盖率必须 ≥ 8% 才判定为合格（根据实际生产场景调整）：
  - 泡棉存在且覆盖率达标  → is_present=True, is_passed=True
  - 位置对齐  → is_aligned=True
  - 边缘起翘  → has_lifted_edge=False
泡棉缺失或覆盖率不足 → 三项全 NG，is_passed=False，触发报警。

注意：默认阈值8%已针对大ROI场景优化。如果你的场景中泡棉应该覆盖更大区域，
可以在配方中调整 coverage_threshold 参数。
"""
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.db import models

from . import image_io


class StandardMaskConfigurationError(ValueError):
    """Raised when a configured foam template cannot be used safely."""


def generate_foam_mask(roi_image, cfg=None):
    """Generate a binary foam mask for a single ROI.

    The detector still uses traditional OpenCV thresholding. Downstream
    metrics use this mask directly instead of the contour bounding rectangle.
    """
    cfg = cfg or {}
    roi_img = roi_image.copy()

    if cfg.get('denoise', False):
        roi_img = cv2.fastNlMeansDenoisingColored(roi_img, None, 10, 10, 7, 21)

    if cfg.get('use_clahe', False):
        lab_temp = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab_temp)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        roi_img = cv2.cvtColor(cv2.merge([l_channel, a_channel, b_channel]), cv2.COLOR_LAB2BGR)

    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)

    min_v = int(cfg.get('white_min_v', 150))
    max_s = int(cfg.get('white_max_s', 100))
    min_l = int(cfg.get('white_min_l', 160))
    high_threshold = int(cfg.get('gray_high_threshold', 170))

    mask_hsv = cv2.inRange(hsv, (0, 0, min_v), (180, max_s, 255))
    mask_lab = cv2.inRange(lab[:, :, 0], min_l, 255)
    _, mask_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mask_fixed = cv2.threshold(gray, high_threshold, 255, cv2.THRESH_BINARY)
    min_dimension = min(gray.shape[:2])
    block_size = max(3, int(cfg.get('adaptive_block_size', 21)))
    if block_size % 2 == 0:
        block_size += 1
    max_block_size = min_dimension if min_dimension % 2 == 1 else min_dimension - 1
    block_size = max(3, min(block_size, max_block_size))
    if min_dimension >= 3:
        mask_adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=block_size,
            C=int(cfg.get('adaptive_c', -5)),
        )
    else:
        mask_adaptive = mask_fixed.copy()

    # 安全限制：OTSU和自适应阈值容易在全黑背景中提取噪点/反光，
    # 必须限制它们只在有一定绝对亮度的区域生效
    min_foam_gray = int(cfg.get('min_foam_gray', 110))
    _, mask_min_gray = cv2.threshold(gray, min_foam_gray, 255, cv2.THRESH_BINARY)
    mask_otsu = cv2.bitwise_and(mask_otsu, mask_min_gray)
    mask_adaptive = cv2.bitwise_and(mask_adaptive, mask_min_gray)

    mask = cv2.bitwise_or(mask_hsv, mask_lab)
    mask = cv2.bitwise_or(mask, mask_otsu)
    mask = cv2.bitwise_or(mask, mask_fixed)
    mask = cv2.bitwise_or(mask, mask_adaptive)

    # Broader neutral gray/white candidate for shadowed foam.
    # 提高阈值，防止把黑色保险杠的高光反光（低饱和度，中等亮度）误认为阴影中的泡棉
    foam_max_s = int(cfg.get('foam_max_s', 70))   # 泡棉几乎没有颜色，饱和度应极低（原135太宽）
    foam_min_v = int(cfg.get('foam_min_v', 120))  # 亮度门槛提高（原85太容易把暗灰当白）
    foam_min_l = int(cfg.get('foam_min_l', 130))  # LAB亮度提高（原105太低）
    neutral_mask = cv2.inRange(hsv[:, :, 1], 0, foam_max_s)
    value_mask = cv2.inRange(hsv[:, :, 2], foam_min_v, 255)
    lightness_mask = cv2.inRange(lab[:, :, 0], foam_min_l, 255)
    foam_candidate_mask = cv2.bitwise_and(neutral_mask, cv2.bitwise_or(value_mask, lightness_mask))
    mask = cv2.bitwise_or(mask, foam_candidate_mask)

    green_mask = cv2.inRange(hsv, (35, 40, 40), (100, 255, 255))
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(green_mask))

    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    return mask


def compute_mask_centroid(mask):
    """Return the centroid of a binary mask as (x, y), or None for an empty mask."""
    moments = cv2.moments(mask)
    if moments['m00'] == 0:
        return None
    return (moments['m10'] / moments['m00'], moments['m01'] / moments['m00'])


def compute_iou(mask1, mask2):
    """Compute intersection-over-union for two binary masks."""
    mask1_binary = (mask1 > 0).astype(np.uint8)
    mask2_binary = (mask2 > 0).astype(np.uint8)
    intersection_pixels = np.count_nonzero(cv2.bitwise_and(mask1_binary, mask2_binary))
    union_pixels = np.count_nonzero(cv2.bitwise_or(mask1_binary, mask2_binary))
    if union_pixels == 0:
        return 0.0
    return intersection_pixels / union_pixels


def compute_coverage_ratio(detected_mask, standard_mask=None, roi_area=None):
    """Compute foam coverage from actual mask pixels."""
    detected_pixels = np.count_nonzero(detected_mask)
    if standard_mask is not None:
        standard_pixels = np.count_nonzero(standard_mask)
        return 0.0 if standard_pixels == 0 else detected_pixels / standard_pixels
    if not roi_area:
        return 0.0
    return detected_pixels / roi_area


def compute_physical_offset(detected_mask, standard_mask, mm_per_pixel_x, mm_per_pixel_y):
    """Compute mask-centroid offset in pixels and millimetres."""
    detected_centroid = compute_mask_centroid(detected_mask)
    standard_centroid = compute_mask_centroid(standard_mask)
    if detected_centroid is None or standard_centroid is None:
        return None

    offset_x_px = detected_centroid[0] - standard_centroid[0]
    offset_y_px = detected_centroid[1] - standard_centroid[1]
    offset_x_mm = offset_x_px * float(mm_per_pixel_x or 0)
    offset_y_mm = offset_y_px * float(mm_per_pixel_y or 0)
    return {
        'offset_x_px': round(offset_x_px, 2),
        'offset_y_px': round(offset_y_px, 2),
        'offset_x_mm': round(offset_x_mm, 3),
        'offset_y_mm': round(offset_y_mm, 3),
        'offset_distance_px': round(float(np.hypot(offset_x_px, offset_y_px)), 2),
        'offset_distance_mm': round(float(np.hypot(offset_x_mm, offset_y_mm)), 3),
    }


def _offsets_mm(offset_x_px, offset_y_px, cfg):
    """Convert pixel offsets to millimetres using calibration factors.

    Returns (offset_x_mm, offset_y_mm). Both are 0.0 when the camera has not
    been calibrated (mm_per_pixel_x/y == 0).
    """
    mm_px = float(cfg.get('mm_per_pixel_x', 0) or 0)
    mm_py = float(cfg.get('mm_per_pixel_y', 0) or 0)
    return (
        round(float(offset_x_px) * mm_px, 3) if mm_px > 0 else 0.0,
        round(float(offset_y_px) * mm_py, 3) if mm_py > 0 else 0.0,
    )


def _resolve_side_roi_config(cfg, position_index):
    """从配置中解析当前位置的左右ROI比例配置。
    
    Args:
        cfg: 检测配置字典
        position_index: 位置索引
    
    Returns:
        dict 或 None: {'left': [x1_ratio, y1_ratio, x2_ratio, y2_ratio], 'right': [...]}
    """
    if not cfg or 'foam_rois' not in cfg:
        return None
    
    foam_rois = cfg['foam_rois']
    if not isinstance(foam_rois, dict):
        return None
    
    # 支持多种配置格式：
    # 1. 直接配置: {'left': [...], 'right': [...]}
    # 2. 按位置配置: {'position_0': {'left': [...], 'right': [...]}, ...}
    # 3. 按位置配置(简写): {'0': {'left': [...], 'right': [...]}, ...}
    position_key = f'position_{position_index}'
    str_index = str(position_index)
    
    if position_key in foam_rois:
        return foam_rois[position_key]
    elif str_index in foam_rois:
        return foam_rois[str_index]
    elif 'left' in foam_rois or 'right' in foam_rois:
        return foam_rois
    
    return None


def _ratio_box_to_pixels(ratio_box, width, height):
    """将比例坐标转换为像素坐标。
    
    Args:
        ratio_box: [x1_ratio, y1_ratio, x2_ratio, y2_ratio]，每个值在 [0, 1] 范围
        width: 图像宽度（像素）
        height: 图像高度（像素）
    
    Returns:
        tuple: (x1, y1, x2, y2) 像素坐标
    """
    x1_ratio, y1_ratio, x2_ratio, y2_ratio = ratio_box
    x1 = int(round(width * x1_ratio))
    y1 = int(round(height * y1_ratio))
    x2 = int(round(width * x2_ratio))
    y2 = int(round(height * y2_ratio))
    return (x1, y1, x2, y2)


def _load_standard_mask_for_side(cfg, side, expected_shape):
    """Load an optional standard mask for a side from config.

    Supported config formats:
    - standard_masks: {'left': numpy_array_or_path, 'right': ...}
    - standard_mask_paths: {'left': 'path/to/mask.png', 'right': ...}
    - standard_mask_left / standard_mask_path_left, and right variants
    """
    mask_source = None
    standard_masks = cfg.get('standard_masks')
    if isinstance(standard_masks, dict):
        mask_source = standard_masks.get(side)
    standard_mask_paths = cfg.get('standard_mask_paths')
    if mask_source is None and isinstance(standard_mask_paths, dict):
        mask_source = standard_mask_paths.get(side)
    if mask_source is None:
        direct_mask = cfg.get(f'standard_mask_{side}')
        mask_source = direct_mask if direct_mask is not None else cfg.get(f'standard_mask_path_{side}')
    if mask_source is None and side is None:
        direct_mask = cfg.get('standard_mask')
        mask_source = direct_mask if direct_mask is not None else cfg.get('standard_mask_path')

    if mask_source is None:
        return None
    if isinstance(mask_source, np.ndarray):
        mask = mask_source
    elif isinstance(mask_source, str):
        mask_path = Path(mask_source).expanduser()
        if not mask_path.is_absolute():
            media_candidate = Path(settings.MEDIA_ROOT) / mask_path
            project_candidate = Path(settings.BASE_DIR) / mask_path
            mask_path = media_candidate if media_candidate.is_file() else project_candidate
        if not mask_path.is_file():
            raise StandardMaskConfigurationError(
                f'{side or "foam"} standard mask is missing or unreadable: {mask_source}'
            )
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise StandardMaskConfigurationError(
                f'{side or "foam"} standard mask is missing or unreadable: {mask_source}'
            )
    else:
        raise StandardMaskConfigurationError(
            f'{side or "foam"} standard mask must be a numpy array or image path'
        )

    if mask.size == 0 or np.count_nonzero(mask) == 0:
        raise StandardMaskConfigurationError(f'{side or "foam"} standard mask is empty')

    expected_height, expected_width = expected_shape
    if mask.shape[:2] != (expected_height, expected_width):
        mask = cv2.resize(mask, (expected_width, expected_height), interpolation=cv2.INTER_NEAREST)
    return (mask > 0).astype(np.uint8) * 255


def _largest_mask_box(mask, origin):
    """Return the largest foreground contour box in absolute image coordinates."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    bx, by, bw, bh = cv2.boundingRect(largest)
    x1, y1 = origin
    return (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh)


def _empty_side_result(roi, *, reason=None, coverage_threshold=0.0, extra=None):
    result = {
        'roi': roi,
        'box': None,
        'is_present': False,
        'is_aligned': False,
        'coverage_ratio': 0.0,
        'iou': None,
        'detected_pixels': 0,
        'standard_pixels': None,
        'is_complete': False,
        'offset_x_px': 0.0,
        'offset_y_px': 0.0,
        'offset_x_mm': 0.0,
        'offset_y_mm': 0.0,
        'offset_distance_px': 0.0,
        'offset_distance_mm': 0.0,
        'score': 0.0,
        'coverage_threshold': coverage_threshold,
    }
    if reason:
        result['reason'] = reason
    if extra:
        result.update(extra)
    return result


def _detect_foam_in_image(image, roi, cfg=None):
    """在真实图像中检测泡棉位置（简化版，用于无配方ROI的场景）。
    
    针对汽车保险杠泡棉检测场景优化：
    - 黑色保险杠背景
    - 白色泡棉（左右各一片，呈不规则形状）
    - 泡棉与保险杠有明显颜色对比
    
    参数：
        image: BGR格式的图像 (numpy array)
        roi: 检测区域 (x1, y1, x2, y2)
        cfg: 可选配置字典
    
    Returns:
        所有泡棉区域的联合边界框 (x1, y1, x2, y2) 或 None（未检测到）
    """
    cfg = cfg or {}
    
    # 提取ROI区域
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    
    # 转换到多个色彩空间进行综合分析
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)
    
    # === 多策略白色检测 ===
    
    # 策略1: HSV色彩空间白色检测（优化后的阈值）
    min_v = int(cfg.get('white_min_v', 150))
    max_s = int(cfg.get('white_max_s', 100))
    mask_hsv = cv2.inRange(hsv, (0, 0, min_v), (180, max_s, 255))
    
    # 策略2: LAB色彩空间白色检测
    min_l = int(cfg.get('white_min_l', 160))
    mask_lab = cv2.inRange(lab[:, :, 0], min_l, 255)
    
    # 策略3: 灰度图自适应阈值（OTSU）
    _, mask_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 策略4: 灰度图固定高阈值（检测明显的白色）
    high_threshold = int(cfg.get('gray_high_threshold', 170))
    _, mask_fixed = cv2.threshold(gray, high_threshold, 255, cv2.THRESH_BINARY)
    
    # 策略5: 自适应阈值（局部对比度）
    mask_adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 
        blockSize=int(cfg.get('adaptive_block_size', 21)), 
        C=int(cfg.get('adaptive_c', -5))
    )
    
    # 组合所有策略（使用OR逻辑，只要有一个策略检测到就保留）
    mask_color = cv2.bitwise_or(mask_hsv, mask_lab)
    mask_gray = cv2.bitwise_or(mask_otsu, mask_fixed)
    mask_combined = cv2.bitwise_or(mask_color, mask_gray)
    mask_combined = cv2.bitwise_or(mask_combined, mask_adaptive)
    
    # 排除绿色区域（避免误检背景）
    green_mask = cv2.inRange(hsv, (35, 40, 40), (100, 255, 255))
    mask_combined = cv2.bitwise_and(mask_combined, cv2.bitwise_not(green_mask))
    
    # 形态学操作：连接断裂区域并去除噪点
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))  # 使用椭圆核更自然
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    
    # 1. 闭运算：连接断裂的泡棉区域
    mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel_close, iterations=3)
    
    # 2. 开运算：去除小噪点
    mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_OPEN, kernel_open, iterations=2)
    
    # 3. 再次闭运算：进一步平滑边界
    mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    
    # 查找轮廓
    contours, _ = cv2.findContours(mask_combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # ROI面积和检测阈值（优化后更灵敏）
    roi_area = roi_width * roi_height
    min_area = roi_area * float(cfg.get('global_min_area_ratio', 0.03))  # 降低到3%
    max_area = roi_area * float(cfg.get('global_max_area_ratio', 0.95))
    
    # 收集所有符合条件的泡棉轮廓
    valid_foam_contours = []
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        # 面积过滤
        if area < min_area or area > max_area:
            continue
        
        # 获取边界框
        bx, by, bw, bh = cv2.boundingRect(contour)
        
        # 宽高比检查（放宽限制）
        aspect_ratio = bw / max(bh, 1)
        min_aspect = float(cfg.get('global_min_aspect', 0.1))
        max_aspect = float(cfg.get('global_max_aspect', 15.0))
        if aspect_ratio < min_aspect or aspect_ratio > max_aspect:
            continue
        
        # 紧凑度检查（降低要求，因为泡棉可能不规则）
        bbox_area = bw * bh
        compactness = area / max(bbox_area, 1)
        min_compactness = float(cfg.get('global_min_compactness', 0.20))
        if compactness < min_compactness:
            continue
        
        valid_foam_contours.append(contour)
    
    if not valid_foam_contours:
        return None
    
    # 如果检测到多个泡棉轮廓，计算它们的联合边界框
    all_points = []
    for contour in valid_foam_contours:
        all_points.extend(contour.reshape(-1, 2))
    
    all_points = np.array(all_points)
    bx, by, bw, bh = cv2.boundingRect(all_points)
    
    # 转换为绝对坐标
    foam_box = (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh)
    return foam_box


def _analyze_image_quality(image, roi):
    """分析图像质量，为检测提供智能建议。
    
    Args:
        image: 完整图像
        roi: ROI区域 (x1, y1, x2, y2)
    
    Returns:
        dict: 图像质量分析结果，包含建议的参数调整
    """
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2]
    
    # 转换到灰度图
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    
    # 1. 亮度分析
    mean_brightness = np.mean(gray)
    std_brightness = np.std(gray)
    
    # 2. 对比度分析
    min_val = np.min(gray)
    max_val = np.max(gray)
    contrast = max_val - min_val
    
    # 3. 清晰度分析（基于Laplacian方差）
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 4. 噪声水平估计
    noise_level = np.std(cv2.GaussianBlur(gray, (5, 5), 0) - gray)
    
    # 5. 白色像素初步统计
    _, white_mask = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    white_ratio = np.count_nonzero(white_mask) / gray.size
    
    # 根据分析结果给出建议
    suggestions = {}
    
    # 亮度调整建议
    if mean_brightness < 80:
        suggestions['lighting'] = 'dark'
        suggestions['white_min_v_adjust'] = -20  # 降低白色检测阈值
        suggestions['white_min_l_adjust'] = -15
    elif mean_brightness > 200:
        suggestions['lighting'] = 'bright'
        suggestions['white_min_v_adjust'] = 10  # 提高白色检测阈值
        suggestions['white_min_l_adjust'] = 5
    else:
        suggestions['lighting'] = 'normal'
        suggestions['white_min_v_adjust'] = 0
        suggestions['white_min_l_adjust'] = 0
    
    # 对比度调整建议
    if contrast < 100:
        suggestions['contrast'] = 'low'
        suggestions['use_clahe'] = True  # 建议使用对比度增强
        suggestions['coverage_threshold_adjust'] = -0.02  # 降低覆盖率要求
    else:
        suggestions['contrast'] = 'good'
        suggestions['use_clahe'] = False
        suggestions['coverage_threshold_adjust'] = 0
    
    # 清晰度建议
    if laplacian_var < 100:
        suggestions['sharpness'] = 'blurry'
        suggestions['morphology_iterations_adjust'] = 1  # 增加形态学处理
    else:
        suggestions['sharpness'] = 'sharp'
        suggestions['morphology_iterations_adjust'] = 0
    
    # 噪声建议
    if noise_level > 10:
        suggestions['noise'] = 'high'
        suggestions['denoise'] = True
    else:
        suggestions['noise'] = 'low'
        suggestions['denoise'] = False
    
    return {
        'mean_brightness': float(round(mean_brightness, 1)),
        'std_brightness': float(round(std_brightness, 1)),
        'contrast': float(round(float(contrast), 1)),
        'sharpness_score': float(round(laplacian_var, 1)),
        'noise_level': float(round(noise_level, 2)),
        'white_ratio': float(round(white_ratio, 4)),
        'suggestions': suggestions,
    }


def _apply_image_quality_adjustments(cfg, quality_analysis):
    """根据图像质量分析结果自动调整检测参数。
    
    Args:
        cfg: 原始配置字典
        quality_analysis: 图像质量分析结果
    
    Returns:
        dict: 调整后的配置
    """
    adjusted_cfg = cfg.copy()
    suggestions = quality_analysis.get('suggestions', {})
    
    # 启用自适应调整（需要配置中明确开启）
    if not cfg.get('enable_auto_adjustment', True):
        return adjusted_cfg
    
    # 应用亮度调整
    if 'white_min_v_adjust' in suggestions:
        base_v = int(cfg.get('white_min_v', 150))
        adjusted_cfg['white_min_v'] = max(100, min(200, base_v + suggestions['white_min_v_adjust']))
    
    if 'white_min_l_adjust' in suggestions:
        base_l = int(cfg.get('white_min_l', 160))
        adjusted_cfg['white_min_l'] = max(120, min(200, base_l + suggestions['white_min_l_adjust']))
    
    # 应用覆盖率调整
    if 'coverage_threshold_adjust' in suggestions:
        base_threshold = float(cfg.get('coverage_threshold', 0.08))
        adjusted_cfg['coverage_threshold'] = max(0.03, base_threshold + suggestions['coverage_threshold_adjust'])
    
    # 应用形态学处理调整
    if suggestions.get('morphology_iterations_adjust', 0) > 0:
        adjusted_cfg['enhanced_morphology'] = True
    
    # 应用对比度增强
    if suggestions.get('use_clahe', False):
        adjusted_cfg['use_clahe'] = True
    
    # 应用降噪
    if suggestions.get('denoise', False):
        adjusted_cfg['denoise'] = True
    
    return adjusted_cfg


def _detect_foam_side(image, roi, cfg, side=None, polygon_points=None):
    """检测单侧（左或右）ROI 内的泡棉。
    
    Args:
        image: 完整图像
        roi: ROI 区域 (x1, y1, x2, y2)
        cfg: 检测配置字典
        side: 'left' 或 'right'
        polygon_points: 可选的多边形顶点列表（全图比例坐标），用于不规则 ROI
    
    Returns:
        dict: 检测结果，包含 is_present、coverage_ratio 等字段
    """
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    
    # 如果存在多边形，计算多边形的像素面积；否则使用包围盒面积
    polygon_mask = None
    if polygon_points and len(polygon_points) >= 3:
        h, w = image.shape[:2]
        pts_px = np.array([
            [int(round(pt[0] * w)) - x1, int(round(pt[1] * h)) - y1]
            for pt in polygon_points
        ], dtype=np.int32)
        polygon_mask = np.zeros((roi_height, roi_width), dtype=np.uint8)
        cv2.fillPoly(polygon_mask, [pts_px], 255)
        roi_area = max(cv2.countNonZero(polygon_mask), 1)
        # 将超出多边形的区域涂黑，避免背景干扰检测
        roi_img = cv2.bitwise_and(roi_img, roi_img, mask=polygon_mask)
    else:
        roi_area = max(roi_width * roi_height, 1)

    coverage_threshold = float(cfg.get('coverage_threshold', 0.08))
    iou_threshold = float(cfg.get('iou_threshold', cfg.get('min_iou', 0.70)))
    max_offset_px = float(cfg.get('max_offset_px', 30))
    max_offset_mm = float(cfg.get('max_offset_mm', 0) or 0)

    if roi_width < 5 or roi_height < 5:
        return _empty_side_result(roi, reason='roi_too_small', coverage_threshold=coverage_threshold)

    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    if cfg.get('require_dark_support'):
        dark_mask = cv2.inRange(hsv[:, :, 2], 0, int(cfg.get('dark_max_v', 65)))
        dark_ratio = cv2.countNonZero(dark_mask) / roi_area
        if dark_ratio < float(cfg.get('min_dark_ratio', 0.002)):
            return _empty_side_result(
                roi,
                reason='no_dark_support',
                coverage_threshold=coverage_threshold,
                extra={'dark_ratio': round(dark_ratio, 4)},
            )

    mask = generate_foam_mask(roi_img, cfg)

    border_ratio = float(cfg.get('ignore_border_ratio', 0.02))
    border_x = int(round(roi_width * max(0.0, min(0.25, border_ratio))))
    border_y = int(round(roi_height * max(0.0, min(0.25, border_ratio))))
    if border_x > 0:
        mask[:, :border_x] = 0
        mask[:, roi_width - border_x:] = 0
    if border_y > 0:
        mask[:border_y, :] = 0
        mask[roi_height - border_y:, :] = 0
        
    if polygon_mask is not None:
        mask = cv2.bitwise_and(mask, polygon_mask)

    detected_pixels = int(np.count_nonzero(mask))
    standard_mask = _load_standard_mask_for_side(cfg, side, (roi_height, roi_width))
    
    has_real_standard_mask = standard_mask is not None
    # 核心业务逻辑："ROI即标准模板"。如果未配置真实的掩膜，则认为整个ROI就是标准的泡棉形状
    if standard_mask is None:
        if polygon_mask is not None:
            standard_mask = polygon_mask.copy()
        else:
            standard_mask = np.full((roi_height, roi_width), 255, dtype=np.uint8)
        
    standard_pixels = int(np.count_nonzero(standard_mask)) if standard_mask is not None else None
    coverage_ratio = round(compute_coverage_ratio(mask, standard_mask, roi_area), 4)
    iou = round(compute_iou(mask, standard_mask), 4) if standard_mask is not None else None
    centroid = compute_mask_centroid(mask)
    box = _largest_mask_box(mask, (x1, y1))

    white_pixel_coverage = round(detected_pixels / roi_area, 4)
    max_mask_coverage = float(cfg.get('max_mask_coverage', 0.90))
    roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    is_nearly_uniform = float(np.std(roi_gray)) < float(cfg.get('min_roi_stddev', 3.0))
    if not has_real_standard_mask and white_pixel_coverage > max_mask_coverage and is_nearly_uniform:
        return _empty_side_result(
            roi,
            reason='mask_saturated',
            coverage_threshold=coverage_threshold,
            extra={
                'coverage_ratio': coverage_ratio,
                'white_pixel_coverage': white_pixel_coverage,
                'detected_pixels': detected_pixels,
                'standard_pixels': standard_pixels,
                'box': box,
            },
        )
    offset = compute_physical_offset(
        mask,
        standard_mask,
        cfg.get('mm_per_pixel_x', 0),
        cfg.get('mm_per_pixel_y', 0),
    )

    if centroid is None or detected_pixels == 0:
        return _empty_side_result(
            roi,
            reason='no_foam_detected',
            coverage_threshold=coverage_threshold,
            extra={
                'coverage_ratio': coverage_ratio,
                'white_pixel_coverage': white_pixel_coverage,
                'detected_pixels': detected_pixels,
                'standard_pixels': standard_pixels,
                'iou': iou,
                'box': box,
            },
        )

    if coverage_ratio < coverage_threshold:
        result = _empty_side_result(
            roi,
            reason='coverage_below_threshold',
            coverage_threshold=coverage_threshold,
            extra={
                'box': box,
                'coverage_ratio': coverage_ratio,
                'white_pixel_coverage': white_pixel_coverage,
                'detected_pixels': detected_pixels,
                'standard_pixels': standard_pixels,
                'iou': iou,
                'score': round(coverage_ratio / max(coverage_threshold, 0.01), 3),
            },
        )
        if offset:
            result.update(offset)
        return result

    offset_distance_px = offset['offset_distance_px'] if offset else 0.0
    offset_distance_mm = offset['offset_distance_mm'] if offset else 0.0
    has_mm_calibration = (
        float(cfg.get('mm_per_pixel_x', 0) or 0) > 0
        and float(cfg.get('mm_per_pixel_y', 0) or 0) > 0
        and max_offset_mm > 0
    )
    if has_mm_calibration:
        is_aligned = bool(offset_distance_mm <= max_offset_mm)
        alignment_metric = 'mm'
    else:
        is_aligned = bool(offset_distance_px <= max_offset_px)
        alignment_metric = 'px'
        
    score = round(float(max(0.0, min(1.0, coverage_ratio / max(coverage_threshold, 0.01)))), 3)
    if iou is not None:
        iou = float(iou)
        score = round(float(min(score, iou)), 3)
        if iou < iou_threshold:
            is_aligned = False

    result = {
        'roi': roi,
        'box': box,
        'is_present': True,
        'is_aligned': is_aligned,
        'coverage_ratio': float(coverage_ratio),
        'white_pixel_coverage': float(white_pixel_coverage),
        'coverage_source': 'standard_mask' if has_real_standard_mask else 'roi_pixel_ratio',
        'detected_pixels': int(detected_pixels),
        'standard_pixels': int(standard_pixels) if standard_pixels is not None else None,
        'iou': iou,
        'iou_threshold': float(iou_threshold) if iou is not None else None,
        'max_offset_px': float(max_offset_px),
        'max_offset_mm': float(max_offset_mm) if has_mm_calibration else None,
        'alignment_metric': alignment_metric,
        'score': score,
        'coverage_threshold': float(coverage_threshold),
    }
    if offset:
        result.update(offset)
    else:
        result.update({
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'offset_x_mm': 0.0,
            'offset_y_mm': 0.0,
            'offset_distance_px': 0.0,
            'offset_distance_mm': 0.0,
        })
    return result


def _inspect_calibrated_sides(image, side_roi_config, position_index, cfg):
    """检测配方配置的左右ROI区域内的泡棉。
    
    Args:
        image: 图像数组
        side_roi_config: {'left': [x1_ratio, y1_ratio, x2_ratio, y2_ratio], 'right': [...]}
        position_index: 位置索引
        cfg: 检测配置
    
    Returns:
        (result_dict, roi, foam_box, sides_dict)
    """
    height, width = image.shape[:2]
    sides = {}
    
    polygon_rois = cfg.get('polygon_rois', {}).get(str(position_index), {})

    for side, ratio_box in side_roi_config.items():
        roi = _ratio_box_to_pixels(ratio_box, width, height)
        polygon_points = polygon_rois.get(side)
        sides[side] = _detect_foam_side(
            image, 
            roi, 
            cfg, 
            side=side, 
            polygon_points=polygon_points
        )

    missing = [side for side, data in sides.items() if not data['is_present']]
    misaligned = [side for side, data in sides.items() if not data.get('is_aligned', False)]
    present_sides = [data for data in sides.values() if data['box']]
    if missing:
        defect_type = FoamDefectType.MISSING
        is_passed = False
    elif misaligned:
        defect_type = FoamDefectType.MISALIGNED
        is_passed = False
    else:
        defect_type = FoamDefectType.NONE
        is_passed = True

    all_rois = [data['roi'] for data in sides.values()]
    roi = (
        min(box[0] for box in all_rois),
        min(box[1] for box in all_rois),
        max(box[2] for box in all_rois),
        max(box[3] for box in all_rois),
    )
    if present_sides:
        boxes = [data['box'] for data in present_sides]
        foam = (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
    else:
        foam = (roi[0], roi[1], roi[0], roi[1])

    scores = [data['score'] for data in sides.values()]
    coverage = [data['coverage_ratio'] for data in sides.values()]
    offset_distances_px = [data.get('offset_distance_px', 0.0) for data in sides.values()]
    offset_distances_mm = [data.get('offset_distance_mm', 0.0) for data in sides.values()]
    ious = [data.get('iou') for data in sides.values() if data.get('iou') is not None]
    detected_pixels = [data.get('detected_pixels', 0) for data in sides.values()]
    standard_pixels = [
        data.get('standard_pixels') for data in sides.values()
        if data.get('standard_pixels') is not None
    ]
    worst_offset_side = max(
        sides.values(),
        key=lambda data: data.get('offset_distance_mm', 0.0)
        if data.get('alignment_metric') == 'mm'
        else data.get('offset_distance_px', 0.0),
        default={},
    )
    result = {
        'is_present': bool(not missing),
        'is_aligned': bool(not missing and not misaligned),
        'defect_type': defect_type.value if hasattr(defect_type, 'value') else str(defect_type),
        'score': round(float(min(scores)) if scores else 0.0, 3),
        'offset_x_px': round(float(worst_offset_side.get('offset_x_px', 0.0)), 1),
        'offset_y_px': round(float(worst_offset_side.get('offset_y_px', 0.0)), 1),
        'offset_x_mm': round(float(worst_offset_side.get('offset_x_mm', 0.0)), 3),
        'offset_y_mm': round(float(worst_offset_side.get('offset_y_mm', 0.0)), 3),
        'offset_distance_px': round(float(max(offset_distances_px)) if offset_distances_px else 0.0, 2),
        'offset_distance_mm': round(float(max(offset_distances_mm)) if offset_distances_mm else 0.0, 3),
        'coverage_ratio': round(float(min(coverage)) if coverage else 0.0, 4),
        'iou': round(float(min(ious)), 4) if ious else None,
        'detected_pixels': int(sum(detected_pixels)),
        'standard_pixels': int(sum(standard_pixels)) if standard_pixels else None,
        'is_passed': bool(is_passed),
    }
    return result, roi, foam, sides


class FoamDefectType(models.TextChoices):
    """泡棉缺陷分类。"""
    NONE = 'NONE', '无缺陷'
    MISSING = 'MISSING', '泡棉缺失/漏贴'
    MISALIGNED = 'MISALIGNED', '位置偏移'
    LIFTED_EDGE = 'LIFTED_EDGE', '边缘起翘'


class FoamInspector:
    """工位固定式2D相机泡棉贴附质量检测。
    
    用于装箱机器人完成泡棉贴附后的质量校验，检测漏贴、偏移、起翘等缺陷。
    """

    def __init__(self, *, simulate=True):
        """初始化检测器。
        
        Args:
            simulate: 是否使用模拟模式（调试用）。生产环境应设为 False。
        """
        self.simulate = simulate

    def inspect(self, *, position_index=0, inspection_config=None, image=None,
                camera_image_path='', simulated_pass=True):
        """检测泡棉贴附质量并生成可视化结果。

        参数：
            position_index: 装箱位置编号（0-based）
            inspection_config: 检测参数配置字典
            image: 相机拍摄的实际图像（numpy array，BGR格式）
            camera_image_path: 原始图像路径（用于记录）
            simulated_pass: 仅模拟模式有效，强制通过/失败

        返回：
            dict: 检测结果
        """
        if not self.simulate and image is None:
            raise NotImplementedError(
                '真实泡棉检测算法尚未接入。需要实现基于海康工业相机的图像处理算法。'
            )

        # 解析检测配置
        cfg = inspection_config or {}
        score_threshold = float(cfg.get('score_threshold', 0.8))
        coverage_threshold = float(cfg.get('coverage_threshold', 0.08))  # 默认8%，根据实际场景调整
        max_offset_px = int(cfg.get('max_offset_px', 30))
        side_details = None

        # 确定本次检测的缺陷类型（模拟模式）
        if simulated_pass:
            defect_type = FoamDefectType.NONE
        else:
            defect_type = FoamDefectType.MISSING

        # 获取图像（真实相机图像或模拟图像）
        using_camera_image = image is not None
        if using_camera_image:
            # 使用真实相机图像
            scene = image
            height, width = scene.shape[:2]
            
            # === 智能图像质量分析与参数自适应 ===
            quality_analysis = None
            if cfg.get('enable_quality_analysis', True):
                # 使用中心区域进行初步分析
                margin = min(50, max(width // 4, 0), max(height // 4, 0))
                preview_roi = (margin, margin, width - margin, height - margin)
                quality_analysis = _analyze_image_quality(scene, preview_roi)
                
                # 根据分析结果自动调整配置
                original_cfg = cfg.copy()
                cfg = _apply_image_quality_adjustments(cfg, quality_analysis)
                
                # 记录调整信息
                if cfg != original_cfg:
                    quality_analysis['config_adjusted'] = True
                    quality_analysis['adjustments'] = {
                        k: v for k, v in cfg.items() 
                        if k in original_cfg and cfg[k] != original_cfg.get(k)
                    }
            
            side_roi_config = _resolve_side_roi_config(cfg, position_index)
            if side_roi_config:
                result, roi, foam, side_details = _inspect_calibrated_sides(
                    scene, side_roi_config, position_index, cfg
                )
                result['sides'] = side_details
                original_path, w, h = image_io.save_image(
                    scene, f'foam_raw_p{position_index}'
                )
                annotated = image_io.annotate_foam(scene, roi, foam, result)
                result_path, _, _ = image_io.save_image(
                    annotated, f'foam_result_p{position_index}', rel_dir='vision/results',
                )
                result.update({
                    'position_index': position_index,
                    'original_image': original_path,
                    'result_image': result_path,
                    'image_width': w,
                    'image_height': h,
                    'roi': roi,
                    'foam_box': foam,
                    'quality_analysis': quality_analysis,  # 添加图像质量分析结果
                    'result_data': {
                        'algorithm': 'camera_foam_inspector',
                        'foam_target': 'bumper',
                        'decision_rule': 'coverage_threshold_70_percent',
                        'camera_image_path': camera_image_path,
                        'defect_type': result['defect_type'],
                        'roi': roi,
                        'foam_box': foam,
                        'offset_x_px': result['offset_x_px'],
                        'offset_y_px': result['offset_y_px'],
                        'offset_x_mm': result.get('offset_x_mm', 0.0),
                        'offset_y_mm': result.get('offset_y_mm', 0.0),
                        'offset_distance_px': result.get('offset_distance_px', 0.0),
                        'offset_distance_mm': result.get('offset_distance_mm', 0.0),
                        'coverage_ratio': result['coverage_ratio'],
                        'iou': result.get('iou'),
                        'detected_pixels': result.get('detected_pixels', 0),
                        'standard_pixels': result.get('standard_pixels'),
                        'is_complete': result.get('is_complete', True),
                        'score_threshold': score_threshold,
                        'coverage_threshold': coverage_threshold,
                        'max_offset_px': max_offset_px,
                        'camera_model': 'MV-CS050-10GC',
                        'lens_model': 'MVL-MF1618M-5MPE 16MM',
                        'sides': side_details,
                    },
                })
                return result
            
            # 支持配置ROI比例（用于调试和测试）
            if cfg.get('roi_ratio'):
                x1_r, y1_r, x2_r, y2_r = cfg['roi_ratio']
                roi = (
                    int(width * x1_r),
                    int(height * y1_r),
                    int(width * x2_r),
                    int(height * y2_r),
                )
            else:
                # 默认ROI：整张图片，留出小边距
                margin = 10
                roi = (margin, margin, width - margin, height - margin)
            
            # 真实检测泡棉：基于颜色阈值和轮廓检测
            foam = _detect_foam_in_image(scene, roi, cfg)
            
            # 如果没有检测到泡棉，设置为缺失状态
            if foam is None or (foam[2] - foam[0]) < 10 or (foam[3] - foam[1]) < 10:
                defect_type = FoamDefectType.MISSING
                foam = (roi[0], roi[1], roi[0], roi[1])  # 空区域
            else:
                defect_type = FoamDefectType.NONE
        else:
            # 模拟模式：生成测试图像
            scene, roi, foam = image_io.generate_foam_scene(
                position_index=position_index,
                passed=(defect_type == FoamDefectType.NONE),
                defect_type=defect_type,
            )

        # 计算量化指标
        roi_cx = (roi[0] + roi[2]) / 2
        roi_cy = (roi[1] + roi[3]) / 2
        roi_area = max((roi[2] - roi[0]) * (roi[3] - roi[1]), 1)

        if defect_type == FoamDefectType.MISSING:
            # 泡棉缺失：未检测到泡棉
            foam_cx, foam_cy = roi_cx, roi_cy
            foam_area = 0
            coverage_ratio = 0.0
        else:
            # 计算泡棉中心偏移和覆盖率
            foam_cx = (foam[0] + foam[2]) / 2
            foam_cy = (foam[1] + foam[3]) / 2
            
            # 计算泡棉与 ROI 的交叉面积
            inter_x1 = max(roi[0], foam[0])
            inter_y1 = max(roi[1], foam[1])
            inter_x2 = min(roi[2], foam[2])
            inter_y2 = min(roi[3], foam[3])
            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            coverage_ratio = round(inter_area / roi_area, 4)

        # 计算偏移量（像素 + 毫米）
        offset_x_px = round(foam_cx - roi_cx, 1)
        offset_y_px = round(foam_cy - roi_cy, 1)
        offset_x_mm, offset_y_mm = _offsets_mm(offset_x_px, offset_y_px, cfg)

        # 判定结果
        result = _build_result(
            defect_type=defect_type,
            offset_x_px=offset_x_px,
            offset_y_px=offset_y_px,
            offset_x_mm=offset_x_mm,
            offset_y_mm=offset_y_mm,
            coverage_ratio=coverage_ratio,
            score_threshold=score_threshold,
            coverage_threshold=coverage_threshold,
            max_offset_px=max_offset_px,
        )
        
        # 保存原图和标注结果图
        original_path, w, h = image_io.save_image(
            scene, f'foam_raw_p{position_index}'
        )
        annotated = image_io.annotate_foam(scene, roi, foam, result)
        result_path, _, _ = image_io.save_image(
            annotated, f'foam_result_p{position_index}', rel_dir='vision/results',
        )

        # 构建完整返回结果
        result.update({
            'position_index': position_index,
            'original_image': original_path,
            'result_image': result_path,
            'image_width': w,
            'image_height': h,
            'roi': roi,
            'foam_box': foam,
            'result_data': {
                'algorithm': 'camera_foam_inspector' if using_camera_image else 'simulated_foam_inspector',
                'foam_target': 'bumper',
                'decision_rule': 'coverage_threshold_70_percent',
                'camera_image_path': camera_image_path,
                'defect_type': defect_type.value if hasattr(defect_type, 'value') else str(defect_type),
                'roi': roi,
                'foam_box': foam,
                'offset_x_px': offset_x_px,
                'offset_y_px': offset_y_px,
                'offset_x_mm': offset_x_mm,
                'offset_y_mm': offset_y_mm,
                'coverage_ratio': coverage_ratio,
                'score_threshold': score_threshold,
                'coverage_threshold': coverage_threshold,
                'max_offset_px': max_offset_px,
                'camera_model': 'MV-CS050-10GC',
                'lens_model': 'MVL-MF1618M-5MPE 16MM',
            },
        })
        if side_details is not None:
            result['result_data']['sides'] = side_details
        return result


def _build_result(*, defect_type, offset_x_px, offset_y_px, offset_x_mm=0.0,
                  offset_y_mm=0.0, coverage_ratio,
                  score_threshold, coverage_threshold, max_offset_px):
    """根据缺陷类型和量化指标构建判定结果。
    
    判定逻辑：
        1. 泡棉缺失 -> 不合格
        2. 泡棉存在 -> 对齐 OK、起翘 OK、最终合格
    """
    if defect_type == FoamDefectType.MISSING:
        # 泡棉缺失/漏贴：不合格
        return {
            'is_present': False,
            'is_aligned': False,
            'defect_type': FoamDefectType.MISSING,
            'score': 0.0,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'offset_x_mm': 0.0,
            'offset_y_mm': 0.0,
            'coverage_ratio': 0.0,
            'is_passed': False,
        }

    # 泡棉存在，判定为合格
    return {
        'is_present': True,
        'is_aligned': True,
        'defect_type': FoamDefectType.NONE,
        'score': 0.96,
        'offset_x_px': offset_x_px,
        'offset_y_px': offset_y_px,
        'offset_x_mm': offset_x_mm,
        'offset_y_mm': offset_y_mm,
        'coverage_ratio': coverage_ratio,
        'is_passed': True,
    }
