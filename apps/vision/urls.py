from django.urls import path

from . import views

app_name = 'vision'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/<int:pk>/delete/', views.delete_task, name='delete_task'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('rack-results/', views.rack_results, name='rack_results'),
    path('foam-results/', views.foam_results, name='foam_results'),

    # 泡棉检测工作台
    path('foam-inspector/', views.foam_inspector_interactive, name='foam_inspector_interactive'),

    # 视觉配方管理（独立页面）
    path('recipes/', views.recipe_management, name='recipe_management'),

    # 料架定位工作台（新增）
    path('rack-locator/', views.rack_locator_panel, name='rack_locator_panel'),
    path('rack-location/', views.rack_location_workbench, name='rack_location_workbench'),
    path('rack-location/recipes/', views.rack_location_recipes, name='rack_location_recipes'),
    path('rack-location/recipes/create/', views.rack_location_recipe_create, name='rack_location_recipe_create'),
    path('rack-location/recipes/<int:recipe_id>/edit/', views.rack_location_recipe_edit, name='rack_location_recipe_edit'),
    path('rack-location/recipes/capture/', views.rack_location_capture, name='rack_location_capture'),
    path('rack-location/recipes/preview-calculate/', views.rack_location_preview_calculate, name='rack_location_preview_calculate'),
    path('rack-location/results/', views.rack_location_history, name='rack_location_history'),
    path('rack-location/trigger/', views.api_rack_location_trigger, name='rack_location_trigger'),

    # API — 泡棉检测
    path('api/camera/preview/', views.api_camera_preview, name='api_camera_preview'),
    path('api/foam/calibration/', views.api_foam_calibration, name='api_foam_calibration'),
    path('api/foam/calibration/save/', views.api_foam_calibration_save, name='api_foam_calibration_save'),
    path('api/recipes/', views.api_vision_recipes, name='api_vision_recipes'),
    path('api/recipes/foam-2d/by-pos/', views.api_foam_recipe_by_pos, name='api_foam_recipe_by_pos'),
    path('api/recipes/foam-2d/defaults/', views.api_foam_recipe_defaults, name='api_foam_recipe_defaults'),
    path('api/recipes/foam-2d/save/', views.api_foam_recipe_save, name='api_foam_recipe_save'),
    path('api/recipes/foam-2d/create/', views.api_foam_recipe_create, name='api_foam_recipe_create'),
    path('api/recipes/foam-2d/<int:recipe_id>/delete/', views.api_foam_recipe_delete, name='api_foam_recipe_delete'),
    path('api/foam/capture-inspect/', views.api_foam_capture_inspect, name='api_foam_capture_inspect'),
    path('api/foam/upload-inspect/', views.api_foam_upload_inspect, name='api_foam_upload_inspect'),

    # API — 料架定位（新增）
    path('api/rack/locate/', views.api_rack_locate, name='api_rack_locate'),
    path('api/rack/results/', views.api_rack_results, name='api_rack_results'),
    path('api/vision/3d/recipes/', views.api_vision_3d_recipes, name='api_vision_3d_recipes'),
    path('api/vision/3d/recipes/<int:recipe_id>/', views.api_vision_3d_recipe_detail, name='api_vision_3d_recipe_detail'),
    path('api/vision/3d/rois/', views.api_vision_3d_rois, name='api_vision_3d_rois'),
    path('api/vision/3d/rois/<int:roi_id>/', views.api_vision_3d_roi_detail, name='api_vision_3d_roi_detail'),
    path('api/vision/3d/capture/', views.api_vision_3d_capture, name='api_vision_3d_capture'),
    path('api/vision/3d/auto-align/', views.api_vision_3d_auto_align, name='api_vision_3d_auto_align'),
    path('api/vision/3d/test-locate/', views.api_vision_3d_test_locate, name='api_vision_3d_test_locate'),
    path('api/vision/3d/write-plc/', views.api_vision_3d_write_plc, name='api_vision_3d_write_plc'),
    path('api/rack-location/workbench/capture/', views.api_rack_location_workbench_capture, name='api_rack_location_workbench_capture'),
    path('api/rack-location/workbench/calculate/', views.api_rack_location_workbench_calculate, name='api_rack_location_workbench_calculate'),
    path('api/rack-location/workbench/save/', views.api_rack_location_workbench_save, name='api_rack_location_workbench_save'),
    path('api/rack-location/trigger/', views.api_rack_location_trigger, name='api_rack_location_trigger'),
    path('api/rack-location/write-plc/', views.api_rack_location_write_plc, name='api_rack_location_write_plc'),
    path('api/rack-location/recipes/', views.api_rack_location_recipes, name='api_rack_location_recipes'),
    path('api/rack-location/recipes/<int:recipe_id>/update/', views.api_rack_location_recipe_update, name='api_rack_location_recipe_update'),
    path('api/rack-location/results/', views.api_rack_location_results, name='api_rack_location_results'),
]
