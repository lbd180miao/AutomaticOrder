from django.urls import path

from . import views

app_name = 'mes'

urlpatterns = [
    path('records/', views.record_list, name='record_list'),
]
