from copy import deepcopy

from .models import FoamProductLayout, FoamRackSpec, VisionRecipe


DEFAULT_THRESHOLD_CONFIG = {
    'minCoverage': 0.75,
    'maxOffsetX': 30,
    'maxOffsetY': 30,
    'maxOffsetMm': 2.0,
    'maxOffsetXMm': 2.0,
    'maxOffsetYMm': 2.0,
    'minScore': 0.8,
    'requireStandardTemplate': True,
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
    spec, _ = FoamRackSpec.objects.get_or_create(
        rack_type='RACK-3L',
        defaults={'name': '三层标准料架', 'layer_count': 3, 'remark': '系统初始化规格'},
    )
    layout, _ = FoamProductLayout.objects.get_or_create(
        rack_spec=spec,
        product_code='PROD-A',
        defaults={'product_name': 'A 产品', 'qty_per_layer': 5},
    )
    recipes = []
    for item in DEFAULT_FOAM_2D_RECIPES:
        recipe, _ = VisionRecipe.objects.get_or_create(
            recipe_type='FOAM_2D',
            foam_product_layout=layout,
            pos=item['pos'],
            camera_side='both',
            defaults={
                'name': item['name'],
                'rack_type': spec.rack_type,
                'product_code': layout.product_code,
                'image_width': 1280,
                'image_height': 720,
                'roi_config': deepcopy(item['roi_config']),
                'threshold_config': deepcopy(DEFAULT_THRESHOLD_CONFIG),
                'is_active': True,
            },
        )
        recipes.append(recipe)
    return recipes


def get_active_foam_2d_recipe_by_pos(pos, layout_id=None):
    queryset = VisionRecipe.objects.filter(
        recipe_type='FOAM_2D', pos=int(pos), is_active=True,
    )
    if layout_id not in (None, ''):
        queryset = queryset.filter(foam_product_layout_id=int(layout_id))
    return queryset.order_by('-updated_at', '-id').first()


def serialize_recipe(recipe):
    template_status = get_foam_standard_template_status(recipe)
    layout = recipe.foam_product_layout
    if layout:
        layer_number = recipe.pos // max(layout.qty_per_layer, 1) + 1
        slot_number = recipe.pos % max(layout.qty_per_layer, 1) + 1
    else:
        layer_number = recipe.pos + 1
        slot_number = 1
    return {
        'id': recipe.id,
        'name': recipe.name,
        'recipe_type': recipe.recipe_type,
        'product_code': recipe.product_code,
        'rack_type': recipe.rack_type,
        'foam_product_layout_id': recipe.foam_product_layout_id,
        'foam_product_name': layout.product_name if layout else '',
        'foam_rack_name': layout.rack_spec.name if layout else '',
        'camera_side': recipe.camera_side or 'both',
        'pos': recipe.pos,
        # Keep the legacy display field stable for older clients. Structured
        # consumers should use rack_layer / slot_number / positionLabel.
        'layerName': f'第{recipe.pos + 1}层',
        'rack_layer': layer_number,
        'slot_number': slot_number,
        'positionLabel': f'第{layer_number}层 · {slot_number}号位',
        'image_width': recipe.image_width,
        'image_height': recipe.image_height,
        'roi_config': recipe.roi_config or {},
        'threshold_config': recipe.threshold_config or {},
        'algorithm_config': recipe.algorithm_config or {},
        'standard_template': recipe.standard_template_config or {},
        'standard_template_status': template_status,
        'standard_template_version': recipe.standard_template_version or '',
        'standard_template_built_at': (
            recipe.standard_template_built_at.isoformat()
            if recipe.standard_template_built_at else ''
        ),
        'is_active': recipe.is_active,
        'remark': recipe.remark or '',
        'created_at': recipe.created_at.isoformat() if recipe.created_at else '',
        'updated_at': recipe.updated_at.isoformat() if recipe.updated_at else '',
    }


def _pixel_roi_to_ratio(roi, image_width, image_height):
    """将 ROI 配置转换为归一化比例坐标 [x1, y1, x2, y2]。

    支持三种格式：
    1. 比例格式（新格式）：{x1r, y1r, x2r, y2r}，值在 [0, 1]，**优先使用**
    2. 多边形格式（画笔 ROI）：{type:'polygon', points:[[xr,yr],...]}，计算边界框
    3. 像素格式（旧格式）：{x, y, width, height}，需要除以图像尺寸

    返回 None 表示 ROI 数据无效（负数、零面积等）。
    """
    # ── 多边形格式（画笔 ROI）──────────────────────────
    if isinstance(roi, dict) and roi.get('type') == 'polygon':
        points = roi.get('points', [])
        if len(points) >= 3:
            try:
                pts = [[float(p[0]), float(p[1])] for p in points]
                if all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in pts):
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    x1r = round(min(xs), 6)
                    y1r = round(min(ys), 6)
                    x2r = round(max(xs), 6)
                    y2r = round(max(ys), 6)
                    if x1r < x2r and y1r < y2r:
                        return [x1r, y1r, x2r, y2r]
            except (TypeError, IndexError, ValueError):
                pass

    # ── 比例坐标格式（新矩形格式）────────────────────────
    if all(k in roi for k in ('x1r', 'y1r', 'x2r', 'y2r')):
        x1r = float(roi['x1r'])
        y1r = float(roi['y1r'])
        x2r = float(roi['x2r'])
        y2r = float(roi['y2r'])
        # 校验：必须是合法的 [0,1] 区间且有正面积
        if (0.0 <= x1r < x2r <= 1.0) and (0.0 <= y1r < y2r <= 1.0):
            return [round(x1r, 6), round(y1r, 6), round(x2r, 6), round(y2r, 6)]

    # ── 旧格式（像素坐标）────────────────────────────────
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

def _extract_polygon_points(roi):
    """从 ROI 配置中提取多边形点列表（全图比例坐标）。

    如果 ROI 不是多边形格式，返回 None。
    """
    if not isinstance(roi, dict) or roi.get('type') != 'polygon':
        return None
    points = roi.get('points', [])
    if len(points) < 3:
        return None
    try:
        pts = [[float(p[0]), float(p[1])] for p in points]
        if all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in pts):
            return pts
    except (TypeError, IndexError, ValueError):
        pass
    return None


def _threshold_value(thresholds, keys, default):
    for key in keys:
        if key in thresholds and thresholds[key] is not None:
            return thresholds[key]
    return default


def has_complete_foam_template_side_metadata(side_data):
    """A usable template side must include mask area and ROI-local position data."""
    if not isinstance(side_data, dict):
        return False
    bounding_box = side_data.get('bounding_box')
    return bool(
        side_data.get('path')
        and int(side_data.get('pixels') or side_data.get('pixel_count') or 0) > 0
        and int(side_data.get('search_area') or 0) > 0
        and side_data.get('centroid_x') is not None
        and side_data.get('centroid_y') is not None
        and isinstance(bounding_box, dict)
        and int(bounding_box.get('width') or 0) > 0
        and int(bounding_box.get('height') or 0) > 0
    )


def get_foam_standard_template_status(recipe):
    """Return whether a recipe has a usable left/right template for its current ROI."""
    template = recipe.standard_template_config or {}
    thresholds = recipe.threshold_config or {}
    sides = template.get('sides') if isinstance(template.get('sides'), dict) else {}
    legacy_paths = _threshold_value(
        thresholds, ('standard_mask_paths', 'standardMaskPaths'), {}
    )
    legacy_paths = legacy_paths if isinstance(legacy_paths, dict) else {}
    paths = {
        side: (sides.get(side) or {}).get('path') or legacy_paths.get(side, '')
        for side in ('left', 'right')
    }

    reason = ''
    roi_matches = True
    resolution_matches = True
    if template:
        saved_roi = template.get('roi_config')
        if saved_roi is not None and saved_roi != (recipe.roi_config or {}):
            roi_matches = False
            reason = 'ROI已修改，需要重新示教标准模板'
        saved_width = int(template.get('image_width') or 0)
        saved_height = int(template.get('image_height') or 0)
        if saved_width and saved_height and (
            saved_width != int(recipe.image_width) or saved_height != int(recipe.image_height)
        ):
            resolution_matches = False
            reason = '配方图像分辨率已修改，需要重新示教标准模板'

    missing_sides = [side for side, path in paths.items() if not path]
    incomplete_sides = [
        side for side, path in paths.items()
        if path and not has_complete_foam_template_side_metadata(sides.get(side))
    ]
    if (missing_sides or incomplete_sides) and not reason:
        labels = {'left': '左侧', 'right': '右侧'}
        if missing_sides and not incomplete_sides:
            reason = '缺少' + '、'.join(labels[side] for side in missing_sides) + '标准模板'
        elif incomplete_sides and not missing_sides:
            reason = (
                '、'.join(labels[side] for side in incomplete_sides)
                + '旧模板缺少泡棉位置数据，需要重新示教'
            )
        else:
            reason = (
                '、'.join(labels[side] for side in incomplete_sides)
                + '旧模板缺少泡棉位置数据；'
                + '、'.join(labels[side] for side in missing_sides)
                + '标准模板未示教，请重新示教左右模板'
            )

    ready = not missing_sides and not incomplete_sides and roi_matches and resolution_matches
    return {
        'ready': ready,
        'reason': reason,
        'paths': paths,
        'roi_matches': roi_matches,
        'resolution_matches': resolution_matches,
        'version': recipe.standard_template_version or template.get('version', ''),
        'built_at': (
            recipe.standard_template_built_at.isoformat()
            if recipe.standard_template_built_at else template.get('built_at', '')
        ),
        'sides': sides,
        'incomplete_sides': incomplete_sides,
    }


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
    
    left_polygon = _extract_polygon_points(left_roi_raw)
    right_polygon = _extract_polygon_points(right_roi_raw)

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

    max_offset_mm = float(_threshold_value(thresholds, ('max_offset_mm', 'maxOffsetMm'), 2.0))
    max_offset_x_mm = float(
        _threshold_value(thresholds, ('max_offset_x_mm', 'maxOffsetXMm'), max_offset_mm)
    )
    max_offset_y_mm = float(
        _threshold_value(thresholds, ('max_offset_y_mm', 'maxOffsetYMm'), max_offset_mm)
    )
    legacy_max_offset_px = float(_threshold_value(thresholds, ('max_offset_px',), 30))
    max_offset_x_px = float(
        _threshold_value(thresholds, ('max_offset_x_px', 'maxOffsetX'), legacy_max_offset_px)
    )
    max_offset_y_px = float(
        _threshold_value(thresholds, ('max_offset_y_px', 'maxOffsetY'), legacy_max_offset_px)
    )

    # 优先读取 pixels_per_mm 配置，并换算为底层的 mm_per_pixel；兼容旧配置
    px_per_mm_x = float(_threshold_value(thresholds, ('pixels_per_mm_x', 'pixelsPerMmX'), 0))
    if px_per_mm_x > 0:
        mm_per_pixel_x = round(1.0 / px_per_mm_x, 6)
    else:
        mm_per_pixel_x = float(_threshold_value(thresholds, ('mm_per_pixel_x', 'mmPerPixelX'), 0))

    px_per_mm_y = float(_threshold_value(thresholds, ('pixels_per_mm_y', 'pixelsPerMmY'), 0))
    if px_per_mm_y > 0:
        mm_per_pixel_y = round(1.0 / px_per_mm_y, 6)
    else:
        mm_per_pixel_y = float(_threshold_value(thresholds, ('mm_per_pixel_y', 'mmPerPixelY'), 0))

    # 标准泡棉面积比（0 表示不启用）
    standard_foam_area_ratio = float(
        _threshold_value(thresholds, ('standard_foam_area_ratio', 'standardFoamAreaRatio'), 0)
    )
    template_status = get_foam_standard_template_status(recipe)
    standard_mask_paths = template_status['paths']
    
    pos_str = str(recipe.pos)
    return {
        'foam_rois': {
            pos_str: {
                'left': left,
                'right': right,
            },
        },
        'polygon_rois': {
            pos_str: {
                'left': left_polygon,
                'right': right_polygon,
            }
        },
        'coverage_threshold': float(
            _threshold_value(thresholds, ('coverage_threshold', 'minCoverage'), 0.75)
        ),
        'score_threshold': float(
            _threshold_value(thresholds, ('score_threshold', 'minScore'), 0.8)
        ),
        'max_offset_mm': max_offset_mm,
        'max_offset_x_mm': max_offset_x_mm,
        'max_offset_y_mm': max_offset_y_mm,
        'max_offset_px': max(max_offset_x_px, max_offset_y_px),
        'max_offset_x_px': max_offset_x_px,
        'max_offset_y_px': max_offset_y_px,
        'mm_per_pixel_x': mm_per_pixel_x,
        'mm_per_pixel_y': mm_per_pixel_y,
        'standard_foam_area_ratio': standard_foam_area_ratio,
        # 模板必须成套使用；任一侧不完整时不要加载遗留的单侧掩膜。
        'standard_mask_paths': (
            standard_mask_paths
            if template_status['ready'] and isinstance(standard_mask_paths, dict)
            else {}
        ),
        'require_standard_template': bool(
            _threshold_value(thresholds, ('require_standard_template', 'requireStandardTemplate'), True)
        ),
        'standard_template_ready': template_status['ready'],
        'standard_template_error': template_status['reason'],
    }

