"""
PLC补偿值写入模块路由配置
"""
from django.urls import path
from . import views_plc_writer

app_name = 'vision_plc'

urlpatterns = [
    # ========== PLC写入接口 ==========
    
    # 写入补偿值到PLC
    path('write/', views_plc_writer.write_compensation_to_plc, name='write_compensation'),
    
    # 从定位结果写入补偿值
    path('write/from-result/', views_plc_writer.write_from_result, name='write_from_result'),
    
    # 批量写入配方所有层
    path('write/batch/', views_plc_writer.batch_write_for_recipe, name='batch_write'),
    
    # ========== 完整流程接口 ==========
    
    # 定位 → 补偿 → PLC写入（完整流程）
    path('complete-flow/', views_plc_writer.complete_positioning_and_write, name='complete_flow'),
    
    # ========== 查询接口 ==========
    
    # 查询PLC写入状态
    path('status/', views_plc_writer.get_plc_write_status, name='get_status'),
    
    # 查询PLC写入历史
    path('history/', views_plc_writer.get_plc_write_history, name='get_history'),
]
