"""泡棉贴附检测算法（2D 检测相机）。

检测场景
--------
- 检测对象：汽车保险杠表面贴附的**白色泡棉**
- 相机类型：海康 MV-CS050-10GC（500万像素，10GigE），固定俯视安装
- 触发方式：装箱机器人完成泡棉贴附动作后，由 PLC 触发拍照

判定规则（简化策略）
--------------------
只要在 ROI 区域内检测到白色泡棉即判定合格：
  - 泡棉存在  → is_present=True
  - 位置对齐  → is_aligned=True（存在即 OK，不依赖偏移量二次判 NG）
  - 边缘起翘  → has_lifted_edge=False（存在即无起翘，不额外计算边缘）
  - 综合结论  → is_passed=True
泡棉缺失（漏贴）→ 三项全 NG，is_passed=False，触发报警。

前端展示三项指标卡：存在 / 对齐 / 起翘，数据来自算法返回字段，与 PLC 判定结论一致。
"""
import cv2
import numpy as np
from django.db import models

from . import image_io


def _detect_foam_in_image(image, roi):
    """在真实图像中检测泡棉位置。
    
    针对汽车保险杠泡棉检测场景优化：
    - 黑色保险杠背景
    - 白色泡棉（左右各一片，呈不规则形状）
    - 泡棉与保险杠有明显颜色对比
    
    参数：
        image: BGR格式的图像 (numpy array)
        roi: 检测区域 (x1, y1, x2, y2)
    
    返回：
        所有泡棉区域的联合边界框 (x1, y1, x2, y2) 或 None（未检测到）
    """
    # 提取ROI区域
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    
    # 转换到灰度图和HSV色彩空间
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    
    # 策略1: 使用大津法（OTSU）自适应阈值分离前景（白色泡棉）和背景（黑色保险杠）
    # 对于黑白对比强烈的场景，OTSU 效果最好
    _, mask_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 策略2: 固定阈值作为补充（检测明显的白色区域）
    # 白色泡棉的灰度值通常 > 180
    _, mask_fixed = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    
    # 策略3: 自适应阈值（处理光照不均的情况）
    mask_adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 21, -10
    )
    
    # 组合多个策略的结果
    mask_combined = cv2.bitwise_or(mask_otsu, mask_fixed)
    mask_combined = cv2.bitwise_or(mask_combined, mask_adaptive)
    
    # 形态学操作：
    # 1. 闭运算：连接断裂的泡棉区域（因为泡棉可能有纹理或折痕）
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel_close, iterations=3)
    
    # 2. 开运算：去除小噪点
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_OPEN, kernel_open)
    
    # 查找轮廓
    contours, _ = cv2.findContours(mask_combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # ROI面积和最小检测阈值
    roi_area = roi_width * roi_height
    min_area = roi_area * 0.03  # 降低到3%，因为单片泡棉可能较小
    max_area = roi_area * 0.9   # 最多占90%
    
    # 收集所有符合条件的泡棉轮廓
    valid_foam_contours = []
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        # 面积过滤
        if area < min_area or area > max_area:
            continue
        
        # 获取边界框
        bx, by, bw, bh = cv2.boundingRect(contour)
        
        # 宽高比检查（泡棉形状相对规则，不会是极端的长条）
        aspect_ratio = bw / max(bh, 1)
        if aspect_ratio > 10 or aspect_ratio < 0.1:  # 10:1 到 1:10
            continue
        
        # 紧凑度检查（避免选中过于分散的区域）
        bbox_area = bw * bh
        compactness = area / max(bbox_area, 1)
        if compactness < 0.25:  # 降低紧凑度要求，因为泡棉可能不规则
            continue
        
        valid_foam_contours.append(contour)
    
    if not valid_foam_contours:
        return None
    
    # 如果检测到多个泡棉区域（左右两片），计算它们的联合边界框
    all_points = np.vstack(valid_foam_contours)
    x, y, w, h = cv2.boundingRect(all_points)
    
    # 转换回原图坐标系
    foam_x1 = x1 + x
    foam_y1 = y1 + y
    foam_x2 = foam_x1 + w
    foam_y2 = foam_y1 + h
    
    return (foam_x1, foam_y1, foam_x2, foam_y2)


def _ratio_box_to_pixels(ratio_box, width, height):
    x1_r, y1_r, x2_r, y2_r = [float(v) for v in ratio_box]
    x1 = int(round(width * max(0.0, min(1.0, x1_r))))
    y1 = int(round(height * max(0.0, min(1.0, y1_r))))
    x2 = int(round(width * max(0.0, min(1.0, x2_r))))
    y2 = int(round(height * max(0.0, min(1.0, y2_r))))
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _resolve_side_roi_config(cfg, position_index):
    foam_rois = cfg.get('foam_rois') or {}
    if not isinstance(foam_rois, dict):
        return None
    key = str(position_index)
    rois = foam_rois.get(key) or foam_rois.get(position_index)
    if not rois and {'left', 'right'} <= set(foam_rois.keys()):
        rois = foam_rois
    if not isinstance(rois, dict):
        return None
    if not rois.get('left') or not rois.get('right'):
        return None
    return {'left': rois['left'], 'right': rois['right']}


def _detect_foam_side(image, roi, cfg):
    x1, y1, x2, y2 = roi
    roi_img = image[y1:y2, x1:x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    roi_area = max(roi_width * roi_height, 1)
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

    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(roi_img, cv2.COLOR_BGR2LAB)
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

    min_v = int(cfg.get('white_min_v', 170))
    max_s = int(cfg.get('white_max_s', 80))
    min_l = int(cfg.get('white_min_l', 175))
    white_hsv = cv2.inRange(hsv, (0, 0, min_v), (180, max_s, 255))
    white_lab = cv2.inRange(lab[:, :, 0], min_l, 255)
    mask = cv2.bitwise_or(white_hsv, white_lab)

    green_mask = cv2.inRange(hsv, (35, 40, 40), (100, 255, 255))

    border_ratio = float(cfg.get('ignore_border_ratio', 0.04))
    border_x = int(round(roi_width * max(0.0, min(0.25, border_ratio))))
    border_y = int(round(roi_height * max(0.0, min(0.25, border_ratio))))

    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    min_area = roi_area * float(cfg.get('side_min_area_ratio', 0.08))
    max_area = roi_area * float(cfg.get('side_max_area_ratio', 0.95))

    def prepare_mask(raw_mask):
        prepared = cv2.bitwise_and(raw_mask, cv2.bitwise_not(green_mask))
        if border_x > 0:
            prepared[:, :border_x] = 0
            prepared[:, roi_width - border_x:] = 0
        if border_y > 0:
            prepared[:border_y, :] = 0
            prepared[roi_height - border_y:, :] = 0
        prepared = cv2.morphologyEx(prepared, cv2.MORPH_CLOSE, kernel_close, iterations=2)
        prepared = cv2.morphologyEx(prepared, cv2.MORPH_OPEN, kernel_open)
        if border_x > 0:
            prepared[:, :border_x] = 0
            prepared[:, roi_width - border_x:] = 0
        if border_y > 0:
            prepared[:border_y, :] = 0
            prepared[roi_height - border_y:, :] = 0
        return prepared

    def find_best(mask_to_check):
        contours, _ = cv2.findContours(mask_to_check, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_candidate = None
        best_area = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(contour)
            aspect = bw / max(bh, 1)
            if aspect < 0.15 or aspect > 8:
                continue
            compactness = area / max(bw * bh, 1)
            if compactness < float(cfg.get('side_min_compactness', 0.25)):
                continue
            if area > best_area:
                best_candidate = (bx, by, bw, bh, area)
                best_area = area
        return best_candidate

    mask = prepare_mask(mask)
    best = find_best(mask)

    if not best and cfg.get('enable_low_light_gray_detection', True):
        # 低光场景下泡棉可能不是高亮白色，而是低饱和灰白块。
        # 用 CLAHE + OTSU/相对亮度找局部灰白区域，并继续排除绿色/彩色背景。
        gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_blur)
        _, otsu_mask = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        min_gray = int(cfg.get('low_light_min_gray', 45))
        delta_gray = float(cfg.get('low_light_delta_gray', 8))
        local_floor = int(max(min_gray, min(255, np.percentile(gray_blur, 25) + delta_gray)))
        relative_mask = cv2.inRange(gray_blur, local_floor, 255)
        neutral_mask = cv2.inRange(hsv[:, :, 1], 0, int(cfg.get('low_light_max_s', 115)))
        brightness_mask = cv2.inRange(hsv[:, :, 2], min_gray, 255)
        low_light_mask = cv2.bitwise_or(otsu_mask, relative_mask)
        low_light_mask = cv2.bitwise_and(low_light_mask, neutral_mask)
        low_light_mask = cv2.bitwise_and(low_light_mask, brightness_mask)
        mask = prepare_mask(low_light_mask)
        best = find_best(mask)

    if not best:
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

    bx, by, bw, bh, area = best
    box = (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh)
    roi_cx = (x1 + x2) / 2
    roi_cy = (y1 + y2) / 2
    foam_cx = (box[0] + box[2]) / 2
    foam_cy = (box[1] + box[3]) / 2
    offset_x = round(foam_cx - roi_cx, 1)
    offset_y = round(foam_cy - roi_cy, 1)
    coverage_ratio = round((bw * bh) / roi_area, 4)
    # 当前现场策略：泡棉贴在保险杠上，2D 视觉只做“白色泡棉是否存在”
    # 的强判定。只要在当前 ROI 内检测到泡棉，前端仍展示“存在 / 对齐 /
    # 起翘”三项，但对齐与起翘直接随存在判 OK，避免复杂阈值导致误报。
    coverage_threshold = float(cfg.get('coverage_threshold', 0.3))
    is_aligned = True
    score = round(max(0.85, min(1.0, coverage_ratio / max(coverage_threshold, 0.01))), 3)
    return {
        'roi': roi,
        'box': box,
        'is_present': True,
        'is_aligned': is_aligned,
        'coverage_ratio': coverage_ratio,
        'offset_x_px': offset_x,
        'offset_y_px': offset_y,
        'score': score,
    }


def _inspect_calibrated_sides(image, side_roi_config, position_index, cfg):
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

        本方法由 PLC 触发相机拍照后调用，用于检测：
          1. 泡棉是否存在（is_present）- 检测漏贴
          2. 泡棉位置是否对齐（is_aligned）- 当前策略：存在即 OK
          3. 泡棉边缘是否起翘（has_lifted_edge）- 当前策略：存在即不起翘

        参数：
            position_index: 装箱位置编号（0-based），用于区分不同产品或不同装箱位
            inspection_config: 检测参数配置字典：
                - score_threshold (float, default 0.8): 综合评分阈值
                - coverage_threshold (float, default 0.75): ROI 覆盖率阈值
                - max_offset_px (int, default 30): 允许的最大像素偏移
            image: 相机拍摄的实际图像（numpy array，BGR格式）
                   - 模拟模式下可为 None
                   - 生产模式下由相机适配器传入
            camera_image_path: 原始图像路径（用于记录）
            simulated_pass: 仅模拟模式有效，强制通过/失败

        返回：
            dict: 检测结果，包含以下字段：
                - is_present (bool): 泡棉是否存在
                - is_aligned (bool): 泡棉位置是否对齐
                - has_lifted_edge (bool): 是否检测到边缘起翘
                - defect_type (str): 缺陷类型（NONE/MISSING/MISALIGNED/LIFTED_EDGE）
                - score (float): 综合评分 (0.0-1.0)
                - is_passed (bool): 最终判定（合格/不合格）
                - offset_x_px (float): X方向偏移（像素）
                - offset_y_px (float): Y方向偏移（像素）
                - coverage_ratio (float): 泡棉覆盖率 (0.0-1.0)
                - original_image (str): 原始图像路径
                - result_image (str): 标注结果图路径
                - roi (tuple): ROI检测区域 (x1, y1, x2, y2)
                - foam_box (tuple): 检测到的泡棉位置 (x1, y1, x2, y2)
                - result_data (dict): 详细检测数据（用于调试和追溯）

        工作流程：
            1. PLC 触发拍照 -> 相机采集图像
            2. 调用本方法进行检测
            3. 返回检测结果
            4. 根据 is_passed 判断：
               - True: 向 PLC 发送"工序完成"信号
               - False: 系统报警并锁定工位
        """
        if not self.simulate and image is None:
            raise NotImplementedError(
                '真实泡棉检测算法尚未接入。需要实现基于海康工业相机的图像处理算法。'
            )

        # 解析检测配置
        cfg = inspection_config or {}
        score_threshold = float(cfg.get('score_threshold', 0.8))
        coverage_threshold = float(cfg.get('coverage_threshold', 0.75))
        max_offset_px = int(cfg.get('max_offset_px', 30))
        side_details = None

        # 1) 确定本次检测的缺陷类型（模拟模式）
        if simulated_pass:
            defect_type = FoamDefectType.NONE
        else:
            # 新版简化规则只区分“存在/缺失”。模拟失败统一表示漏贴。
            defect_type = FoamDefectType.MISSING

        # 2) 获取图像（真实相机图像或模拟图像）
        using_camera_image = image is not None
        if using_camera_image:
            # 使用真实相机图像
            scene = image
            height, width = scene.shape[:2]
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
                    'result_data': {
                        'algorithm': 'camera_foam_inspector',
                        'foam_target': 'bumper',
                        'decision_rule': 'present_means_aligned_and_not_lifted',
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
            # roi_ratio: (x1_ratio, y1_ratio, x2_ratio, y2_ratio)，每个值在 [0, 1] 范围
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
            foam = _detect_foam_in_image(scene, roi)
            
            # 如果没有检测到泡棉，设置为缺失状态；检测到即合格。
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

        # 3) 计算量化指标
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

        # 4) 判定结果
        result = _build_result(
            defect_type=defect_type,
            offset_x_px=offset_x_px,
            offset_y_px=offset_y_px,
            coverage_ratio=coverage_ratio,
            score_threshold=score_threshold,
            coverage_threshold=coverage_threshold,
            max_offset_px=max_offset_px,
        )
        # 5) 保存原图和标注结果图
        original_path, w, h = image_io.save_image(
            scene, f'foam_raw_p{position_index}'
        )
        annotated = image_io.annotate_foam(scene, roi, foam, result)
        result_path, _, _ = image_io.save_image(
            annotated, f'foam_result_p{position_index}', rel_dir='vision/results',
        )

        # 6) 构建完整返回结果
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
                'decision_rule': 'present_means_aligned_and_not_lifted',
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

    # 当前生产算法简化为“存在即 OK”。保留对齐/起翘字段供前端和 PLC
    # 使用，但不再用偏移、覆盖率、边缘状态二次判 NG。
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
