"""OpenCV/NumPy 图像生成与标注工具。

无真实相机时，用程序化方式生成模拟相机画面，并在画面上绘制 ROI 检测框、
标注文字、深度伪彩色和补偿向量箭头，便于在页面上可视化视觉结果。

真实相机接入后，这里的 generate_* 函数可替换为从相机/文件读取的真实图像，
draw_* / save_image 等标注与归档函数可继续复用。
"""
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.utils import timezone


# 颜色常量（BGR，OpenCV 顺序）。
COLOR_OK = (76, 175, 80)        # 绿
COLOR_FAIL = (0, 0, 220)        # 红（注意：OpenCV 为 BGR，纯红 = (0,0,220)）
COLOR_WARN = (0, 170, 240)      # 橙黄
COLOR_ROI = (235, 180, 40)      # 蓝
COLOR_TEXT = (255, 255, 255)    # 白
COLOR_AXIS = (255, 255, 0)      # 青
COLOR_MISSING = (128, 0, 128)   # 紫（泡棉缺失标注）


def _media_path(rel_dir):
    """返回 media 下的绝对目录，必要时创建。"""
    date_dir = timezone.now().strftime('%Y/%m/%d')
    abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir, date_dir)
    os.makedirs(abs_dir, exist_ok=True)
    return abs_dir, os.path.join(rel_dir, date_dir).replace('\\', '/')


def save_image(image, prefix, rel_dir='vision/captures'):
    """保存图像到 media，返回 (相对路径, 宽, 高)。"""
    abs_dir, rel = _media_path(rel_dir)
    stamp = timezone.now().strftime('%H%M%S_%f')
    filename = f'{prefix}_{stamp}.png'
    abs_path = os.path.join(abs_dir, filename)
    cv2.imwrite(abs_path, image)
    h, w = image.shape[:2]
    return f'{rel}/{filename}', w, h


def _put_label(img, text, org, color, scale=0.5, thickness=1):
    """带背景底的文字标注，支持中文显示。"""
    # 转换为PIL图像以支持中文
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    
    # 尝试使用系统中文字体，如果失败则使用默认字体
    try:
        # Windows系统中文字体
        font_size = int(20 * scale)
        font = ImageFont.truetype("msyh.ttc", font_size)  # 微软雅黑
    except:
        try:
            font = ImageFont.truetype("simsun.ttc", font_size)  # 宋体
        except:
            font = ImageFont.load_default()
    
    x, y = org
    # 获取文本尺寸
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    # 绘制背景矩形
    draw.rectangle([x, y - th - 4, x + tw + 6, y + 2], fill=(30, 30, 30))
    
    # 绘制文字（PIL使用RGB颜色顺序，需要转换）
    rgb_color = (color[2], color[1], color[0])
    draw.text((x + 3, y - th - 2), text, font=font, fill=rgb_color)
    
    # 转换回OpenCV格式
    img[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def draw_roi(img, box, color=COLOR_ROI, label=None, thickness=2):
    """在图上画 ROI 矩形框（box=(x1,y1,x2,y2)）和可选标签。"""
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    if label:
        _put_label(img, label, (x1, max(y1 - 4, 14)), COLOR_TEXT)
    return img


# ---------------- 2D 检测相机：泡棉场景 ----------------

# 每个检测位置的背景色偏移，使不同位置在模拟图中有视觉差异（BGR 偏移量）
_POSITION_BG_TINTS = [
    (0, 0, 0),       # 位置 0：标准灰
    (0, 8, 0),       # 位置 1：略带绿
    (8, 0, 0),       # 位置 2：略带蓝
    (0, 0, 8),       # 位置 3：略带红
]


def generate_foam_scene(position_index=0, passed=True, defect_type=None,
                        width=640, height=480):
    """生成模拟的 2D 检测相机画面：保险杠表面 + 一片泡棉。

    参数：
        position_index: 贴附位置编号，影响背景色调和位置标识文字。
        passed: 是否合格。
        defect_type: 缺陷类型字符串（'NONE'/'MISALIGNED'/'LIFTED_EDGE'/'MISSING'）。
    返回 (image, roi_box, foam_box)。
    """
    # --- 背景：保险杠曲面渐变 ---
    img = np.full((height, width, 3), 70, dtype=np.uint8)
    grad = np.linspace(50, 110, width, dtype=np.uint8)
    img[:] = np.dstack([grad] * 3)[0]

    # 根据 position_index 叠加轻微色调，区分不同检测位置
    tint = _POSITION_BG_TINTS[position_index % len(_POSITION_BG_TINTS)]
    img = np.clip(img.astype(np.int16) + np.array(tint, dtype=np.int16), 0, 255).astype(np.uint8)

    cv2.rectangle(img, (40, 40), (width - 40, height - 40), (90, 95, 100), -1)

    # 位置编号标识（右上角）
    _put_label(img, f'POS #{position_index}', (width - 80, 22), COLOR_AXIS, scale=0.45)

    # ROI：期望泡棉应处的检测区域。
    roi = (width // 2 - 110, height // 2 - 80, width // 2 + 110, height // 2 + 80)

    # 泡棉缺失时不画泡棉
    defect_str = str(defect_type) if defect_type else ''
    if 'MISSING' in defect_str:
        # 返回空泡棉区域（与 ROI 中心重合，面积为 0）
        cx, cy = width // 2, height // 2
        foam = (cx, cy, cx, cy)
        return img, roi, foam

    # 偏移量：根据 position_index 和合格状态计算
    if passed or 'NONE' in defect_str:
        cx, cy = width // 2, height // 2
    elif 'MISALIGNED' in defect_str:
        # 不同位置偏移方向不同
        offsets = [(70, 45), (-60, 50), (80, -40), (-55, -50)]
        dx, dy = offsets[position_index % len(offsets)]
        cx, cy = width // 2 + dx, height // 2 + dy
    else:
        # LIFTED_EDGE：位置居中，但有起翘
        cx, cy = width // 2, height // 2

    fw, fh = 150, 110
    foam = (cx - fw // 2, cy - fh // 2, cx + fw // 2, cy + fh // 2)

    # 画泡棉主体（浅灰块）
    cv2.rectangle(img, (foam[0], foam[1]), (foam[2], foam[3]), (200, 205, 210), -1)
    cv2.rectangle(img, (foam[0], foam[1]), (foam[2], foam[3]), (150, 150, 155), 2)

    if 'LIFTED_EDGE' in defect_str:
        # 模拟起翘：泡棉一角翘起的阴影三角 + 高光边
        pts = np.array([[foam[2] - 45, foam[1]], [foam[2], foam[1]],
                        [foam[2], foam[1] + 45]], dtype=np.int32)
        cv2.fillPoly(img, [pts], (120, 120, 130))
        # 翘起高光线
        cv2.line(img, (foam[2] - 45, foam[1]), (foam[2], foam[1] + 45),
                 (230, 230, 235), 1)

    return img, roi, foam


def annotate_foam(img, roi, foam, result):
    """在泡棉画面上叠加 ROI、检测框与判定标注，返回结果图。

    标注内容：
    - ROI 检测区（蓝色框）
    - 泡棉实际位置（绿/红色框）
    - 左上角：判定结果 + 缺陷类型
    - 左下角：存在/对齐/起翘状态 + 偏移量 + 覆盖率
    - 不合格时：对角线 × 标记
    """
    out = img.copy()
    h = height_of(out)
    passed = result.get('is_passed', False)
    defect_type = result.get('defect_type', '')
    is_missing = not result.get('is_present', True)
    sides = result.get('sides') or result.get('result_data', {}).get('sides') or {}

    # 有左右独立 ROI 时，只画左右 ROI，避免把两个框合成一个横跨中间的大框。
    if not sides:
        draw_roi(out, roi, color=COLOR_ROI, label='ROI 检测区')
    else:
        # 左右ROI区域标注的中文标签
        side_labels = {'left': '泡棉左区', 'right': '泡棉右区'}
        for side, data in sides.items():
            side_roi = data.get('roi')
            side_box = data.get('box')
            side_label = side_labels.get(side, side)
            
            # 始终绘制配方定义的ROI区域框（蓝色）
            if side_roi:
                draw_roi(out, tuple(side_roi), color=COLOR_ROI, label=side_label, thickness=2)
            
            # 如果检测到泡棉，再绘制泡棉实际位置框（绿色/红色）
            if side_box:
                box_color = COLOR_OK if data.get('is_aligned') else COLOR_FAIL
                draw_roi(out, tuple(side_box), color=box_color, label=None, thickness=2)
            elif side_roi:
                # 如果ROI内未检测到泡棉，标注缺失警告
                draw_roi(out, tuple(side_roi), color=COLOR_MISSING, label=f'{side_label} 缺失!', thickness=2)

    # 泡棉框（左右独立 ROI 已在上方分别画出，非 side 模式才画总泡棉框）
    if not sides and not is_missing and foam and (foam[2] - foam[0]) > 0:
        color = COLOR_OK if passed else COLOR_FAIL
        draw_roi(out, foam, color=color, label='泡棉', thickness=2)
    elif not sides and is_missing:
        # 缺失：在 ROI 区域画紫色虚线框提示
        draw_roi(out, roi, color=COLOR_MISSING, label='泡棉缺失!', thickness=2)

    # 不合格时：无 side 详情才画总 ROI 的红叉；有 side 详情时分别画在问题 ROI 内。
    if not passed:
        failed_rois = []
        if sides:
            for data in sides.values():
                side_roi = data.get('roi')
                if side_roi and (not data.get('is_present') or not data.get('is_aligned', True)):
                    failed_rois.append(tuple(side_roi))
        else:
            failed_rois.append(roi)
        for rx1, ry1, rx2, ry2 in failed_rois:
            cv2.line(out, (rx1, ry1), (rx2, ry2), COLOR_FAIL, 2, cv2.LINE_AA)
            cv2.line(out, (rx2, ry1), (rx1, ry2), COLOR_FAIL, 2, cv2.LINE_AA)

    # 左上角：判定标题行
    verdict = '合格 ✓' if passed else '不合格 ✗'
    verdict_color = COLOR_OK if passed else COLOR_FAIL
    _put_label(out, f'判定: {verdict}', (12, 28), verdict_color, scale=0.6, thickness=2)

    # 缺陷类型（第二行）
    defect_label = _defect_label(str(defect_type))
    _put_label(out, f'缺陷: {defect_label}', (12, 52), COLOR_WARN, scale=0.5)

    # 分数
    score_val = result.get('score', 0)
    _put_label(out, f'score={score_val:.3f}', (12, 72), COLOR_WARN, scale=0.45)

    # 左下角：详细状态行
    ox = result.get('offset_x_px', 0)
    oy = result.get('offset_y_px', 0)
    cov = result.get('coverage_ratio', 0)
    _put_label(
        out,
        f"存在:{'是' if result.get('is_present') else '否'}  "
        f"对齐:{'OK' if result.get('is_aligned') else 'NG'}  "
        f"起翘:{'NG' if result.get('has_lifted_edge') else 'OK'}",
        (12, h - 32), COLOR_TEXT, scale=0.45,
    )
    _put_label(
        out,
        f'偏移 X={ox:+.0f}px Y={oy:+.0f}px  覆盖率={cov:.1%}',
        (12, h - 14), COLOR_TEXT, scale=0.45,
    )
    return out


def _defect_label(defect_type_str):
    """将 FoamDefectType 值转为中文显示标签。"""
    mapping = {
        'NONE': '无缺陷',
        'MISALIGNED': '位置偏移',
        'LIFTED_EDGE': '边缘起翘',
        'MISSING': '泡棉缺失',
    }
    for key, label in mapping.items():
        if key in defect_type_str:
            return label
    return defect_type_str


# ---------------- 深度相机：料架场景 ----------------
def generate_depth_scene(side='LEFT', layer_count=3, width=640, height=480):
    """生成模拟深度图并转伪彩色：料架立柱 + 装箱区域 + 分层线。

    参数：
        side: 'LEFT' 或 'RIGHT'
        layer_count: 料架层数，默认 3（与实际设备一致），在装箱区域绘制等距分层线
    返回 (color_depth_image, pillar_roi, region_roi)。
    """
    # 构造渐变深度场（远近不同），叠加立柱与装箱区域。
    yy, xx = np.mgrid[0:height, 0:width]
    depth = (120 + 0.12 * yy + 0.05 * xx).astype(np.float32)

    # 立柱：作为定位基准，深度较近（值小）。
    pillar_x = 90 if side == 'LEFT' else width - 150
    pillar = (pillar_x, 60, pillar_x + 60, height - 60)
    depth[pillar[1]:pillar[3], pillar[0]:pillar[2]] -= 60

    # 装箱区域：略微凹陷。
    region = (pillar_x + 90, 120, pillar_x + 320, height - 120)
    region = (min(region[0], width - 60), region[1],
              min(region[2], width - 20), region[3])
    depth[region[1]:region[3], region[0]:region[2]] += 30

    # 分层深度梯度：在装箱区域内每层叠加轻微深度差，模拟各层高度不同
    if layer_count > 1:
        layer_h = (region[3] - region[1]) // layer_count
        for i in range(layer_count):
            y1 = region[1] + i * layer_h
            y2 = min(region[1] + (i + 1) * layer_h, region[3])
            depth[y1:y2, region[0]:region[2]] += float(i) * 8

    depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

    # 在伪彩色图上绘制分层分割线（白色虚线）
    if layer_count > 1:
        layer_h = (region[3] - region[1]) // layer_count
        for i in range(1, layer_count):
            ly = region[1] + i * layer_h
            # 虚线效果：每 8px 画 4px
            for sx in range(region[0], region[2], 8):
                cv2.line(color, (sx, ly), (min(sx + 4, region[2]), ly),
                         (255, 255, 255), 1)
        # 右侧层编号标注
        lh = (region[3] - region[1]) // layer_count
        for i in range(layer_count):
            ly = region[1] + i * lh + lh // 2
            _put_label(color, f'L{layer_count - i}', (region[2] + 4, ly),
                       COLOR_TEXT, scale=0.4)

    return color, pillar, region


def annotate_depth(img, pillar, region, side, offsets,
                   confidence=None, layer_heights=None, recipe_matched=True):
    """在深度伪彩色图上叠加立柱基准 ROI、装箱区 ROI 与标注。

    标注内容：
    - 立柱基准框（青色）
    - 装箱区 ROI 框（蓝色）
    - X/Y 偏差箭头 + Z 文字
    - 左上角第一行：料架侧别 + 补偿值
    - 左上角第二行：置信度 conf=0.93
    - 底部：各层实测高度列表
    - recipe_matched=False 时：顶部橙色警告条
    """
    out = img.copy()
    h = height_of(out)
    w = out.shape[1]

    # 配方不匹配：顶部橙色警告条
    if not recipe_matched:
        cv2.rectangle(out, (0, 0), (w, 22), (0, 140, 255), -1)
        _put_label(out, '! 层高/层距超差 — 配方校验不通过 !',
                   (w // 2 - 120, 16), (255, 255, 255), scale=0.5, thickness=1)

    draw_roi(out, pillar, color=COLOR_AXIS, label='立柱基准')
    draw_roi(out, region, color=COLOR_ROI, label='装箱区 ROI')

    # 补偿向量：从装箱区中心画箭头表示 X/Y 偏差。
    cx = (region[0] + region[2]) // 2
    cy = (region[1] + region[3]) // 2
    ox = float(offsets.get('offset_x', 0))
    oy = float(offsets.get('offset_y', 0))
    oz = float(offsets.get('offset_z', 0))
    end = (int(cx + ox * 8), int(cy + oy * 8))
    cv2.arrowedLine(out, (cx, cy), end, COLOR_TEXT, 2, tipLength=0.3)
    cv2.circle(out, (cx, cy), 4, COLOR_TEXT, -1)

    # 左上角：侧别 + 补偿值
    side_label = '左侧' if side == 'LEFT' else '右侧'
    top_y = 28 if recipe_matched else 42  # 有警告条时下移
    _put_label(out, f'{side_label}料架补偿', (12, top_y), COLOR_AXIS,
               scale=0.6, thickness=2)
    _put_label(out, f'X={ox:+.2f}  Y={oy:+.2f}  Z={oz:+.2f} mm',
               (12, top_y + 20), COLOR_TEXT, scale=0.5)

    # 置信度（第三行）
    if confidence is not None:
        conf_color = COLOR_OK if confidence >= 0.80 else COLOR_WARN
        _put_label(out, f'置信度: {confidence:.2%}', (12, top_y + 40),
                   conf_color, scale=0.5)

    # 底部：各层实测高度
    if layer_heights:
        heights_str = '  '.join(f'L{i+1}:{v:.1f}' for i, v in enumerate(layer_heights))
        _put_label(out, f'层高(mm): {heights_str}', (12, h - 14),
                   COLOR_TEXT, scale=0.45)

    return out


def height_of(img):
    return img.shape[0]


class ImageIO:
    """图像归档辅助类（保留类形式以兼容既有引用）。"""

    @staticmethod
    def save(image, prefix, rel_dir='vision/captures'):
        return save_image(image, prefix, rel_dir)


# ---------------- 深度相机：双料架合并场景（单次拍摄）----------------

def generate_depth_scene_both(layer_count=3, width=1280, height=480):
    """生成单次拍摄覆盖左右双料架的宽幅深度图（1280x480）。

    硬件确认：3D 相机一次拍摄即可覆盖两个并列料架，此函数模拟该场景。
    图像左半区为左料架，右半区为右料架，中间留分界线。

    返回 (color_depth_image, rois_dict)。
    rois_dict = {
        'LEFT':  {'pillar': (x1,y1,x2,y2), 'region': (x1,y1,x2,y2)},
        'RIGHT': {'pillar': (x1,y1,x2,y2), 'region': (x1,y1,x2,y2)},
    }
    """
    half = width // 2
    yy, xx = np.mgrid[0:height, 0:width]
    depth = (120 + 0.12 * yy + 0.04 * xx).astype(np.float32)

    rois = {}
    for i, side in enumerate(('LEFT', 'RIGHT')):
        base_x = i * half
        pillar_x = base_x + 80
        pillar = (pillar_x, 60, pillar_x + 55, height - 60)
        depth[pillar[1]:pillar[3], pillar[0]:pillar[2]] -= 60

        region_x1 = pillar_x + 80
        region_x2 = min(base_x + half - 30, region_x1 + 280)
        region = (region_x1, 120, region_x2, height - 120)
        depth[region[1]:region[3], region[0]:region[2]] += 30

        if layer_count > 1:
            lh = (region[3] - region[1]) // layer_count
            for j in range(layer_count):
                y1 = region[1] + j * lh
                y2 = min(region[1] + (j + 1) * lh, region[3])
                depth[y1:y2, region[0]:region[2]] += float(j) * 8

        rois[side] = {'pillar': pillar, 'region': region}

    depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

    for side, roi_data in rois.items():
        region = roi_data['region']
        if layer_count > 1:
            lh = (region[3] - region[1]) // layer_count
            for i in range(1, layer_count):
                ly = region[1] + i * lh
                for sx in range(region[0], region[2], 8):
                    cv2.line(color, (sx, ly), (min(sx + 4, region[2]), ly),
                             (255, 255, 255), 1)
            for i in range(layer_count):
                ly = region[1] + i * lh + lh // 2
                _put_label(color, f'L{layer_count - i}',
                           (region[2] + 4, ly), COLOR_TEXT, scale=0.38)

    cv2.line(color, (half, 0), (half, height), (80, 80, 80), 2)
    return color, rois


def annotate_depth_both(img, rois, side_data, layer_count=3):
    """在双料架宽幅深度图上绘制左右两侧的定位标注。

    参数：
        img      : generate_depth_scene_both() 返回的图像
        rois     : rois_dict，含 LEFT/RIGHT 的 pillar/region
        side_data: {'LEFT': _analyse_side() 结果, 'RIGHT': ...}
    """
    out = img.copy()
    h = height_of(out)

    for side in ('LEFT', 'RIGHT'):
        data = side_data.get(side, {})
        roi_data = rois.get(side, {})
        pillar = roi_data.get('pillar')
        region = roi_data.get('region')
        if pillar is None or region is None:
            continue

        ox = float(data.get('offset_x', 0))
        oy = float(data.get('offset_y', 0))
        oz = float(data.get('offset_z', 0))
        recipe_matched = data.get('recipe_matched', True)
        confidence     = data.get('confidence')
        layer_heights  = data.get('layer_heights')

        if not recipe_matched:
            rx1, _, rx2, _ = region
            cv2.rectangle(out, (rx1, 0), (rx2, 20), (0, 140, 255), -1)
            _put_label(out, 'WARN:超差', (rx1 + 4, 16), (255, 255, 255), scale=0.38)

        draw_roi(out, pillar, color=COLOR_AXIS, label='立柱')
        side_cn = '左侧' if side == 'LEFT' else '右侧'
        draw_roi(out, region, color=COLOR_ROI, label=side_cn)

        cx = (region[0] + region[2]) // 2
        cy = (region[1] + region[3]) // 2
        end = (int(cx + ox * 8), int(cy + oy * 8))
        cv2.arrowedLine(out, (cx, cy), end, COLOR_TEXT, 2, tipLength=0.3)
        cv2.circle(out, (cx, cy), 4, COLOR_TEXT, -1)

        label_x = region[0] + 4
        top_y   = 28 if recipe_matched else 42
        _put_label(out, f'{side_cn}补偿', (label_x, top_y),
                   COLOR_AXIS, scale=0.55, thickness=2)
        _put_label(out, f'X={ox:+.2f} Y={oy:+.2f} Z={oz:+.2f}mm',
                   (label_x, top_y + 18), COLOR_TEXT, scale=0.42)

        if confidence is not None:
            conf_color = COLOR_OK if confidence >= 0.80 else COLOR_WARN
            _put_label(out, f'conf={confidence:.2%}',
                       (label_x, top_y + 34), conf_color, scale=0.42)

        if layer_heights:
            hs = ' '.join(f'L{i+1}:{v:.1f}' for i, v in enumerate(layer_heights))
            _put_label(out, f'层高: {hs}',
                       (region[0] + 4, h - 14), COLOR_TEXT, scale=0.38)

    return out
