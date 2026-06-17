from django.urls import path

from . import views

app_name = 'vision'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/capture-foam-roi/', views.capture_foam_roi, name='capture_foam_roi'),
    path('tasks/capture-depth-roi/', views.capture_depth_roi, name='capture_depth_roi'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('rack-results/', views.rack_results, name='rack_results'),
    path('foam-results/', views.foam_results, name='foam_results'),
    
    # 交互式泡棉检测
    path('foam-inspector/', views.foam_inspector_interactive, name='foam_inspector_interactive'),
    
    # API接口
    path('api/camera/preview/', views.api_camera_preview, name='api_camera_preview'),
    path('api/foam/capture-inspect/', views.api_foam_capture_inspect, name='api_foam_capture_inspect'),
    path('api/foam/upload-inspect/', views.api_foam_upload_inspect, name='api_foam_upload_inspect'),
]
