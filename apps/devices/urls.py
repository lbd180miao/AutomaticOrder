from django.urls import path

from . import views

app_name = 'devices'

urlpatterns = [
    path('status/', views.status, name='status'),
    path('signals/', views.signals, name='signals'),
    path('plc-config/', views.plc_config, name='plc_config'),
    path('plc-debug/', views.plc_debug, name='plc_debug'),
    path('api/plc-status/', views.api_plc_status, name='api_plc_status'),
    path('api/plc-read/', views.api_plc_read, name='api_plc_read'),
    path('api/plc-write/', views.api_plc_write, name='api_plc_write'),
]
