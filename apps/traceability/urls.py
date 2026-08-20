from django.urls import path

from . import views

app_name = 'traceability'

urlpatterns = [
    # 模块一：料框检测记录
    path('rack/', views.rack_detection, name='rack_detection'),
    # 模块二：产品与料框绑定记录
    path('binding/', views.product_binding, name='product_binding'),
    # 模块三：泡棉检测记录
    path('foam/', views.foam_inspection, name='foam_inspection'),
    # 单件产品详情（保留）
    path('product/<str:product_code>/', views.product_detail, name='product_detail'),
    # 兼容旧链接：/traceability/search/ → 重定向到 binding
    path('search/', views.product_binding, name='search'),
]
