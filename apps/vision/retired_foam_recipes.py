"""Retired 2D recipe endpoints. Historical database records remain intact."""
from django.http import JsonResponse


def retired_recipe(request, **kwargs):
    return JsonResponse({'success': False, 'error': '2D 配方功能已移除，请使用相机连续检测工作台'}, status=410)
