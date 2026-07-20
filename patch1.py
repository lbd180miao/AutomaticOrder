import sys

file_path = "apps/vision/algorithms/foam_inspector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''def _detect_foam_side(image, roi, cfg, side=None, polygon_points=None):
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
        roi_area = max(roi_width * roi_height, 1)'''

replace1 = '''def _detect_foam_side(image, roi, cfg, side=None, polygon_points=None):
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
    
    # 为了能检测到溢出标准模板（用户画的ROI/多边形）的泡棉，扩大搜索区域
    margin = 50
    h, w = image.shape[:2]
    search_x1 = max(0, x1 - margin)
    search_y1 = max(0, y1 - margin)
    search_x2 = min(w, x2 + margin)
    search_y2 = min(h, y2 + margin)
    
    roi_img = image[search_y1:search_y2, search_x1:search_x2].copy()
    roi_height, roi_width = roi_img.shape[:2]
    
    # 原始 ROI 在放大后搜索区域中的偏移
    dx = x1 - search_x1
    dy = y1 - search_y1
    
    # 如果存在多边形，计算多边形的像素面积；否则使用包围盒面积
    polygon_mask = None
    if polygon_points and len(polygon_points) >= 3:
        pts_px = np.array([
            [int(round(pt[0] * w)) - search_x1, int(round(pt[1] * h)) - search_y1]
            for pt in polygon_points
        ], dtype=np.int32)
        polygon_mask = np.zeros((roi_height, roi_width), dtype=np.uint8)
        cv2.fillPoly(polygon_mask, [pts_px], 255)
        roi_area = max(cv2.countNonZero(polygon_mask), 1)
        # 移除了位运算掩码逻辑，允许检测多边形之外的溢出泡棉
    else:
        roi_area = max((x2 - x1) * (y2 - y1), 1)'''

target2 = '''    has_real_standard_mask = standard_mask is not None
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
    box = _largest_mask_box(mask, (x1, y1))'''

replace2 = '''    has_real_standard_mask = standard_mask is not None
    # 核心业务逻辑："ROI即标准模板"。如果未配置真实的掩膜，则认为整个ROI就是标准的泡棉形状
    if standard_mask is None:
        if polygon_mask is not None:
            standard_mask = polygon_mask.copy()
        else:
            standard_mask = np.zeros((roi_height, roi_width), dtype=np.uint8)
            cv2.rectangle(standard_mask, (dx, dy), (dx + (x2 - x1), dy + (y2 - y1)), 255, -1)
        
    standard_pixels = int(np.count_nonzero(standard_mask)) if standard_mask is not None else None
    coverage_ratio = round(compute_coverage_ratio(mask, standard_mask, roi_area), 4)
    iou = round(compute_iou(mask, standard_mask), 4) if standard_mask is not None else None
    centroid = compute_mask_centroid(mask)
    box = _largest_mask_box(mask, (search_x1, search_y1))'''

target3 = '''    result = {
        'roi': roi,
        'box': box,
        'mask': mask,'''

replace3 = '''    result = {
        'roi': (search_x1, search_y1, search_x2, search_y2),
        'original_roi': roi,
        'box': box,
        'mask': mask,'''

content = content.replace(target1, replace1)
content = content.replace(target2, replace2)
content = content.replace(target3, replace3)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done foam_inspector")
