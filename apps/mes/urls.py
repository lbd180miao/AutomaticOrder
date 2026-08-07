from django.urls import path

from . import views

app_name = 'mes'

urlpatterns = [
    # 主页面
    path('records/', views.record_list, name='record_list'),

    # API
    path('api/stats/', views.stats_api, name='stats_api'),
    path('api/retry/<int:record_id>/', views.retry_api, name='retry_api'),
    path('api/test/', views.test_upload_api, name='test_upload_api'),
]
