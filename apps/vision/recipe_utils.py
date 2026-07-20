from copy import deepcopy

from .models import VisionRecipe


DEFAULT_THRESHOLD_CONFIG = {
    'minCoverage': 0.75,
    'maxOffsetX': 30,
    'maxOffsetY': 30,
    'maxOffsetMm': 2.0,
    'minScore': 0.8,
    'minIoU': 0.70,
    # mm_per_pixel 标定系数（0 表示未标定，不输出 mm 偏移）
    'mmPerPixelX': 0,
    'mmPerPixelY': 0,
    # 标准泡棉面积占 ROI 面积的比例（0 表示不启用 mask 面积比）
    'standardFoamAreaRatio': 0,
    # 可选标准模板掩膜路径：{'left': '...', 'right': '...'}
    'standardMaskPaths': {},
}

DEFAULT_FOAM_2D_RECIPES = [
    {
        'name': '第1层泡棉检测配方',
        'pos': 0,
        'roi_config': {
            'leftFoamROI': {'x': 220, 'y': 140, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 140, 'width': 110, 'height': 70},
        },
    },
    {
        'name': '第2层泡棉检测配方',
        'pos': 1,
        'roi_config': {
            'leftFoamROI': {'x': 220, 'y': 300, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 300, 'width': 110, 'height': 70},
        },
    },
    {
        'name': '第3层泡棉检测配方',
        'pos': 2,
        'roi_config': {
            'leftFoamROI': {'x': 220, 'y': 460, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 460, 'width': 110, 'height': 70},
        },
    },
]


def ensure_default_foam_2d_recipes():
    recipes = []
    for item in DEFAULT_FOAM_2D_RECIPES:
        recipe, _ = VisionRecipe.objects.get_or_create(
            recipe_type='FOAM_2D',
            pos=item['pos'],
            camera_side='both',
            defaults={
                'name': item['name'],
                'image_width': 1280,
                'image_height': 720,
                'roi_config': deepcopy(item['roi_config']),
                'threshold_config': deepcopy(DEFAULT_THRESHOLD_CONFIG),
                'is_active': True,
            },
        )
        recipes.append(recipe)
    return recipes


def get_active_foam_2d_recipe_by_pos(pos):
    return (
        VisionRecipe.objects
        .filter(recipe_type='FOAM_2D', pos=int(pos), is_active=True)
        .order_by('-updated_at', '-id')
        .first()
    )


def serialize_recipe(recipe):
    return {
        'id': recipe.id,
        'name': recipe.name,
        'recipe_type': recipe.recipe_type,
        'product_code': recipe.product_code,
        'rack_type': recipe.rack_type,
        'camera_side': recipe.camera_side or 'both',
        'pos': recipe.pos,
        'layerName': f'第{recipe.pos + 1}层',
        'image_width': recipe.image_width,
        'image_height': recipe.image_height,
        'roi_config': recipe.roi_config or {},
        'threshold_config': recipe.threshold_config or {},
        'algorithm_config': recipe.algorithm_config or {},
        'is_active': recipe.is_active,
        'remark': recipe.remark or '',
        'created_at': recipe.created_at.isoformat() if recipe.created_at else '',
        'updated_at': recipe.updated_at.isoformat() if recipe.updated_at else '',
    }


def _pixel_roi_to_ratio(roi, image_width, image_height):
    """将 ROI 配置转换为归一化比例坐标 [x1, y1, x2, y2]。

    支持两种格式：
    1. 比例格式（新格式）：{x1r, y1r, x2r, y2r}，值在 [0, 1]，**优先使用**
    2. 像素格式（旧格式）：{x, y, width, height}，需要除以图像尺寸

    返回 None 表示 ROI 数据无效（负数、零面积等）。
    """
    # 优先读取比例坐标（前端新格式，精确且不依赖分辨率）
    if all(k in roi for k in ('x1r', 'y1r', 'x2r', 'y2r')):
        x1r = float(roi['x1r'])
        y1r = float(roi['y1r'])
        x2r = float(roi['x2r'])
        y2r = float(roi['y2r'])
        # 校验：必须是合法的 [0,1] 区间且有正面积
        if (0.0 <= x1r < x2r <= 1.0) and (0.0 <= y1r < y2r <= 1.0):
            return [round(x1r, 6), round(y1r, 6), round(x2r, 6), round(y2r, 6)]

    # 回退到旧格式（像素坐标）
    x = float(roi.get('x', 0))
    y = float(roi.get('y', 0))
    w = float(roi.get('width', 0))
    h = float(roi.get('height', 0))
    iw = max(float(image_width or 1), 1.0)
    ih = max(float(image_height or 1), 1.0)
    # 宽度或高度为负 / 零 → 数据损坏
    if w <= 0 or h <= 0:
        return None
    x1 = round(max(0.0, min(1.0, x / iw)), 6)
    y1 = round(max(0.0, min(1.0, y / ih)), 6)
    x2 = round(max(0.0, min(1.0, (x + w) / iw)), 6)
    y2 = round(max(0.0, min(1.0, (y + h) / ih)), 6)
    if x1 >= x2 or y1 >= y2:
        return None
    return [x1, y1, x2, y2]


def _threshold_value(thresholds, keys, default):
    for key in keys:
        if key in thresholds and thresholds[key] is not None:
            return thresholds[key]
    return default


def build_foam_inspection_config(recipe):
    roi_config = recipe.roi_config or {}
    thresholds = recipe.threshold_config or {}

    left_roi_raw = roi_config.get('leftFoamROI')
    right_roi_raw = roi_config.get('rightFoamROI')
    if not left_roi_raw or not right_roi_raw:
        raise ValueError(
            f'配方 "{recipe.name}" (POS {recipe.pos}) 缺少 ROI 配置，'
            '请在工作台重新标定左右泡棉区域后保存配方。'
        )

    left = _pixel_roi_to_ratio(left_roi_raw, recipe.image_width, recipe.image_height)
    right = _pixel_roi_to_ratio(right_roi_raw, recipe.image_width, recipe.image_height)

    if left is None:
        raise ValueError(
            f'配方 "{recipe.name}" (POS {recipe.pos}) 的左侧 ROI 数据无效 '
            f'(raw={left_roi_raw})。请重新标定左侧泡棉区域后保存配方。'
        )
    if right is None:
        raise ValueError(
            f'配方 "{recipe.name}" (POS {recipe.pos}) 的右侧 ROI 数据无效 '
            f'(raw={right_roi_raw})。请重新标定右侧泡棉区域后保存配方。'
        )

    max_offset = thresholds.get('max_offset_px')
    max_offset_x = int(_threshold_value(thresholds, ('max_offset_x', 'maxOffsetX'), 150))
    max_offset_y = int(_threshold_value(thresholds, ('max_offset_y', 'maxOffsetY'), 150))
    max_offset_mm = float(
        _threshold_value(thresholds, ('max_offset_mm', 'maxOffsetMm'), 2.0)
    )
    # mm_per_pixel 标定系数（0 表示未标定，跳过 mm 换算）
    mm_per_pixel_x = float(
        _threshold_value(thresholds, ('mm_per_pixel_x', 'mmPerPixelX'), 0)
    )
    mm_per_pixel_y = float(
        _threshold_value(thresholds, ('mm_per_pixel_y', 'mmPerPixelY'), 0)
    )
    # 标准泡棉面积比（0 表示不启用）
    standard_foam_area_ratio = float(
        _threshold_value(thresholds, ('standard_foam_area_ratio', 'standardFoamAreaRatio'), 0)
    )
    standard_mask_paths = _threshold_value(
        thresholds, ('standard_mask_paths', 'standardMaskPaths'), {}
    )
    return {
        'foam_rois': {
            str(recipe.pos): {
                'left': left,
                'right': right,
            },
        },
        'coverage_threshold': float(
            _threshold_value(thresholds, ('coverage_threshold', 'minCoverage'), 0.75)
        ),
        'score_threshold': float(
            _threshold_value(thresholds, ('score_threshold', 'minScore'), 0.8)
        ),
        'iou_threshold': float(
            _threshold_value(thresholds, ('iou_threshold', 'minIoU'), 0.70)
        ),
        'max_offset_px': int(max_offset) if max_offset is not None else max(max_offset_x, max_offset_y),
        'max_offset_mm': max_offset_mm,
        'mm_per_pixel_x': mm_per_pixel_x,
        'mm_per_pixel_y': mm_per_pixel_y,
        'standard_foam_area_ratio': standard_foam_area_ratio,
        'standard_mask_paths': standard_mask_paths if isinstance(standard_mask_paths, dict) else {},
    }

