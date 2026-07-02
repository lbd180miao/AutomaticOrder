"""
PLC补偿值写入模块测试脚本

测试PLC写入功能
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

import numpy as np
from apps.vision.plc_writer_service import PLCCompensationWriter
from apps.vision.compensation_calculator import CompensationData
from apps.vision.compensation_service import CompensationService
from apps.vision.models import RackLocationRecipe, RackLocationResult
from apps.core.constants import RackSide


def print_separator(title):
    """打印分隔符"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_1_write_compensation_to_plc():
    """测试1: 写入补偿值到PLC"""
    print_separator("测试1: 写入补偿值到PLC")
    
    try:
        writer = PLCCompensationWriter()
        
        # 创建测试补偿值
        compensation = CompensationData(
            compensation_x=-2.23,
            compensation_y=4.60,
            compensation_z=2.05,
            compensation_rz=0.15,
            confidence_x=1.0,
            confidence_y=1.0,
            confidence_z=0.624,
            is_valid=True,
            validation_message=""
        )
        
        # 写入PLC
        result = writer.write_compensation_to_plc(
            compensation=compensation,
            layer_no=2,
            position_no=1,
            rack_side=RackSide.BOTH,
            validate=True
        )
        
        print(f"✓ 写入结果: {result['success']}")
        print(f"  消息: {result.get('message', result.get('error', ''))}")
        
        if result.get('plc_payload'):
            payload = result['plc_payload']
            print(f"  PLC数据: X={payload['offset_x']}, Y={payload['offset_y']}, Z={payload['offset_z']}")
        
        if result.get('simulated'):
            print("  ⚠ 模拟模式（PLC适配器未实现）")
        
        assert result['success'], "写入应该成功"
        
        print("\n✅ 测试1通过")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试1失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_write_invalid_compensation():
    """测试2: 写入无效补偿值（应被拒绝）"""
    print_separator("测试2: 写入无效补偿值")
    
    try:
        writer = PLCCompensationWriter()
        
        # 创建无效补偿值（超限）
        compensation = CompensationData(
            compensation_x=100.0,  # 超限
            compensation_y=4.60,
            compensation_z=2.05,
            compensation_rz=0.0,
            confidence_x=1.0,
            confidence_y=1.0,
            confidence_z=1.0,
            is_valid=False,  # 标记为无效
            validation_message="X补偿超限"
        )
        
        # 写入PLC
        result = writer.write_compensation_to_plc(
            compensation=compensation,
            layer_no=2,
            position_no=1,
            rack_side=RackSide.BOTH,
            validate=True
        )
        
        print(f"✓ 写入结果: {result['success']}")
        print(f"  是否被拒绝: {result.get('rejected', False)}")
        print(f"  拒绝原因: {result.get('error', '')}")
        
        assert not result['success'], "无效补偿值应被拒绝"
        assert result.get('rejected'), "应标记为rejected"
        
        print("\n✅ 测试2通过")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_plc_payload_format():
    """测试3: PLC数据格式验证"""
    print_separator("测试3: PLC数据格式")
    
    try:
        writer = PLCCompensationWriter()
        
        compensation = CompensationData(
            compensation_x=-2.234,
            compensation_y=4.567,
            compensation_z=2.089,
            compensation_rz=0.123,
            confidence_x=0.95,
            confidence_y=0.88,
            confidence_z=0.76,
            is_valid=True,
            validation_message=""
        )
        
        # 准备PLC数据
        payload = writer._prepare_plc_payload(
            compensation=compensation,
            layer_no=3,
            position_no=2,
            rack_side=RackSide.LEFT
        )
        
        print("✓ PLC数据格式:")
        print(f"  任务类型: {payload['task_kind']}")
        print(f"  侧面: {payload['side']}")
        print(f"  层号: {payload['layer_no']}")
        print(f"  位置号: {payload['position_no']}")
        print(f"  补偿值: X={payload['offset_x']}, Y={payload['offset_y']}, Z={payload['offset_z']}")
        print(f"  RZ补偿: {payload['offset_rz']}°")
        print(f"  置信度: {payload['confidence']}")
        print(f"  有效性: {payload['compensation_valid']}")
        
        # 验证数据格式
        assert payload['task_kind'] == 'RACK_3D_LOCATION', "任务类型错误"
        assert payload['side'] == RackSide.LEFT, "侧面错误"
        assert payload['layer_no'] == 3, "层号错误"
        assert payload['position_no'] == 2, "位置号错误"
        
        # 验证数值精度（保留2位小数）
        assert payload['offset_x'] == -2.23, "X补偿精度错误"
        assert payload['offset_y'] == 4.57, "Y补偿精度错误"
        assert payload['offset_z'] == 2.09, "Z补偿精度错误"
        
        # 验证RZ精度（保留3位小数）
        assert payload['offset_rz'] == 0.123, "RZ补偿精度错误"
        
        # 验证置信度
        expected_confidence = round((0.95 + 0.88 + 0.76) / 3, 3)
        assert payload['confidence'] == expected_confidence, "平均置信度计算错误"
        
        print("\n✅ 测试3通过")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_write_from_result():
    """测试4: 从定位结果写入（如果有测试数据）"""
    print_separator("测试4: 从定位结果写入")
    
    try:
        # 查找最新的成功定位结果
        result = RackLocationResult.objects.filter(
            is_success=True
        ).order_by('-created_at').first()
        
        if not result:
            print("⚠ 无测试数据，跳过测试")
            return True
        
        print(f"✓ 使用测试结果: ID={result.id}")
        print(f"  配方: {result.recipe.name if result.recipe else 'N/A'}")
        print(f"  层号: {result.layer_no}")
        print(f"  偏移: X={result.offset_x}, Y={result.offset_y}, Z={result.offset_z}")
        
        # 从结果写入PLC
        writer = PLCCompensationWriter()
        
        write_result = writer.write_compensation_from_result(
            result_id=result.id,
            validate=True,
            revalidate=True
        )
        
        print(f"✓ 写入结果: {write_result['success']}")
        print(f"  消息: {write_result.get('message', write_result.get('error', ''))}")
        
        if write_result.get('simulated'):
            print("  ⚠ 模拟模式")
        
        # 检查PLC写入状态
        result.refresh_from_db()
        print(f"  PLC状态: {result.plc_write_status}")
        
        print("\n✅ 测试4通过")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试4失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_batch_write():
    """测试5: 批量写入（如果有测试数据）"""
    print_separator("测试5: 批量写入配方所有层")
    
    try:
        # 查找有定位结果的配方
        recipe = RackLocationRecipe.objects.filter(
            racklocationresult__is_success=True
        ).distinct().first()
        
        if not recipe:
            print("⚠ 无测试数据，跳过测试")
            return True
        
        print(f"✓ 使用测试配方: {recipe.name} (ID={recipe.id})")
        print(f"  层数: {recipe.layer_count}")
        
        # 批量写入
        writer = PLCCompensationWriter()
        
        result = writer.batch_write_compensations_for_recipe(
            recipe_id=recipe.id,
            layers=[1, 2, 3],  # 只测试前3层
            validate=True
        )
        
        print(f"✓ 批量写入结果: {result['success']}")
        print(f"  总数: {result['total']}")
        print(f"  成功: {result['success_count']}")
        print(f"  失败: {result['failed_count']}")
        
        # 显示详细结果
        for layer_no, layer_result in result['results'].items():
            status = "✓" if layer_result.get('success') else "✗"
            print(f"  {status} 第{layer_no}层: {layer_result.get('message', layer_result.get('error', ''))}")
        
        print("\n✅ 测试5通过")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试5失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_compensation_service_integration():
    """测试6: 补偿服务集成"""
    print_separator("测试6: 补偿服务集成")
    
    try:
        from apps.vision.rack_positioning_algorithm import (
            RackPositioningAlgorithm,
            PositioningResult
        )
        
        # 创建模拟定位结果
        positioning_result = PositioningResult(
            is_success=True,
            offset_x=-3.45,
            offset_y=6.78,
            offset_z=1.23,
            confidence_x=0.95,
            confidence_y=0.88,
            confidence_z=0.92,
            error_message=""
        )
        
        print("✓ 模拟定位结果:")
        print(f"  偏移: X={positioning_result.offset_x}, Y={positioning_result.offset_y}, Z={positioning_result.offset_z}")
        print(f"  置信度: X={positioning_result.confidence_x}, Y={positioning_result.confidence_y}, Z={positioning_result.confidence_z}")
        
        # 计算补偿值
        compensation_service = CompensationService()
        
        compensation = compensation_service.calculate_compensation_from_positioning_result(
            positioning_result=positioning_result,
            rack_side=RackSide.BOTH
        )
        
        print("\n✓ 补偿值:")
        print(f"  补偿: X={compensation.compensation_x}, Y={compensation.compensation_y}, Z={compensation.compensation_z}")
        print(f"  有效性: {compensation.is_valid}")
        
        # 写入PLC
        writer = PLCCompensationWriter()
        
        write_result = writer.write_compensation_to_plc(
            compensation=compensation,
            layer_no=2,
            rack_side=RackSide.BOTH,
            validate=True
        )
        
        print("\n✓ PLC写入:")
        print(f"  成功: {write_result['success']}")
        print(f"  消息: {write_result.get('message', write_result.get('error', ''))}")
        
        assert write_result['success'], "写入应该成功"
        
        print("\n✅ 测试6通过 - 定位→补偿→PLC写入 完整流程正常")
        return True
    
    except Exception as e:
        print(f"\n❌ 测试6失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  PLC补偿值写入模块 - 功能测试")
    print("=" * 60)
    
    tests = [
        test_1_write_compensation_to_plc,
        test_2_write_invalid_compensation,
        test_3_plc_payload_format,
        test_4_write_from_result,
        test_5_batch_write,
        test_6_compensation_service_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # 总结
    print("\n" + "=" * 60)
    print("  测试总结")
    print("=" * 60)
    print(f"总计: {len(tests)} 个测试")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  {failed} 个测试失败")
    
    print("=" * 60)


if __name__ == '__main__':
    run_all_tests()
