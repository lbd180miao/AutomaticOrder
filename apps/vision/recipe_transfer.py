"""Versioned, create-only JSON transfer for both vision recipe families."""
import base64
import binascii
import json
import re
import shutil
import uuid
from pathlib import Path

from django.conf import settings
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


def template_paths(data, callback):
    """Visit only the 2D template's documented file references, not arbitrary paths."""
    template = data.get('standard_template_config') or {}
    for container, key in [(template, 'source_image_path')] + [
        (side, 'path') for side in (template.get('sides') or {}).values() if isinstance(side, dict)
    ]:
        if container.get(key):
            container[key] = callback(container[key])
    for key in ('standardMaskPaths', 'standard_mask_paths'):
        paths = (data.get('threshold_config') or {}).get(key) or {}
        for side, value in paths.items():
            if value:
                paths[side] = callback(value)


@require_GET
def export_recipe(request, kind, recipe_id):
    if kind not in KINDS:
        return JsonResponse({'success': False, 'error': '未知配方类型'}, status=400)
    query = KINDS[kind].objects.all()
    if kind == 'foam2d':
        query = query.filter(recipe_type='FOAM_2D')
    recipe = get_object_or_404(query, pk=recipe_id)
    payload = {'format': FORMAT, 'version': 1, 'kind': kind,
               'recipe': snapshot(recipe), 'relations': {}, 'assets': {}}
    # Make independent JSON containers before rewriting file references.
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder, allow_nan=False))
    try:
        if kind == 'foam2d':
            if recipe.foam_product_layout:
                layout = recipe.foam_product_layout
                payload['relations']['layout'] = snapshot(layout)
                payload['relations']['rack_spec'] = snapshot(layout.rack_spec)
            media = Path(settings.MEDIA_ROOT).resolve()
            seen = {}
            total = 0

            def attach(value):
                nonlocal total
                if value in seen:
                    return seen[value]
                path = Path(value)
                path = (path if path.is_absolute() else media / path).resolve()
                if not path.is_relative_to(media) or not path.is_file():
                    raise ValueError('标准模板文件缺失或不在媒体目录内，请重新示教后导出')
                if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'):
                    raise ValueError('不支持的标准模板文件类型')
                total += path.stat().st_size
                if total > MAX_BYTES // 2:
                    raise ValueError('模板文件过大，无法导出为单个 JSON')
                key = f'asset-{len(seen)}{path.suffix.lower()}'
                payload['assets'][key] = base64.b64encode(path.read_bytes()).decode('ascii')
                seen[value] = 'asset:' + key
                return seen[value]
            template_paths(payload['recipe'], attach)
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
    destination = None
    try:
        upload = request.FILES.get('file')
        if not upload or upload.size > MAX_BYTES:
            raise ValueError('请选择不超过 32 MB 的配方 JSON 文件')
        payload = json.loads(upload.read().decode('utf-8-sig'), parse_constant=reject_constant)
        json.dumps(payload, allow_nan=False)  # Also reject exponent overflow (e.g. 1e999).
        if (not isinstance(payload, dict) or payload.get('format') != FORMAT
                or type(payload.get('version')) is not int or payload['version'] != 1
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
                destination = Path(settings.MEDIA_ROOT).resolve() / 'vision' / 'recipe_imports' / uuid.uuid4().hex
                restored = {}

                def restore(value):
                    if not isinstance(value, str) or not value.startswith('asset:'):
                        raise ValueError('模板必须包含文件内容，不能引用外部路径')
                    key = value[6:]
                    if key not in assets or not re.fullmatch(r'asset-[0-9]+\.(png|jpg|jpeg|bmp|tif|tiff)', key):
                        raise ValueError('模板文件索引无效')
                    if key not in restored:
                        content = base64.b64decode(assets[key], validate=True)
                        if not content:
                            raise ValueError('模板文件为空')
                        destination.mkdir(parents=True, exist_ok=True)
                        target = destination / key
                        target.write_bytes(content)
                        restored[key] = target.relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
                    return restored[key]
                template_paths(data, restore)
                if set(restored) != set(assets):
                    raise ValueError('存在未引用的模板文件')
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
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, ValidationError, IntegrityError, OSError, binascii.Error, RecursionError) as exc:
        if destination and destination.exists():
            shutil.rmtree(destination)
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
