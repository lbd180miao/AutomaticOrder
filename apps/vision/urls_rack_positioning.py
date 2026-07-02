"""
料架定位算法模块 URL配置
"""
from django.urls import path
from . import views_rack_positioning

urlpatterns = [
    # ========== 定位计算接口 ==========
    path('process/', views_rack_positioning.process_positioning, name='rack_positioning_process'),
    
    # 单独检测接口
    path('detect/plane/', views_rack_positioning.detect_plane, name='rack_positioning_detect_plane'),
    path('detect/edge/', views_rack_positioning.detect_edge, name='rack_positioning_detect_edge'),
    path('detect/pillar/', views_rack_positioning.detect_pillar, name='rack_positioning_detect_pillar'),
    
    # ========== 历史记录接口 ==========
    path('history/', views_rack_positioning.get_positioning_history, name='rack_positioning_history'),
    path('average-offsets/', views_rack_positioning.get_average_offsets, name='rack_positioning_average_offsets'),
    path('stability/', views_rack_positioning.analyze_stability, name='rack_positioning_stability'),
    
    # ========== 算法参数接口 ==========
    path('default-params/', views_rack_positioning.get_default_algorithm_params, name='rack_positioning_default_params'),
]
