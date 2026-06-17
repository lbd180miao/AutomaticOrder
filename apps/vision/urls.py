from django.urls import path

from . import views

app_name = 'vision'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('rack-results/', views.rack_results, name='rack_results'),
    path('foam-results/', views.foam_results, name='foam_results'),
]
