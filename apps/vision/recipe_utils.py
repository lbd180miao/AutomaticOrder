from copy import deepcopy

from .models import VisionRecipe


DEFAULT_THRESHOLD_CONFIG = {
    'minCoverage': 0.75,
    'maxOffsetX': 30,
    'maxOffsetY': 30,
    'minScore': 0.8,
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
    x = float(roi.get('x', 0))
    y = float(roi.get('y', 0))
    width = float(roi.get('width', 0))
    height = float(roi.get('height', 0))
    image_width = max(float(image_width or 1), 1.0)
    image_height = max(float(image_height or 1), 1.0)
    return [
        round(max(0.0, min(1.0, x / image_width)), 6),
        round(max(0.0, min(1.0, y / image_height)), 6),
        round(max(0.0, min(1.0, (x + width) / image_width)), 6),
        round(max(0.0, min(1.0, (y + height) / image_height)), 6),
    ]


def build_foam_inspection_config(recipe):
    roi_config = recipe.roi_config or {}
    thresholds = recipe.threshold_config or {}
    left = _pixel_roi_to_ratio(
        roi_config['leftFoamROI'], recipe.image_width, recipe.image_height
    )
    right = _pixel_roi_to_ratio(
        roi_config['rightFoamROI'], recipe.image_width, recipe.image_height
    )
    max_offset_x = int(thresholds.get('maxOffsetX', 30))
    max_offset_y = int(thresholds.get('maxOffsetY', 30))
    return {
        'foam_rois': {
            str(recipe.pos): {
                'left': left,
                'right': right,
            },
        },
        'coverage_threshold': float(thresholds.get('minCoverage', 0.75)),
        'score_threshold': float(thresholds.get('minScore', 0.8)),
        'max_offset_px': max(max_offset_x, max_offset_y),
    }
