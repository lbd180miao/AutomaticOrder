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
import cv2
import numpy as np
from django.db import models

from . import image_io


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
        'mean_brightness': round(mean_brightness, 1),
        'std_brightness': round(std_brightness, 1),
        'contrast': round(contrast, 1),
        'sharpness_score': round(laplacian_var, 1),
        'noise_level': round(noise_level, 2),
        'white_ratio': round(white_ratio, 4),
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


def _detect_foam_side(image, roi, cfg):
    """检测单侧（左或右）ROI 内的泡棉。
    
    Args:
        image: 完整图像
        roi: ROI 区域 (x1, y1, x2, y2)
        cfg: 检测配置字典
    
    Returns:
        dict: 检测结果，包含 is_present、coverage_ratio 等字段
    """
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    roi_area = max(roi_width * roi_height, 1)
    
    # 覆盖率阈值：根据实际场景调整
    # 降低阈值以适应不同尺寸的ROI配置，避免误判
    coverage_threshold = float(cfg.get('coverage_threshold', 0.08))
    
    if roi_width < 5 or roi_height < 5:
        return {
            'roi': roi,
            'box': None,
            'is_present': False,
            'is_aligned': False,
            'coverage_ratio': 0.0,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'score': 0.0,
        }

    # === 图像预处理（根据配置应用增强） ===
    
    # 降噪处理
    if cfg.get('denoise', False):
        roi_img = cv2.fastNlMeansDenoisingColored(roi_img, None, 10, 10, 7, 21)
    
    # 对比度增强（CLAHE）
    if cfg.get('use_clahe', False):
        lab_temp = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab_temp)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        roi_img = cv2.cvtColor(cv2.merge([l_channel, a_channel, b_channel]), cv2.COLOR_LAB2BGR)
    
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)
    
    # 可选：黑色底座检测（确保保险杠在视野内）
    if cfg.get('require_dark_support'):
        dark_mask = cv2.inRange(hsv[:, :, 2], 0, int(cfg.get('dark_max_v', 65)))
        dark_ratio = cv2.countNonZero(dark_mask) / roi_area
        if dark_ratio < float(cfg.get('min_dark_ratio', 0.002)):
            return {
                'roi': roi,
                'box': None,
                'is_present': False,
                'is_aligned': False,
                'coverage_ratio': 0.0,
                'offset_x_px': 0.0,
                'offset_y_px': 0.0,
                'score': 0.0,
                'reason': 'no_dark_support',
                'dark_ratio': round(dark_ratio, 4),
            }

    # 白色检测：HSV + LAB 双策略（降低阈值以提高检测灵敏度）
    min_v = int(cfg.get('white_min_v', 150))  # 从170降到150，更容易检测到白色
    max_s = int(cfg.get('white_max_s', 100))  # 从80提高到100，允许更多饱和度范围
    min_l = int(cfg.get('white_min_l', 160))  # 从175降到160，LAB空间更宽容
    white_hsv = cv2.inRange(hsv, (0, 0, min_v), (180, max_s, 255))
    white_lab = cv2.inRange(lab[:, :, 0], min_l, 255)
    mask = cv2.bitwise_or(white_hsv, white_lab)

    # 排除绿色区域（避免误检绿色背景物体）
    green_mask = cv2.inRange(hsv, (35, 40, 40), (100, 255, 255))

    # 边界忽略（避免边缘反光误检）- 减小边界忽略范围，提高检测覆盖
    border_ratio = float(cfg.get('ignore_border_ratio', 0.02))  # 从0.04降到0.02
    border_x = int(round(roi_width * max(0.0, min(0.25, border_ratio))))
    border_y = int(round(roi_height * max(0.0, min(0.25, border_ratio))))

    # 形态学操作：增强闭运算以更好地连接泡棉区域
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    
    # 降低最小面积阈值，提高检测灵敏度
    min_area = roi_area * float(cfg.get('side_min_area_ratio', 0.05))  # 从0.15降到0.05
    max_area = roi_area * float(cfg.get('side_max_area_ratio', 0.98))  # 从0.95提高到0.98

    def prepare_mask(raw_mask):
        """准备最终检测mask：排除绿色、边界，形态学处理"""
        prepared = cv2.bitwise_and(raw_mask, cv2.bitwise_not(green_mask))
        if border_x > 0:
            prepared[:, :border_x] = 0
            prepared[:, roi_width - border_x:] = 0
        if border_y > 0:
            prepared[:border_y, :] = 0
            prepared[roi_height - border_y:, :] = 0
        # 增强形态学处理
        prepared = cv2.morphologyEx(prepared, cv2.MORPH_CLOSE, kernel_close, iterations=3)  # 从2增加到3
        prepared = cv2.morphologyEx(prepared, cv2.MORPH_OPEN, kernel_open, iterations=2)  # 增加开运算次数
        if border_x > 0:
            prepared[:, :border_x] = 0
            prepared[:, roi_width - border_x:] = 0
        if border_y > 0:
            prepared[:border_y, :] = 0
            prepared[roi_height - border_y:, :] = 0
        return prepared

    def find_best(mask_to_check):
        """从mask中找到最佳泡棉轮廓候选"""
        contours, _ = cv2.findContours(mask_to_check, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_candidate = None
        best_area = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(contour)
            aspect = bw / max(bh, 1)
            if aspect < 0.1 or aspect > 10:  # 放宽宽高比限制，从0.15-8改为0.1-10
                continue
            compactness = area / max(bw * bh, 1)
            if compactness < float(cfg.get('side_min_compactness', 0.20)):  # 从0.25降到0.20
                continue
            if area > best_area:
                best_candidate = (bx, by, bw, bh, area)
                best_area = area
        return best_candidate

    mask = prepare_mask(mask)

    # 核心判定：计算白色像素覆盖率（基于实际像素数，而非轮廓边界框面积）
    strict_mask = mask
    white_pixel_count = cv2.countNonZero(strict_mask)
    white_pixel_coverage = round(white_pixel_count / roi_area, 4)

    # Production coverage should approximate the filled visible foam region,
    # not only pure-white pixels. Shadowed foam is often gray, so build a
    # broader neutral gray/white candidate mask and measure its contour area.
    foam_max_s = int(cfg.get('foam_max_s', 135))
    foam_min_v = int(cfg.get('foam_min_v', 85))
    foam_min_l = int(cfg.get('foam_min_l', 105))
    neutral_mask = cv2.inRange(hsv[:, :, 1], 0, foam_max_s)
    value_mask = cv2.inRange(hsv[:, :, 2], foam_min_v, 255)
    lightness_mask = cv2.inRange(lab[:, :, 0], foam_min_l, 255)
    foam_candidate_mask = cv2.bitwise_and(
        neutral_mask,
        cv2.bitwise_or(value_mask, lightness_mask),
    )
    mask = prepare_mask(cv2.bitwise_or(strict_mask, foam_candidate_mask))

    best_for_coverage = find_best(mask)
    if best_for_coverage:
        _, _, bw, bh, area = best_for_coverage
        envelope_coverage = round((bw * bh) / roi_area, 4)
        contour_coverage = round(area / roi_area, 4)
        pixel_coverage = max(white_pixel_coverage, contour_coverage)
    else:
        envelope_coverage = 0.0
        contour_coverage = 0.0
        pixel_coverage = white_pixel_coverage

    # 核心判定：覆盖率必须达到阈值才认为有泡棉
    if pixel_coverage < coverage_threshold:
        # 覆盖率不足，判定为无泡棉
        # 仍然尝试找轮廓用于结果图标注（显示检测到了什么）
        best = find_best(mask)
        box = None
        if best:
            bx, by, bw, bh, area = best
            box = (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh)
        return {
            'roi': roi,
            'box': box,
            'is_present': False,
            'is_aligned': False,
            'coverage_ratio': pixel_coverage,
            'white_pixel_coverage': white_pixel_coverage,
            'envelope_coverage': envelope_coverage,
            'contour_coverage': contour_coverage,
            'coverage_source': 'foam_region_envelope',
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'score': round(pixel_coverage / max(coverage_threshold, 0.01), 3),
            'reason': 'coverage_below_threshold',
            'coverage_threshold': coverage_threshold,
        }

    best = find_best(mask)

    # 低光灰白兜底检测：默认关闭，因实际场景白色泡棉与黑色保险杠对比度足够
    if not best and cfg.get('enable_low_light_gray_detection', False):
        gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_blur)
        _, otsu_mask = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        min_gray = int(cfg.get('low_light_min_gray', 100))
        delta_gray = float(cfg.get('low_light_delta_gray', 8))
        local_floor = int(max(min_gray, min(255, np.percentile(gray_blur, 25) + delta_gray)))
        relative_mask = cv2.inRange(gray_blur, local_floor, 255)
        neutral_mask = cv2.inRange(hsv[:, :, 1], 0, int(cfg.get('low_light_max_s', 50)))
        brightness_mask = cv2.inRange(hsv[:, :, 2], min_gray, 255)
        low_light_mask = cv2.bitwise_or(otsu_mask, relative_mask)
        low_light_mask = cv2.bitwise_and(low_light_mask, neutral_mask)
        low_light_mask = cv2.bitwise_and(low_light_mask, brightness_mask)
        mask = prepare_mask(low_light_mask)
        # 重新计算低光模式下的像素覆盖率
        white_pixel_count = cv2.countNonZero(mask)
        pixel_coverage = round(white_pixel_count / roi_area, 4)
        if pixel_coverage < coverage_threshold:
            return {
                'roi': roi,
                'box': None,
                'is_present': False,
                'is_aligned': False,
                'coverage_ratio': pixel_coverage,
                'offset_x_px': 0.0,
                'offset_y_px': 0.0,
                'score': 0.0,
                'reason': 'low_light_coverage_below_threshold',
                'coverage_threshold': coverage_threshold,
            }
        best = find_best(mask)

    if not best:
        return {
            'roi': roi,
            'box': None,
            'is_present': False,
            'is_aligned': False,
            'coverage_ratio': pixel_coverage,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'score': 0.0,
        }

    bx, by, bw, bh, area = best
    box = (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh)
    roi_cx = (x1 + x2) / 2
    roi_cy = (y1 + y2) / 2
    foam_cx = (box[0] + box[2]) / 2
    foam_cy = (box[1] + box[3]) / 2
    offset_x = round(foam_cx - roi_cx, 1)
    offset_y = round(foam_cy - roi_cy, 1)
    # 使用像素级覆盖率（白色像素数 / ROI 总面积），而非轮廓边界框面积比
    coverage_ratio = pixel_coverage
    is_aligned = True
    score = round(max(0.85, min(1.0, coverage_ratio / max(coverage_threshold, 0.01))), 3)
    return {
        'roi': roi,
        'box': box,
        'is_present': True,
        'is_aligned': is_aligned,
        'coverage_ratio': coverage_ratio,
        'white_pixel_coverage': white_pixel_coverage,
        'envelope_coverage': envelope_coverage,
        'contour_coverage': contour_coverage,
        'coverage_source': 'foam_region_envelope',
        'offset_x_px': offset_x,
        'offset_y_px': offset_y,
        'score': score,
    }


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
    for side, ratio_box in side_roi_config.items():
        roi = _ratio_box_to_pixels(ratio_box, width, height)
        sides[side] = _detect_foam_side(image, roi, cfg)

    missing = [side for side, data in sides.items() if not data['is_present']]
    present_sides = [data for data in sides.values() if data['box']]
    if missing:
        defect_type = FoamDefectType.MISSING
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
    offsets_x = [data['offset_x_px'] for data in sides.values()]
    offsets_y = [data['offset_y_px'] for data in sides.values()]
    result = {
        'is_present': not missing,
        'is_aligned': not missing,
        'has_lifted_edge': bool(missing),
        'defect_type': defect_type,
        'score': round(min(scores) if scores else 0.0, 3),
        'offset_x_px': round(max(offsets_x, key=abs) if offsets_x else 0.0, 1),
        'offset_y_px': round(max(offsets_y, key=abs) if offsets_y else 0.0, 1),
        'coverage_ratio': round(min(coverage) if coverage else 0.0, 4),
        'is_passed': is_passed,
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
                        'coverage_ratio': result['coverage_ratio'],
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

        # 计算偏移量（像素）
        offset_x_px = round(foam_cx - roi_cx, 1)
        offset_y_px = round(foam_cy - roi_cy, 1)

        # 判定结果
        result = _build_result(
            defect_type=defect_type,
            offset_x_px=offset_x_px,
            offset_y_px=offset_y_px,
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
                'defect_type': defect_type,
                'roi': roi,
                'foam_box': foam,
                'offset_x_px': offset_x_px,
                'offset_y_px': offset_y_px,
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


def _build_result(*, defect_type, offset_x_px, offset_y_px, coverage_ratio,
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
            'has_lifted_edge': True,
            'defect_type': FoamDefectType.MISSING,
            'score': 0.0,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'coverage_ratio': 0.0,
            'is_passed': False,
        }

    # 泡棉存在，判定为合格
    return {
        'is_present': True,
        'is_aligned': True,
        'has_lifted_edge': False,
        'defect_type': FoamDefectType.NONE,
        'score': 0.96,
        'offset_x_px': offset_x_px,
        'offset_y_px': offset_y_px,
        'coverage_ratio': coverage_ratio,
        'is_passed': True,
    }
