"""RVC 相机 URL 配置。"""
from django.urls import path

from . import views

app_name = "rvc_camera"

urlpatterns = [
    # 控制台页面
    path("", views.demo_page, name="demo"),
    # 设备控制
    path("api/status/", views.get_status, name="status"),
    path("api/find/", views.find_devices, name="find_devices"),
    path("api/connect/", views.connect_camera, name="connect"),
    path("api/disconnect/", views.disconnect_camera, name="disconnect"),
    path("api/recover/", views.recover_camera, name="recover"),
    path("api/mode/", views.set_mode, name="set_mode"),
    path("api/exposure/", views.set_exposure, name="set_exposure"),
    path("api/capture/", views.capture_frame, name="capture"),
]
