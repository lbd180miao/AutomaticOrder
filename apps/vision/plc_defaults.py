"""Persist explicit default choices independently of recipe copies and names."""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
import json

from .models import PlcVisionDefaults, VisionRecipe, RackLocationRecipe


def get_default_recipe(kind):
    if kind != 'rack':
        raise ValueError('2D 配方已移除，连续检测不使用 PLC 配方')
    defaults = PlcVisionDefaults.objects.select_related('foam_recipe', 'rack_recipe').filter(pk=1).first()
    recipe = getattr(defaults, f'{kind}_recipe', None)
    valid = (recipe and recipe.is_active and recipe.recipe_type == 'FOAM_2D') if kind == 'foam' else (recipe and recipe.enabled)
    if not valid:
        label = '2D' if kind == 'foam' else '3D'
        raise ValueError(f'请在视觉配方管理页面选择已启用的 {label} 默认配方')
    return recipe


@require_http_methods(['GET', 'POST'])
def api_plc_defaults(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body or '{}')
            kind = data.get('kind')
            if kind != 'rack':
                raise ValueError('未知配方类型')
            recipe_id = int(data.get('recipe_id'))
            if kind == 'foam':
                recipe = get_object_or_404(VisionRecipe, pk=recipe_id, recipe_type='FOAM_2D', is_active=True)
            else:
                recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id, enabled=True)
            PlcVisionDefaults.objects.update_or_create(pk=1, defaults={f'{kind}_recipe': recipe})
        except (ValueError, TypeError, AttributeError) as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    defaults = PlcVisionDefaults.objects.filter(pk=1).first()
    return JsonResponse({'success': True,
                         'rack_recipe_id': defaults.rack_recipe_id if defaults else None})
