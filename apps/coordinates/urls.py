from django.urls import path

from . import views


app_name = 'coordinates'

urlpatterns = [
    path('', views.workbench, name='workbench'),
    path('api/workbench/', views.api_workbench, name='api_workbench'),
    path('api/preview/', views.api_preview, name='api_preview'),
    path('api/save/', views.api_save, name='api_save'),
    path('api/transform-roi/', views.api_transform_roi, name='api_transform_roi'),
]
