from django.urls import path

from . import views


app_name = 'coordinates'

urlpatterns = [
    path('', views.workbench, name='workbench'),
    path('api/workbench/', views.api_workbench, name='api_workbench'),
    path('api/preview/', views.api_preview, name='api_preview'),
    path('api/save/', views.api_save, name='api_save'),
    path('api/transform-roi/', views.api_transform_roi, name='api_transform_roi'),
    # ── REAL 模式（新增）──
    path('real/', views.workbench_real, name='workbench_real'),
    path('api/capture-real/', views.api_capture_real, name='api_capture_real'),
    path('api/real-last-capture/', views.api_real_last_capture, name='api_real_last_capture'),
]
