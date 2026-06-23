"""
DM相机URL配置
"""
from django.urls import path
from . import views

app_name = 'dm_camera'

urlpatterns = [
    # 演示页面
    path('', views.demo_page, name='demo'),
    
    # 设备控制
    path('api/devices/find/', views.find_devices, name='find_devices'),
    path('api/connect/', views.connect_camera, name='connect'),
    path('api/disconnect/', views.disconnect_camera, name='disconnect'),
    path('api/stream/start/', views.start_stream, name='start_stream'),
    path('api/stream/stop/', views.stop_stream, name='stop_stream'),
    path('api/capture/', views.capture_frame, name='capture'),
    path('api/status/', views.get_status, name='status'),
    
    # 配置管理
    path('api/configs/', views.list_configs, name='list_configs'),
    path('api/configs/create/', views.create_config, name='create_config'),
    path('api/configs/<int:config_id>/', views.get_config, name='get_config'),
    path('api/configs/<int:config_id>/update/', views.update_config, name='update_config'),
    path('api/configs/<int:config_id>/delete/', views.delete_config, name='delete_config'),
    
    # 采集记录
    path('api/captures/', views.list_captures, name='list_captures'),
    path('api/captures/<int:capture_id>/', views.get_capture, name='get_capture'),
]
