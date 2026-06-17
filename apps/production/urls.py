from django.urls import path

from . import views

app_name = 'production'

urlpatterns = [
    path('products/', views.product_list, name='product_list'),
    path('racks/', views.rack_list, name='rack_list'),
    path('recipes/', views.recipe_list, name='recipe_list'),
]
