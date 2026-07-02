"""
补偿值计算模块 URL配置
"""
from django.urls import path
from . import views_compensation

urlpatterns = [
    # ========== 补偿值计算接口 ==========
    path('calculate/', views_compensation.calculate_compensation, name='compensation_calculate'),
    path('calculate/from-result/', views_compensation.calculate_from_result, name='compensation_from_result'),
    path('calculate/batch/', views_compensation.batch_calculate, name='compensation_batch'),
    
    # ========== 补偿值查询接口 ==========
    path('get/', views_compensation.get_compensation, name='compensation_get'),
    path('latest/', views_compensation.get_latest_compensation, name='compensation_latest'),
    path('average/', views_compensation.get_average_compensation, name='compensation_average'),
    
    # ========== 补偿值统计接口 ==========
    path('statistics/', views_compensation.get_statistics, name='compensation_statistics'),
    
    # ========== PLC数据接口 ==========
    path('plc-data/', views_compensation.prepare_plc_data, name='compensation_plc_data'),
    
    # ========== 配置接口 ==========
    path('default-rule/', views_compensation.get_default_rule, name='compensation_default_rule'),
]
