from django.urls import path

from . import views

app_name = 'devices'

urlpatterns = [
    path('status/', views.status, name='status'),
    path('signals/', views.signals, name='signals'),
]
