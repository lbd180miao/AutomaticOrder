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

    # 料架定位工作台（新增）
    path('rack-locator/', views.rack_locator_panel, name='rack_locator_panel'),

    # API — 泡棉检测
    path('api/camera/preview/', views.api_camera_preview, name='api_camera_preview'),
    path('api/foam/calibration/', views.api_foam_calibration, name='api_foam_calibration'),
    path('api/foam/calibration/save/', views.api_foam_calibration_save, name='api_foam_calibration_save'),
    path('api/recipes/', views.api_vision_recipes, name='api_vision_recipes'),
    path('api/recipes/foam-2d/by-pos/', views.api_foam_recipe_by_pos, name='api_foam_recipe_by_pos'),
    path('api/recipes/foam-2d/defaults/', views.api_foam_recipe_defaults, name='api_foam_recipe_defaults'),
    path('api/recipes/foam-2d/save/', views.api_foam_recipe_save, name='api_foam_recipe_save'),
    path('api/foam/capture-inspect/', views.api_foam_capture_inspect, name='api_foam_capture_inspect'),
    path('api/foam/upload-inspect/', views.api_foam_upload_inspect, name='api_foam_upload_inspect'),

    # API — 料架定位（新增）
    path('api/rack/locate/', views.api_rack_locate, name='api_rack_locate'),
    path('api/rack/results/', views.api_rack_results, name='api_rack_results'),
]
