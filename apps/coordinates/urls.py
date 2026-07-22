from django.urls import path

from . import views


app_name = 'coordinates'

urlpatterns = [
    path('', views.workbench, name='workbench'),
    path('api/workbench/', views.api_workbench, name='api_workbench'),
    path('api/transform-roi/', views.api_transform_roi, name='api_transform_roi'),
    path('api/capture/', views.api_capture, name='api_capture'),
    path('api/last-capture/', views.api_last_capture, name='api_last_capture'),
]
