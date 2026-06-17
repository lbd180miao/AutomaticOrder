from django.urls import path

from . import views

app_name = 'workflow'

urlpatterns = [
    path('current/', views.current, name='current'),
    path('history/', views.history, name='history'),
    path('start/', views.start, name='start'),
    path('<int:pk>/advance/', views.advance, name='advance'),
    path('<int:pk>/unlock/', views.unlock, name='unlock'),
]
