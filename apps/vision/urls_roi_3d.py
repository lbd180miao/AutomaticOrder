"""
3D ROI配方模块路由
"""
from django.urls import path
from . import views_roi_3d

urlpatterns = [
    # 配方管理
    path('api/roi-3d/recipes/', views_roi_3d.list_recipes, name='api_roi_3d_recipe_list'),
    path('api/roi-3d/recipes/<int:recipe_id>/', views_roi_3d.get_recipe_detail, name='api_roi_3d_recipe_get'),
    
    # ROI CRUD
    path('api/roi-3d/list/', views_roi_3d.list_rois, name='api_roi_3d_list'),
    path('api/roi-3d/<int:roi_id>/', views_roi_3d.get_roi, name='api_roi_3d_get'),
    path('api/roi-3d/create/', views_roi_3d.create_roi, name='api_roi_3d_create'),
    path('api/roi-3d/<int:roi_id>/update/', views_roi_3d.update_roi, name='api_roi_3d_update'),
    path('api/roi-3d/<int:roi_id>/delete/', views_roi_3d.delete_roi, name='api_roi_3d_delete'),
    
    # 层级管理
    path('api/roi-3d/layer/summary/', views_roi_3d.get_layer_summary, name='api_roi_3d_layer_summary'),
    path('api/roi-3d/layer/batch-create/', views_roi_3d.batch_create_layer_rois, name='api_roi_3d_layer_batch_create'),
    
    # 模板管理
    path('api/roi-3d/templates/', views_roi_3d.list_templates, name='api_roi_3d_template_list'),
    path('api/roi-3d/templates/<int:template_id>/', views_roi_3d.get_template, name='api_roi_3d_template_get'),
    path('api/roi-3d/templates/create/', views_roi_3d.create_template, name='api_roi_3d_template_create'),
    path('api/roi-3d/templates/apply/', views_roi_3d.apply_template, name='api_roi_3d_template_apply'),
    
    # 统计和辅助
    path('api/roi-3d/statistics/', views_roi_3d.get_recipe_statistics, name='api_roi_3d_statistics'),
    path('api/roi-3d/types/', views_roi_3d.get_roi_types, name='api_roi_3d_types'),
    
    # 工作台专用API
    path('api/roi-3d/auto-fill/', views_roi_3d.auto_fill_roi, name='api_roi_3d_auto_fill'),
    path('api/roi-3d/preview/', views_roi_3d.preview_crop, name='api_roi_3d_preview'),
]
