from django.urls import path

from . import views

app_name = 'alarms'

urlpatterns = [
    path('', views.alarm_list, name='alarm_list'),
    path('<int:pk>/', views.alarm_detail, name='alarm_detail'),
    path('<int:pk>/acknowledge/', views.acknowledge, name='acknowledge'),
    path('<int:pk>/close/', views.close, name='close'),
]
