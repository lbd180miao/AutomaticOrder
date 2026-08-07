from django.urls import path

from . import views

app_name = 'devices'

urlpatterns = [
    path('status/', views.status, name='status'),
    path('signals/', views.signals, name='signals'),
    path('plc-config/', views.plc_config, name='plc_config'),
    path('api/plc-status/', views.api_plc_status, name='api_plc_status'),
]
