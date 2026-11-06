from django.urls import path
from . import views_rack_positioning

urlpatterns = [
    path('history/', views_rack_positioning.get_positioning_history, name='rack_positioning_history'),
    path('average-offsets/', views_rack_positioning.get_average_offsets, name='rack_positioning_average_offsets'),
    path('stability/', views_rack_positioning.analyze_stability, name='rack_positioning_stability'),
]
