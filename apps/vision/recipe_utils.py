from copy import deepcopy
import math
from pathlib import Path
from django.conf import settings

from .algorithms.foam_quality import quality_config
from .algorithms.foam_geometry import geometry_config, uses_foam_mm_alignment

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
        # 同一 POS 可以保留多个历史配方；已有数据时不要再按唯一记录查询。
        existing = VisionRecipe.objects.filter(
            recipe_type='FOAM_2D',
            foam_product_layout=layout,
            pos=item['pos'],
            camera_side='both',
        ).order_by('-is_active', '-updated_at', '-id').first()
        if existing is not None:
            recipes.append(existing)
            continue
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
    """Compatibility entry point: POS is traceability data, not a recipe key.

    Explicit recipe IDs are used for rack selection. Auto-select only when
    there is exactly one enabled recipe, never guess between different racks.
    """
    recipes = list(VisionRecipe.objects.filter(
        recipe_type='FOAM_2D', is_active=True,
    ).order_by('-updated_at', '-id')[:2])
    if len(recipes) > 1:
        raise ValueError('存在多套泡棉配方，请先为当前料架选择配方')
    return recipes[0] if recipes else None


FOAM_MATERIAL_LABELS = {'white': '白色', 'gray': '灰色', 'unspecified': '未标注颜色'}
FOAM_SEGMENTATION_BY_MATERIAL = {'white': 'fixed-threshold', 'gray': 'gray-graphcut-v3'}
FOAM_SEGMENTATION_LABELS = {
    'fixed-threshold': '阈值分割',
    'shadow-graphcut-v1': '阴影分割',
    'shadow-graphcut-fast-v2': '阴影分割',
    'gray-graphcut-v3': '阴影分割',
}


def foam_segmentation_mode(algorithm):
    return FOAM_SEGMENTATION_BY_MATERIAL.get(
        algorithm.get('material_type'), algorithm.get('foam_segmentation', 'fixed-threshold'),
    )


def foam_identity_summary(algorithm, *, mode=None, template_ready=False):
    """Use the recorded mode for history and the resolved mode for live recipes."""
    material = algorithm.get('material_type', 'unspecified')
    mode = mode or algorithm.get('foam_segmentation', 'fixed-threshold')
    effective = mode if template_ready else None
    return {
        'material_type': material,
        'material_label': FOAM_MATERIAL_LABELS.get(material, '未标注颜色'),
        'segmentation_label': FOAM_SEGMENTATION_LABELS.get(mode, mode),
        'configured_mode': mode,
        'effective_mode': effective,
        'effective_mode_label': FOAM_SEGMENTATION_LABELS.get(effective, effective) if effective else '标准 ROI 未配置，请绘制并保存',
        'uses_hsv_thresholds': mode == 'fixed-threshold',
    }


def serialize_recipe(recipe):
    template_status = get_foam_standard_template_status(recipe)
    algorithm = recipe.algorithm_config or {}
    thresholds = recipe.threshold_config or {}
    summary = foam_identity_summary(
        algorithm, mode=foam_segmentation_mode(algorithm), template_ready=template_status['ready'],
    )
    try:
        offsets = foam_offset_config(thresholds)
        summary['alignment'] = {
            'unit': 'mm' if uses_foam_mm_alignment(offsets) else 'px',
            **offsets,
        }
    except (TypeError, ValueError):
        # A legacy invalid value should not prevent the recipe list from opening.
        summary['alignment'] = {}
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
        'foam_summary': summary,
        'standard_template': recipe.standard_template_config or {},
        'standard_template_status': template_status,
        'standard_definition': 'roi',
        'standard_roi_status': template_status,
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


def foam_segmentation_config(recipe):
    algorithm = recipe.algorithm_config or {}
    if foam_segmentation_mode(algorithm) not in FOAM_SEGMENTATION_LABELS:
        raise ValueError('Unsupported foam_segmentation')
    material = algorithm.get('material_type', 'unspecified')
    if material not in ('unspecified', 'white', 'gray'):
        raise ValueError('material_type must be white, gray or unspecified')
    result = {'foam_min_v': 140, 'foam_max_s': 80}
    raw = algorithm.get('segmentation_config') or {}
    if not isinstance(raw, dict) or set(raw) - set(result):
        raise ValueError('segmentation_config supports foam_min_v and foam_max_s')
    for key, value in raw.items():
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 255 or not value.is_integer():
            raise ValueError(f'{key} must be an integer between 0 and 255')
        result[key] = int(value)
    return result


def get_foam_standard_template_status(recipe):
    """Return whether a recipe has a usable left/right template for its current ROI."""
    import cv2
    import numpy as np
    sides = {}
    width, height = int(recipe.image_width or 0), int(recipe.image_height or 0)
    for side, key in (('left', 'leftFoamROI'), ('right', 'rightFoamROI')):
        raw = (recipe.roi_config or {}).get(key)
        try:
            box = _pixel_roi_to_ratio(raw, width, height) if isinstance(raw, dict) else None
            if not box or width <= 0 or height <= 0:
                continue
            x1, y1, x2, y2 = [int(round(v * size)) for v, size in zip(box, (width, height, width, height))]
            if x2 <= x1 or y2 <= y1:
                continue
            mask = np.full((y2-y1, x2-x1), 255, np.uint8)
            polygon = _extract_polygon_points(raw)
            if polygon:
                mask[:] = 0
                points = np.rint(np.asarray(polygon) * [width, height] - [x1, y1]).astype(np.int32)
                cv2.fillPoly(mask, [points], 255)
            moments = cv2.moments(mask, binaryImage=True)
            if not moments['m00']:
                continue
            sides[side] = {
                'exists': True, 'pixels': int(moments['m00']),
                'search_area': mask.size, 'coverage_ratio': moments['m00'] / mask.size,
                'centroid_x': x1 + moments['m10'] / moments['m00'],
                'centroid_y': y1 + moments['m01'] / moments['m00'],
                'bounding_box': {'x': x1, 'y': y1, 'width': x2-x1, 'height': y2-y1},
            }
        except (TypeError, ValueError, OverflowError):
            continue
    ready = len(sides) == 2
    return {
        'ready': ready, 'reason': '' if ready else '请绘制有效的左右标准 ROI 并保存配方',
        'source': 'roi', 'paths': {}, 'sides': sides,
        'roi_matches': ready, 'resolution_matches': width > 0 and height > 0,
        'version': 'roi', 'built_at': '', 'incomplete_sides': [s for s in ('left', 'right') if s not in sides],
    }


def foam_offset_config(thresholds):
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

    return {
        'max_offset_mm': max_offset_mm,
        'max_offset_x_mm': max_offset_x_mm,
        'max_offset_y_mm': max_offset_y_mm,
        'max_offset_px': max(max_offset_x_px, max_offset_y_px),
        'max_offset_x_px': max_offset_x_px,
        'max_offset_y_px': max_offset_y_px,
        'mm_per_pixel_x': mm_per_pixel_x,
        'mm_per_pixel_y': mm_per_pixel_y,
        'pixels_per_mm_x': px_per_mm_x or (1 / mm_per_pixel_x if mm_per_pixel_x > 0 else 0),
        'pixels_per_mm_y': px_per_mm_y or (1 / mm_per_pixel_y if mm_per_pixel_y > 0 else 0),
    }


def build_foam_inspection_config(recipe):
    roi_config = recipe.roi_config or {}
    thresholds = recipe.threshold_config or {}
    algorithm = recipe.algorithm_config or {}
    quality = quality_config(thresholds)
    segmentation = foam_segmentation_config(recipe)
    geometry = geometry_config({**algorithm, 'product_registration': {'enabled': False}})

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

    # 标准泡棉面积比（0 表示不启用）
    standard_foam_area_ratio = float(
        _threshold_value(thresholds, ('standard_foam_area_ratio', 'standardFoamAreaRatio'), 0)
    )
    template_status = get_foam_standard_template_status(recipe)
    standard_mask_paths = template_status['paths']
    
    layer = roi_config.get('layerSearchROI')
    layer_ratio = _pixel_roi_to_ratio(layer, recipe.image_width, recipe.image_height) if layer else None
    if layer:
        if not layer_ratio or not all(0 <= v <= 1 for v in layer_ratio):
            raise ValueError('本层搜索区域无效或超出图像，请在图像内重新绘制“③ 本层大框”')
        for label, box in (('左', left), ('右', right)):
            edges = []
            for index, edge in enumerate(('左', '上', '右', '下')):
                excess = layer_ratio[index] - box[index] if index < 2 else box[index] - layer_ratio[index]
                if excess > 0:
                    size = recipe.image_width if index % 2 == 0 else recipe.image_height
                    edges.append(f'{edge}边约 {max(1, round(excess * size))} 像素')
            if edges:
                raise ValueError(
                    f'{label}标准 ROI 超出本层搜索区域（{"、".join(edges)}）。'
                    '请选择“③ 本层大框”扩大搜索区域，保留左右标准框不变。'
                )
    pos_str = str(recipe.pos)
    configured_mode = foam_segmentation_mode(algorithm)
    template = recipe.standard_template_config or {}
    if quality['decision_mode'] == 'separated-v2' and not layer_ratio:
        raise ValueError('separated-v2 requires a layerSearchROI')
    return {
        **quality,
        **segmentation,
        **geometry,
        **foam_offset_config(thresholds),
        'product_anchor_rois': [],
        'product_reference_path': '',
        'material_type': algorithm.get('material_type', 'unspecified'),
        'standard_mask_space': 'layer-v3' if layer_ratio else 'side',
        'standard_from_roi': True,
        'configured_foam_segmentation': configured_mode,
        'foam_segmentation': configured_mode,
        'layer_search_roi': layer_ratio,
        'layer_search_polygon': _extract_polygon_points(layer) if layer else None,
        'shared_foam_roi_key': pos_str,
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

