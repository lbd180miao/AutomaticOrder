"""Versioned, create-only JSON transfer for both vision recipe families."""
import json

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction, IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .models import (VisionRecipe, RackLocationRecipe, RackLocationROI3D,
                     RackLocationROI3DEnhanced, FoamProductLayout, FoamRackSpec)

FORMAT = 'automatic-order-vision-recipe'
MAX_BYTES = 32 * 1024 * 1024
KINDS = {'foam2d': VisionRecipe, 'rack3d': RackLocationRecipe}


def fields(model):
    return {f.name: f for f in model._meta.fields
            if not f.primary_key and not f.is_relation and f.name not in ('created_at', 'updated_at')}


def snapshot(obj):
    return {name: getattr(obj, name) for name in fields(type(obj))}


def validate(model, data, **relations):
    if not isinstance(data, dict) or set(data) - fields(model).keys():
        raise ValueError('配方包含未知字段或字段格式不正确')
    obj = model(**data, **relations)
    for name, field in fields(model).items():
        value = getattr(obj, name)
        if isinstance(field, models.JSONField) and value is not None and not isinstance(value, dict):
            raise ValueError(f'{name} 必须是 JSON 对象')
        if isinstance(field, models.BooleanField) and type(value) is not bool:
            raise ValueError(f'{name} 必须是布尔值')
        if isinstance(field, models.IntegerField) and not (value is None and field.null) and type(value) is not int:
            raise ValueError(f'{name} 必须是整数')
    obj.full_clean()
    return obj


def unique_name(model, field, value):
    limit = model._meta.get_field(field).max_length
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('配方名称为空或过长')
    candidate, index = value, 1
    while model.objects.filter(**{field: candidate}).exists():
        suffix = f'（导入{index}）'
        candidate = value[:limit-len(suffix)] + suffix
        index += 1
    return candidate


def roi_recipe_data(data):
    """Transfer ROI geometry and parameters, never legacy image templates."""
    data = dict(data)
    for key in ('standard_template_config', 'standard_template_version', 'standard_template_built_at'):
        data.pop(key, None)
    thresholds = data.get('threshold_config', {})
    if not isinstance(thresholds, dict):
        raise ValueError('threshold_config 必须是 JSON 对象')
    data['threshold_config'] = {k: v for k, v in thresholds.items()
                                if k not in ('standardMaskPaths', 'standard_mask_paths')}
    algorithm = data.get('algorithm_config', {})
    if not isinstance(algorithm, dict):
        raise ValueError('algorithm_config 必须是 JSON 对象')
    data['algorithm_config'] = {k: v for k, v in algorithm.items() if k != 'product_registration'}
    roi = data.get('roi_config', {})
    if not isinstance(roi, dict):
        raise ValueError('roi_config 必须是 JSON 对象')
    data['roi_config'] = {k: v for k, v in roi.items() if k != 'productAnchorROIs'}
    return data


@require_GET
def export_recipe(request, kind, recipe_id):
    if kind not in KINDS:
        return JsonResponse({'success': False, 'error': '未知配方类型'}, status=400)
    query = KINDS[kind].objects.all()
    if kind == 'foam2d':
        query = query.filter(recipe_type='FOAM_2D')
    recipe = get_object_or_404(query, pk=recipe_id)
    payload = {'format': FORMAT, 'version': 2, 'kind': kind,
               'recipe': snapshot(recipe), 'relations': {}}
    # Make independent JSON containers before removing legacy template metadata.
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder, allow_nan=False))
    try:
        if kind == 'foam2d':
            if recipe.foam_product_layout:
                layout = recipe.foam_product_layout
                payload['relations']['layout'] = snapshot(layout)
                payload['relations']['rack_spec'] = snapshot(layout.rack_spec)
            payload['recipe'] = roi_recipe_data(payload['recipe'])
        else:
            for name in ('rois_3d', 'enhanced_rois_3d'):
                payload['relations'][name] = [snapshot(obj) for obj in getattr(recipe, name).all()]
            for name in ('camera_device', 'camera_config', 'hand_eye_calibration'):
                obj = getattr(recipe, name)
                payload['relations'][name] = snapshot(obj) if obj else None
        content = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2, allow_nan=False)
        if len(content.encode('utf-8')) > MAX_BYTES:
            raise ValueError('配方超过 32 MB 导出限制')
        response = HttpResponse(content, content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{kind}-recipe-{recipe.pk}.json"'
        return response
    except (ValueError, TypeError, OSError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


def reject_constant(value):
    raise ValueError('JSON 不允许 NaN 或 Infinity')


@require_POST
def import_recipe(request, kind):
    try:
        upload = request.FILES.get('file')
        if not upload or upload.size > MAX_BYTES:
            raise ValueError('请选择不超过 32 MB 的配方 JSON 文件')
        payload = json.loads(upload.read().decode('utf-8-sig'), parse_constant=reject_constant)
        json.dumps(payload, allow_nan=False)  # Also reject exponent overflow (e.g. 1e999).
        if (not isinstance(payload, dict) or payload.get('format') != FORMAT
                or type(payload.get('version')) is not int or payload['version'] not in (1, 2)
                or kind not in KINDS or payload.get('kind') != kind):
            raise ValueError('配方格式、版本或 2D/3D 类型不匹配')
        data = payload['recipe']
        relations = payload.get('relations', {})
        assets = payload.get('assets', {})
        if not all(isinstance(value, dict) for value in (data, relations, assets)):
            raise ValueError('配方数据结构不正确')
        warnings = []
        with transaction.atomic():
            model = KINDS[kind]
            name_field = 'name' if kind == 'foam2d' else 'recipe_name'
            data[name_field] = unique_name(model, name_field, data.get(name_field))
            bindings = {}
            if kind == 'foam2d':
                if data.get('recipe_type') != 'FOAM_2D':
                    raise ValueError('不是 2D 泡棉配方')
                if any(type(data.get(k)) is not int or data[k] <= 0 for k in ('image_width', 'image_height')) or data.get('pos', -1) < 0:
                    raise ValueError('图像尺寸或位置无效')
                if relations.get('layout') is not None:
                    spec_data = relations['rack_spec']
                    if (not isinstance(spec_data, dict) or set(spec_data) != set(fields(FoamRackSpec))
                            or not isinstance(relations['layout'], dict)
                            or set(relations['layout']) != set(fields(FoamProductLayout))):
                        raise ValueError('产品布局或料架规格格式不正确')
                    spec = FoamRackSpec.objects.filter(**spec_data).first()
                    if spec is None:
                        spec_data['rack_type'] = unique_name(FoamRackSpec, 'rack_type', spec_data.get('rack_type'))
                        spec = validate(FoamRackSpec, spec_data)
                        spec.save()
                    layout = FoamProductLayout.objects.filter(rack_spec=spec, **relations['layout']).first()
                    if layout is None:
                        layout_data = relations['layout']
                        if FoamProductLayout.objects.filter(rack_spec=spec, product_code=layout_data.get('product_code')).exists():
                            raise ValueError('产品布局冲突，请先确认目标电脑的产品布局')
                        layout = validate(FoamProductLayout, layout_data, rack_spec=spec)
                        layout.save()
                    bindings['foam_product_layout'] = layout
                data = roi_recipe_data(data)
                if assets or 'standard_template_config' in payload['recipe']:
                    warnings.append('已忽略旧版图片模板，只导入标准 ROI 和参数')
            else:
                if assets:
                    raise ValueError('3D 配方不支持外部模板文件')
                for name in ('camera_device', 'camera_config', 'hand_eye_calibration'):
                    reference = relations.get(name)
                    if reference is not None:
                        related_model = model._meta.get_field(name).related_model
                        if not isinstance(reference, dict) or set(reference) != set(fields(related_model)):
                            raise ValueError('设备或标定关联格式不正确')
                        # Match the complete settings, never an ID from another database.
                        matches = [obj for obj in related_model.objects.all()
                                   if json.loads(json.dumps(snapshot(obj), cls=DjangoJSONEncoder)) == reference]
                        bindings[name] = matches[0] if len(matches) == 1 else None
                        if bindings[name] is None:
                            warnings.append(f'{name} 未找到唯一匹配，请在工作台重新选择')
            recipe = validate(model, data, **bindings)
            recipe.save()
            if kind == 'rack3d':
                for key, child_model in [('rois_3d', RackLocationROI3D), ('enhanced_rois_3d', RackLocationROI3DEnhanced)]:
                    children = relations.get(key, [])
                    if not isinstance(children, list) or len(children) > 1000:
                        raise ValueError('3D ROI 列表无效')
                    for child in children:
                        validate(child_model, child, recipe=recipe).save()
        return JsonResponse({'success': True, 'id': recipe.pk, 'name': getattr(recipe, name_field), 'warnings': warnings})
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, ValidationError, IntegrityError, OSError, RecursionError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
