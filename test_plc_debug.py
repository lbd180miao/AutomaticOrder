#!/usr/bin/env python
"""测试 PLC 调试功能的简单脚本"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.devices.services import get_plc_adapter
from apps.devices.plc_db100 import POINTS_BY_NAME

def test_read_product_barcode():
    """测试读取产品条码"""
    print("=" * 60)
    print("测试 PLC 调试功能 - 读取产品条码")
    print("=" * 60)
    
    try:
        # 获取 PLC 适配器
        adapter = get_plc_adapter()
        print(f"✓ PLC 适配器获取成功")
        print(f"  连接状态: {adapter.is_online()}")
        
        # 读取产品条码点位
        point_name = 'product_barcode'
        point = POINTS_BY_NAME[point_name]
        
        print(f"\n读取点位信息:")
        print(f"  点位名称: {point.name}")
        print(f"  点位说明: {point.description}")
        print(f"  数据类型: {point.data_type}")
        print(f"  方向: {point.direction}")
        print(f"  DB100 地址: DBB{point.offset}")
        
        # 读取值
        value = adapter.read_point(point_name)
        print(f"\n读取结果:")
        print(f"  值: {value}")
        print(f"  类型: {type(value)}")
        
        print("\n✓ 测试成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_read_multiple_points():
    """测试读取多个点位"""
    print("\n" + "=" * 60)
    print("测试读取多个点位")
    print("=" * 60)
    
    test_points = [
        'product_barcode',
        'rack_barcode',
        'heartbeat',
        'mark_trigger',
        'rack_trigger',
        'workstation_locked',
    ]
    
    try:
        adapter = get_plc_adapter()
        
        for point_name in test_points:
            point = POINTS_BY_NAME[point_name]
            value = adapter.read_point(point_name)
            print(f"  {point.description:30s} = {value}")
        
        print("\n✓ 多点位读取测试成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success1 = test_read_product_barcode()
    success2 = test_read_multiple_points()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("所有测试通过！")
        sys.exit(0)
    else:
        print("部分测试失败")
        sys.exit(1)
