from django.urls import path

from . import views

app_name = 'production'

urlpatterns = [
    path('products/', views.product_list, name='product_list'),
    path('racks/', views.rack_list, name='rack_list'),
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('api/validate-barcode/', views.validate_barcode_api, name='validate_barcode_api'),
    path('api/rack/manual-update/', views.manual_rack_update_api, name='manual_rack_update_api'),
    path('api/product/manual-update/', views.manual_product_update_api, name='manual_product_update_api'),
    path('api/product/defective/', views.product_defective_api, name='product_defective_api'),
]
