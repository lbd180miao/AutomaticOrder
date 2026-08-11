from django.urls import path

from . import views

app_name = 'traceability'

urlpatterns = [
    path('search/', views.search, name='search'),
    path('product/<str:product_code>/', views.product_detail, name='product_detail'),
]
