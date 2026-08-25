"""Structured APIs for the three-level 2D foam recipe hierarchy."""

import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from apps.vision.models import FoamProductLayout, FoamRackSpec, VisionRecipe
from apps.vision.recipe_utils import serialize_recipe


DEFAULT_RACK_SPECS = (
    ('RACK-2L', '二层标准料架', 2),
    ('RACK-3L', '三层标准料架', 3),
    ('RACK-4L', '四层标准料架', 4),
)


@transaction.atomic
def ensure_default_foam_profiles():
    """Create defaults and attach pre-structure recipes without deleting data."""
    specs = {}
    for rack_type, name, layer_count in DEFAULT_RACK_SPECS:
        spec, _ = FoamRackSpec.objects.get_or_create(
            rack_type=rack_type,
            defaults={'name': name, 'layer_count': layer_count, 'remark': '系统初始化规格'},
        )
        specs[rack_type] = spec

    layout, _ = FoamProductLayout.objects.get_or_create(
        rack_spec=specs['RACK-3L'],
        product_code='PROD-A',
        defaults={'product_name': 'A 产品', 'qty_per_layer': 5},
    )
    for recipe in VisionRecipe.objects.filter(
        recipe_type='FOAM_2D', foam_product_layout__isnull=True,
    ):
        matched = None
        if recipe.rack_type and recipe.product_code:
            matched = FoamProductLayout.objects.filter(
                rack_spec__rack_type=recipe.rack_type,
                product_code=recipe.product_code,
            ).first()
        target = matched or layout
        recipe.foam_product_layout = target
        recipe.rack_type = target.rack_spec.rack_type
        recipe.product_code = target.product_code
        recipe.save(update_fields=[
            'foam_product_layout', 'rack_type', 'product_code', 'updated_at',
        ])
    return layout


def _json_body(request):
    return json.loads(request.body or '{}')


def _positive_int(value, label):
    number = int(value)
    if number < 1:
        raise ValueError(f'{label}至少为 1')
    if number > 100:
        raise ValueError(f'{label}不能超过 100')
    return number


def _layout_recipes(layout, *, active_only=False):
    queryset = VisionRecipe.objects.filter(
        recipe_type='FOAM_2D', foam_product_layout=layout,
    )
    return queryset.filter(is_active=True) if active_only else queryset


def _serialize_rack_spec(spec):
    layouts = spec.product_layouts.filter(is_active=True)
    return {
        'id': spec.id,
        'name': spec.name,
        'rack_type': spec.rack_type,
        'layer_count': spec.layer_count,
        'remark': spec.remark,
        'is_active': spec.is_active,
        'product_count': layouts.count(),
        'created_at': spec.created_at.isoformat(),
        'updated_at': spec.updated_at.isoformat(),
    }


def _serialize_product_layout(layout):
    recipes = _layout_recipes(layout, active_only=True)
    total = layout.total_positions
    configured = recipes.filter(pos__gte=0, pos__lt=total).values('pos').distinct().count()
    return {
        'id': layout.id,
        'rack_spec_id': layout.rack_spec_id,
        'rack_spec_name': layout.rack_spec.name,
        'rack_type': layout.rack_spec.rack_type,
        'layer_count': layout.rack_spec.layer_count,
        'product_code': layout.product_code,
        'product_name': layout.product_name,
        'qty_per_layer': layout.qty_per_layer,
        'total_positions': total,
        'configured_count': configured,
        'pending_count': max(total - configured, 0),
        'overflow_count': recipes.filter(pos__gte=total).count(),
        'preserved_recipe_count': _layout_recipes(layout).count(),
        'is_active': layout.is_active,
        'created_at': layout.created_at.isoformat(),
        'updated_at': layout.updated_at.isoformat(),
    }


def _serialize_copy_source(recipe):
    layout = recipe.foam_product_layout
    return {
        'id': recipe.id,
        'name': recipe.name,
        'pos': recipe.pos,
        'product_name': layout.product_name if layout else recipe.product_code or '未分类产品',
        'product_code': layout.product_code if layout else recipe.product_code or '',
        'rack_name': layout.rack_spec.name if layout else recipe.rack_type or '未分类料架',
        'layout_id': layout.id if layout else None,
    }


@require_http_methods(['GET', 'POST'])
def api_foam_rack_specs(request):
    ensure_default_foam_profiles()
    if request.method == 'GET':
        specs = FoamRackSpec.objects.filter(is_active=True).prefetch_related('product_layouts')
        return JsonResponse({'success': True, 'rack_specs': [_serialize_rack_spec(s) for s in specs]})
    try:
        body = _json_body(request)
        name = str(body.get('name', '')).strip()
        rack_type = str(body.get('rack_type', '')).strip().upper()
        if not name or not rack_type:
            raise ValueError('规格名称和料架类型码不能为空')
        if FoamRackSpec.objects.filter(rack_type=rack_type).exists():
            return JsonResponse({'success': False, 'error': f'料架类型码 {rack_type} 已存在'}, status=409)
        spec = FoamRackSpec.objects.create(
            name=name,
            rack_type=rack_type,
            layer_count=_positive_int(body.get('layer_count', 3), '层数'),
            remark=str(body.get('remark', '')).strip(),
        )
        return JsonResponse({'success': True, 'rack_spec': _serialize_rack_spec(spec)}, status=201)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_foam_rack_spec_detail(request, spec_id):
    ensure_default_foam_profiles()
    spec = get_object_or_404(FoamRackSpec, pk=spec_id)
    if request.method == 'GET':
        return JsonResponse({'success': True, 'rack_spec': _serialize_rack_spec(spec)})
    if request.method == 'DELETE':
        spec.is_active = False
        spec.save(update_fields=['is_active', 'updated_at'])
        spec.product_layouts.update(is_active=False)
        return JsonResponse({'success': True, 'message': f'料架规格「{spec.name}」已归档，关联配方数据仍保留'})
    try:
        body = _json_body(request)
        if 'name' in body:
            spec.name = str(body['name']).strip() or spec.name
        if 'layer_count' in body:
            spec.layer_count = _positive_int(body['layer_count'], '层数')
        if 'remark' in body:
            spec.remark = str(body['remark']).strip()
        spec.save()
        return JsonResponse({'success': True, 'rack_spec': _serialize_rack_spec(spec)})
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'POST'])
def api_foam_product_layouts(request, spec_id):
    ensure_default_foam_profiles()
    spec = get_object_or_404(FoamRackSpec, pk=spec_id, is_active=True)
    if request.method == 'GET':
        layouts = spec.product_layouts.filter(is_active=True)
        return JsonResponse({
            'success': True,
            'rack_spec': _serialize_rack_spec(spec),
            'product_layouts': [_serialize_product_layout(layout) for layout in layouts],
        })
    try:
        body = _json_body(request)
        product_code = str(body.get('product_code', '')).strip().upper()
        product_name = str(body.get('product_name', '')).strip()
        if not product_code:
            raise ValueError('产品编码不能为空')
        if FoamProductLayout.objects.filter(rack_spec=spec, product_code=product_code).exists():
            return JsonResponse({'success': False, 'error': f'产品编码 {product_code} 已存在'}, status=409)
        layout = FoamProductLayout.objects.create(
            rack_spec=spec,
            product_code=product_code,
            product_name=product_name,
            qty_per_layer=_positive_int(body.get('qty_per_layer', 5), '每层产品数'),
        )
        return JsonResponse({'success': True, 'product_layout': _serialize_product_layout(layout)}, status=201)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_foam_product_layout_detail(request, layout_id):
    ensure_default_foam_profiles()
    layout = get_object_or_404(FoamProductLayout.objects.select_related('rack_spec'), pk=layout_id)
    if request.method == 'GET':
        return JsonResponse({'success': True, 'product_layout': _serialize_product_layout(layout)})
    if request.method == 'DELETE':
        layout.is_active = False
        layout.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({'success': True, 'message': f'产品档案「{layout.product_name or layout.product_code}」已归档，位置配方仍保留'})
    try:
        body = _json_body(request)
        if 'product_name' in body:
            layout.product_name = str(body['product_name']).strip()
        if 'qty_per_layer' in body:
            layout.qty_per_layer = _positive_int(body['qty_per_layer'], '每层产品数')
        layout.save()
        return JsonResponse({'success': True, 'product_layout': _serialize_product_layout(layout)})
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET'])
def api_foam_layout_recipes(request, layout_id):
    ensure_default_foam_profiles()
    layout = get_object_or_404(
        FoamProductLayout.objects.select_related('rack_spec'), pk=layout_id, is_active=True,
    )
    recipes = {}
    for recipe in _layout_recipes(layout, active_only=True).order_by('pos', '-updated_at'):
        recipes.setdefault(recipe.pos, recipe)

    layers = []
    for layer_index in range(layout.rack_spec.layer_count):
        slots = []
        for slot_index in range(layout.qty_per_layer):
            pos = layer_index * layout.qty_per_layer + slot_index
            recipe = recipes.get(pos)
            slots.append({'pos': pos, 'slot_no': slot_index + 1, 'recipe': serialize_recipe(recipe) if recipe else None})
        layers.append({'layer_no': layer_index + 1, 'slots': slots})

    overflow = [
        serialize_recipe(recipe)
        for recipe in _layout_recipes(layout, active_only=True)
        .filter(pos__gte=layout.total_positions).order_by('pos')
    ]
    copy_sources = [
        _serialize_copy_source(recipe)
        for recipe in VisionRecipe.objects.filter(
            recipe_type='FOAM_2D', is_active=True,
        ).select_related('foam_product_layout__rack_spec').order_by(
            'foam_product_layout__rack_spec__layer_count',
            'foam_product_layout__product_code', 'pos',
        )
    ]
    return JsonResponse({
        'success': True,
        'layout': _serialize_product_layout(layout),
        'layers': layers,
        'overflow_recipes': overflow,
        'copy_sources': copy_sources,
    })
