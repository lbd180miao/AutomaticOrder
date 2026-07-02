from django.urls import path

from . import views


app_name = 'coordinates'

urlpatterns = [
    path('', views.workbench, name='workbench'),
]
