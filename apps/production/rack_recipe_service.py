from __future__ import annotations

from dataclasses import dataclass

from .models import RackRecipe, RackRecipeVisionMapping


def _positive_int(value, fallback=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _vision_readiness(recipe):
    if recipe is None:
        return {
            'ready': False,
            'issues': ['未选择3D定位配方'],
            'roi_complete': False,
            'template_ready': False,
            'hand_eye_ready': False,
        }
    roi_config = recipe.roi_config or {}
    local_rois = roi_config.get('local_template_rois') or {}
    roi_complete = bool(
        roi_config.get('target_roi')
        and all(local_rois.get(key) for key in ('plane1', 'plane2', 'plane3'))
    )
    template_ready = bool(recipe.local_template_std)
    hand_eye_ready = bool(recipe.hand_eye_calibration_id or recipe.hand_eye_config)
    issues = []
    if not recipe.enabled:
        issues.append('3D定位配方已禁用')
    if recipe.layer_no not in (1, 2, 3):
        issues.append('当前3D定位算法仅支持第1～3层')
    if not roi_complete:
        issues.append('外框或三平面ROI未完成')
    if not template_ready:
        issues.append('三平面标准模板未保存')
    if not hand_eye_ready:
        issues.append('未关联手眼标定')
    return {
        'ready': not issues,
        'issues': issues,
        'roi_complete': roi_complete,
        'template_ready': template_ready,
        'hand_eye_ready': hand_eye_ready,
    }


def serialize_mapping(mapping):
    vision_recipe = mapping.rack_location_recipe
    readiness = _vision_readiness(vision_recipe)
    issues = list(readiness['issues'])
    if vision_recipe is not None:
        if vision_recipe.position_no != mapping.station_position_no:
            issues.append('3D配方工位位置号不一致')
        if vision_recipe.layer_no != mapping.layer_no:
            issues.append('3D配方层号不一致')
        if (
            vision_recipe.rack_type
            and mapping.rack_recipe.rack_type
            and vision_recipe.rack_type != mapping.rack_recipe.rack_type
        ):
            issues.append('3D配方料架类型不一致')
    readiness['issues'] = issues
    readiness['ready'] = not issues
    return {
        'id': mapping.id,
        'station_position_no': mapping.station_position_no,
        'layer_no': mapping.layer_no,
        'rack_location_recipe_id': mapping.rack_location_recipe_id,
        'rack_location_recipe_name': (
            vision_recipe.recipe_name if vision_recipe else ''
        ),
        'vision_position_no': vision_recipe.position_no if vision_recipe else None,
        'vision_layer_no': vision_recipe.layer_no if vision_recipe else None,
        'robot_target_code': mapping.robot_target_code,
        'enabled': mapping.enabled,
        **readiness,
    }


def validate_rack_recipe(recipe):
    errors = []
    warnings = []
    layers = _positive_int(recipe.layer_count)
    per_layer = _positive_int(recipe.quantity_per_layer)
    total = _positive_int(recipe.total_quantity)
    position_count = _positive_int(recipe.station_position_count)
    capacity = layers * per_layer

    if not recipe.recipe_code.strip():
        errors.append('配方编码不能为空')
    if not recipe.rack_type.strip():
        errors.append('料框类型不能为空')
    if layers < 1:
        errors.append('层数必须大于0')
    if per_layer < 1:
        errors.append('每层件数必须大于0')
    if total < 1:
        errors.append('总装箱数量必须大于0')
    if capacity and total > capacity:
        errors.append(f'总装箱数量 {total} 超过布局容量 {capacity}')
    if position_count not in (1, 2):
        errors.append('工位位置数量目前只支持1或2')

    mappings = {
        (item.station_position_no, item.layer_no): item
        for item in recipe.vision_mappings.select_related('rack_location_recipe')
    }
    mapping_rows = []
    for station_position_no in range(1, max(position_count, 0) + 1):
        for layer_no in range(1, max(layers, 0) + 1):
            mapping = mappings.get((station_position_no, layer_no))
            if mapping is None:
                errors.append(f'{station_position_no}号位第{layer_no}层未建立视觉映射')
                mapping_rows.append({
                    'id': None,
                    'station_position_no': station_position_no,
                    'layer_no': layer_no,
                    'rack_location_recipe_id': None,
                    'rack_location_recipe_name': '',
                    'robot_target_code': '',
                    'enabled': True,
                    'ready': False,
                    'issues': ['未建立视觉映射'],
                    'roi_complete': False,
                    'template_ready': False,
                    'hand_eye_ready': False,
                })
                continue
            row = serialize_mapping(mapping)
            mapping_rows.append(row)
            if mapping.rack_location_recipe is None:
                errors.append(f'{station_position_no}号位第{layer_no}层未选择3D定位配方')
            else:
                if mapping.rack_location_recipe.layer_no != layer_no:
                    errors.append(
                        f'{station_position_no}号位第{layer_no}层映射到错误层号的3D配方'
                    )
                if mapping.rack_location_recipe.position_no != station_position_no:
                    warnings.append(
                        f'{station_position_no}号位第{layer_no}层的3D配方位置号不一致'
                    )
                if not row['ready']:
                    warnings.append(
                        f'{station_position_no}号位第{layer_no}层：'
                        + '、'.join(row['issues'])
                    )

    return {
        'valid': not errors,
        'production_ready': not errors and not warnings,
        'errors': errors,
        'warnings': warnings,
        'capacity': capacity,
        'mapping_rows': mapping_rows,
        'mapping_ready_count': sum(1 for row in mapping_rows if row['ready']),
        'mapping_total_count': max(position_count, 0) * max(layers, 0),
    }


def serialize_rack_recipe(recipe, include_mappings=True):
    validation = validate_rack_recipe(recipe)
    payload = {
        'id': recipe.id,
        'recipe_code': recipe.recipe_code,
        'name': recipe.name,
        'product_code': recipe.product_code,
        'rack_type': recipe.rack_type,
        'station_position_count': recipe.station_position_count,
        'layer_count': recipe.layer_count,
        'quantity_per_layer': recipe.quantity_per_layer,
        'total_quantity': recipe.total_quantity,
        'layout_capacity': validation['capacity'],
        'layer_height': float(recipe.layer_height),
        'layer_spacing': float(recipe.layer_spacing),
        'tolerance_x': float(recipe.tolerance_x),
        'tolerance_y': float(recipe.tolerance_y),
        'tolerance_z': float(recipe.tolerance_z),
        'loading_direction': recipe.loading_direction,
        'loading_direction_label': recipe.get_loading_direction_display(),
        'full_condition': recipe.full_condition,
        'full_condition_label': recipe.get_full_condition_display(),
        'version': recipe.version,
        'mes_updated_at': recipe.mes_updated_at.isoformat() if recipe.mes_updated_at else None,
        'is_active': recipe.is_active,
        'updated_at': recipe.updated_at.isoformat(),
        'validation': {
            key: value for key, value in validation.items() if key != 'mapping_rows'
        },
    }
    if include_mappings:
        payload['mappings'] = validation['mapping_rows']
    return payload


@dataclass(frozen=True)
class RackPosition:
    position_index: int
    layer_no: int
    slot_no: int

    def as_dict(self):
        return {
            'position_index': self.position_index,
            'layer_no': self.layer_no,
            'slot_no': self.slot_no,
        }


class RackPositionResolver:
    def __init__(self, recipe: RackRecipe):
        self.recipe = recipe

    def _position(self, zero_based_index):
        per_layer = max(1, int(self.recipe.quantity_per_layer))
        logical_layer = zero_based_index // per_layer + 1
        logical_slot = zero_based_index % per_layer + 1
        top_down = self.recipe.loading_direction.startswith('TOP_DOWN')
        right_left = self.recipe.loading_direction.endswith('RIGHT_LEFT')
        layer_no = (
            int(self.recipe.layer_count) - logical_layer + 1
            if top_down else logical_layer
        )
        slot_no = per_layer - logical_slot + 1 if right_left else logical_slot
        return RackPosition(zero_based_index, layer_no, slot_no)

    def resolve(self, completed_quantity, station_position_no=1):
        completed = _positive_int(completed_quantity)
        total = _positive_int(self.recipe.total_quantity)
        is_full = total > 0 and completed >= total
        current = None if is_full else self._position(completed)
        next_position = (
            self._position(completed + 1)
            if current is not None and completed + 1 < total else None
        )
        mapping = None
        if current is not None:
            mapping = (
                self.recipe.vision_mappings
                .select_related('rack_location_recipe')
                .filter(
                    station_position_no=station_position_no,
                    layer_no=current.layer_no,
                    enabled=True,
                )
                .first()
            )
        return {
            'completed_quantity': completed,
            'planned_quantity': total,
            'station_position_no': int(station_position_no),
            'current': current.as_dict() if current else None,
            'next': next_position.as_dict() if next_position else None,
            'is_full': is_full,
            'mapping': serialize_mapping(mapping) if mapping else None,
            'rack_location_recipe_id': (
                mapping.rack_location_recipe_id if mapping else None
            ),
        }
