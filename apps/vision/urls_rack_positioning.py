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

    # ========== V2 刚体变换补偿接口 ==========
    # 示教阶段：建立标准模板
    path('v2/template/build/', views_rack_positioning.v2_build_template, name='rack_v2_build_template'),
    # 生产阶段：计算 6DoF 补偿偏差
    path('v2/compensation/compute/', views_rack_positioning.v2_compute_compensation, name='rack_v2_compute_compensation'),
    # 查询模板状态
    path('v2/template/status/<int:recipe_id>/', views_rack_positioning.v2_template_status, name='rack_v2_template_status'),
    # 清除模板（重新示教）
    path('v2/template/clear/<int:recipe_id>/', views_rack_positioning.v2_clear_template, name='rack_v2_clear_template'),
    # 将当前模板保存为标准模板
    path('v2/template/save/', views_rack_positioning.v2_save_as_standard_template, name='rack_v2_save_as_standard_template'),
]
