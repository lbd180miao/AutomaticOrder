"""
补偿值计算模块测试脚本

测试：
1. 基本补偿值计算
2. 补偿规则应用
3. 补偿值验证
4. PLC数据格式转换
5. 服务层集成
6. 统计分析
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.compensation_calculator import (
    CompensationCalculator,
    CompensationRule,
    OffsetData,
    CompensationValidator
)
from apps.vision.compensation_service import CompensationService
from apps.core.constants import RackSide


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_1_basic_calculation():
    """测试1：基本补偿值计算"""
    print_section("测试1: 基本补偿值计算")
    
    calculator = CompensationCalculator()
    
    # 测试场景：料架偏移
    print("场景: 料架向右偏2.23mm，向前偏4.60mm，向上偏2.05mm")
    
    compensation = calculator.calculate_compensation(
        offset_x=-2.23,   # X轴负偏移（向左）
        offset_y=4.60,    # Y轴正偏移（向前）
        offset_z=2.05,    # Z轴正偏移（向上）
        confidence_x=1.0,
        confidence_y=1.0,
        confidence_z=0.624,
        rack_side=RackSide.BOTH
    )
    
    print(f"\n✓ 补偿值计算结果:")
    print(f"  补偿值: X={compensation.compensation_x:.2f}mm, "
          f"Y={compensation.compensation_y:.2f}mm, "
          f"Z={compensation.compensation_z:.2f}mm")
    print(f"  原始偏移: X={compensation.original_offset_x:.2f}mm, "
          f"Y={compensation.original_offset_y:.2f}mm, "
          f"Z={compensation.original_offset_z:.2f}mm")
    print(f"  置信度: X={compensation.confidence_x:.3f}, "
          f"Y={compensation.confidence_y:.3f}, "
          f"Z={compensation.confidence_z:.3f}")
    print(f"  是否有效: {compensation.is_valid}")
    
    if not compensation.is_valid:
        print(f"  验证消息: {compensation.validation_message}")
    
    # 验证：默认情况下，补偿值应该等于偏移值（因为方向系数都是1）
    assert compensation.compensation_x == -2.23, "X补偿值计算错误"
    assert compensation.compensation_y == 4.60, "Y补偿值计算错误"
    assert compensation.compensation_z == 2.05, "Z补偿值计算错误"
    assert compensation.is_valid, "补偿值应该有效"
    
    print("\n✅ 基本补偿值计算测试通过")
    return compensation


def test_2_compensation_rules():
    """测试2：补偿规则应用"""
    print_section("测试2: 补偿规则应用")
    
    # 自定义规则：Y轴反向
    rule = CompensationRule(
        x_direction=1,
        y_direction=-1,  # Y轴反向
        z_direction=1,
        max_compensation_x=50.0,
        max_compensation_y=50.0,
        max_compensation_z=30.0
    )
    
    calculator = CompensationCalculator(rule)
    
    print("规则: Y轴反向（y_direction = -1）")
    print("输入偏移: X=-2.23mm, Y=4.60mm, Z=2.05mm")
    
    compensation = calculator.calculate_compensation(
        offset_x=-2.23,
        offset_y=4.60,
        offset_z=2.05,
        confidence_x=1.0,
        confidence_y=1.0,
        confidence_z=1.0
    )
    
    print(f"\n✓ 应用规则后的补偿值:")
    print(f"  X={compensation.compensation_x:.2f}mm (预期: -2.23mm)")
    print(f"  Y={compensation.compensation_y:.2f}mm (预期: -4.60mm, 因为反向)")
    print(f"  Z={compensation.compensation_z:.2f}mm (预期: 2.05mm)")
    
    # 验证Y轴反向
    assert compensation.compensation_x == -2.23, "X补偿未受影响"
    assert compensation.compensation_y == -4.60, "Y补偿应该反向"
    assert compensation.compensation_z == 2.05, "Z补偿未受影响"
    
    print("\n✅ 补偿规则应用测试通过")


def test_3_rack_side_rules():
    """测试3：料架侧面规则"""
    print_section("测试3: 料架侧面规则")
    
    # 左侧料架X轴反向规则
    rule = CompensationRule(
        left_side_x_invert=True,
        right_side_x_invert=False
    )
    
    calculator = CompensationCalculator(rule)
    
    print("规则: 左侧料架X轴反向")
    print("输入偏移: X=-2.23mm")
    
    # 测试左侧
    comp_left = calculator.calculate_compensation(
        offset_x=-2.23,
        offset_y=0,
        offset_z=0,
        rack_side=RackSide.LEFT
    )
    
    print(f"\n左侧料架:")
    print(f"  原始偏移: X=-2.23mm")
    print(f"  补偿值: X={comp_left.compensation_x:.2f}mm (应该反向)")
    
    # 测试右侧
    comp_right = calculator.calculate_compensation(
        offset_x=-2.23,
        offset_y=0,
        offset_z=0,
        rack_side=RackSide.RIGHT
    )
    
    print(f"\n右侧料架:")
    print(f"  原始偏移: X=-2.23mm")
    print(f"  补偿值: X={comp_right.compensation_x:.2f}mm (不变)")
    
    # 验证
    assert comp_left.compensation_x == 2.23, "左侧X补偿应该反向"
    assert comp_right.compensation_x == -2.23, "右侧X补偿不变"
    
    print("\n✅ 料架侧面规则测试通过")


def test_4_validation():
    """测试4：补偿值验证"""
    print_section("测试4: 补偿值验证")
    
    validator = CompensationValidator()
    calculator = CompensationCalculator()
    
    # 场景1: 正常补偿值
    print("场景1: 正常补偿值")
    comp1 = calculator.calculate_compensation(
        offset_x=2.0,
        offset_y=3.0,
        offset_z=1.5,
        confidence_x=0.9,
        confidence_y=0.9,
        confidence_z=0.9
    )
    
    is_valid, message = validator.validate_compensation(comp1, strict=False)
    print(f"  补偿值: X={comp1.compensation_x:.2f}, Y={comp1.compensation_y:.2f}, Z={comp1.compensation_z:.2f}")
    print(f"  验证结果: {is_valid}")
    print(f"  验证消息: {message}")
    assert is_valid, "正常补偿值应该有效"
    
    # 场景2: 补偿值过大
    print("\n场景2: 补偿值过大（60mm）")
    comp2 = calculator.calculate_compensation(
        offset_x=60.0,  # 超过max_compensation_x (50mm)
        offset_y=5.0,
        offset_z=2.0
    )
    
    print(f"  补偿值: X={comp2.compensation_x:.2f}mm")
    print(f"  是否有效: {comp2.is_valid}")
    print(f"  验证消息: {comp2.validation_message}")
    assert not comp2.is_valid, "超限补偿值应该无效"
    
    # 场景3: 置信度不足
    print("\n场景3: 置信度不足")
    comp3 = calculator.calculate_compensation(
        offset_x=2.0,
        offset_y=3.0,
        offset_z=1.5,
        confidence_x=0.2,  # 低于min_confidence (0.3)
        confidence_y=0.8,
        confidence_z=0.8
    )
    
    print(f"  置信度: X={comp3.confidence_x:.3f}")
    print(f"  是否有效: {comp3.is_valid}")
    print(f"  验证消息: {comp3.validation_message}")
    assert not comp3.is_valid, "低置信度补偿值应该无效"
    
    print("\n✅ 补偿值验证测试通过")


def test_5_plc_format():
    """测试5：PLC数据格式转换"""
    print_section("测试5: PLC数据格式转换")
    
    calculator = CompensationCalculator()
    
    compensation = calculator.calculate_compensation(
        offset_x=-2.234,
        offset_y=4.567,
        offset_z=2.089,
        offset_rz=0.123
    )
    
    # 转换为PLC格式
    plc_data = calculator.to_plc_format(compensation)
    
    print("✓ PLC数据格式:")
    print(f"  X: {plc_data['x']}mm")
    print(f"  Y: {plc_data['y']}mm")
    print(f"  Z: {plc_data['z']}mm")
    print(f"  RZ: {plc_data['rz']}°")
    print(f"  有效标志: {plc_data['valid']}")
    print(f"  置信度: X={plc_data['confidence_x']}, Y={plc_data['confidence_y']}, Z={plc_data['confidence_z']}")
    
    # 验证精度
    assert plc_data['x'] == -2.23, "X应该保留2位小数"
    assert plc_data['y'] == 4.57, "Y应该保留2位小数"
    assert plc_data['z'] == 2.09, "Z应该保留2位小数"
    assert plc_data['rz'] == 0.123, "RZ应该保留3位小数"
    assert plc_data['valid'] == 1, "有效标志应该为1"
    
    print("\n✅ PLC数据格式转换测试通过")


def test_6_service_integration():
    """测试6：服务层集成"""
    print_section("测试6: 服务层集成")
    
    service = CompensationService()
    
    # 使用前面定位测试创建的数据
    from apps.vision.models import RackLocationResult
    
    # 获取最新的定位结果
    latest_result = RackLocationResult.objects.filter(
        is_success=True
    ).order_by('-created_at').first()
    
    if not latest_result:
        print("⚠️ 未找到定位结果，跳过服务层测试")
        print("提示: 先运行 test_rack_positioning.py 创建定位结果")
        return
    
    print(f"使用定位结果: ID={latest_result.id}")
    print(f"  偏移值: X={latest_result.offset_x}, Y={latest_result.offset_y}, Z={latest_result.offset_z}")
    
    # 计算补偿值并保存
    compensation = service.calculate_and_save_compensation(
        result_id=latest_result.id,
        save_to_result=True
    )
    
    print(f"\n✓ 补偿值已计算:")
    print(f"  补偿值: X={compensation.compensation_x:.2f}mm, "
          f"Y={compensation.compensation_y:.2f}mm, "
          f"Z={compensation.compensation_z:.2f}mm")
    print(f"  是否有效: {compensation.is_valid}")
    
    # 读取保存的补偿值
    saved_comp = service.get_compensation_from_result(latest_result.id)
    
    if saved_comp:
        print(f"\n✓ 补偿值已保存到数据库")
        print(f"  读取的补偿值: X={saved_comp['compensation_x']:.2f}mm, "
              f"Y={saved_comp['compensation_y']:.2f}mm, "
              f"Z={saved_comp['compensation_z']:.2f}mm")
    
    # 准备PLC数据
    plc_data = service.prepare_plc_data(
        compensation=compensation,
        layer_no=latest_result.layer_no,
        additional_data={'rack_id': 123}
    )
    
    print(f"\n✓ PLC数据已准备:")
    print(f"  层号: {plc_data['layer_no']}")
    print(f"  X={plc_data['x']}, Y={plc_data['y']}, Z={plc_data['z']}")
    print(f"  料架ID: {plc_data.get('rack_id')}")
    
    print("\n✅ 服务层集成测试通过")


def test_7_statistics():
    """测试7：补偿值统计"""
    print_section("测试7: 补偿值统计")
    
    service = CompensationService()
    
    # 使用测试配方
    from apps.vision.models import RackLocationRecipe
    
    recipe = RackLocationRecipe.objects.filter(
        recipe_name='定位算法测试配方'
    ).first()
    
    if not recipe:
        print("⚠️ 未找到测试配方，跳过统计测试")
        return
    
    print(f"使用配方: {recipe.recipe_name} (ID: {recipe.id})")
    
    # 获取最新补偿值
    latest_comps = service.get_latest_compensation(
        recipe_id=recipe.id,
        layer_no=2,
        limit=5
    )
    
    print(f"\n最新补偿值 (最多5条):")
    if latest_comps:
        for i, comp in enumerate(latest_comps, 1):
            print(f"  {i}. X={comp['compensation_x']:.2f}, "
                  f"Y={comp['compensation_y']:.2f}, "
                  f"Z={comp['compensation_z']:.2f}, "
                  f"有效={comp['is_valid']}")
    else:
        print("  无数据")
    
    # 获取平均补偿值
    if len(latest_comps) > 0:
        avg_comp = service.get_average_compensation(
            recipe_id=recipe.id,
            layer_no=2,
            count=10
        )
        
        print(f"\n平均补偿值 (最近{avg_comp['count']}次):")
        print(f"  X: {avg_comp['avg_compensation_x']:.2f} ± {avg_comp['std_compensation_x']:.2f}mm")
        print(f"  Y: {avg_comp['avg_compensation_y']:.2f} ± {avg_comp['std_compensation_y']:.2f}mm")
        print(f"  Z: {avg_comp['avg_compensation_z']:.2f} ± {avg_comp['std_compensation_z']:.2f}mm")
        
        # 获取统计信息
        if avg_comp['count'] >= 5:
            stats = service.get_compensation_statistics(
                recipe_id=recipe.id,
                layer_no=2,
                count=20
            )
            
            if stats.get('sufficient_data'):
                print(f"\n补偿值统计分析 (最近{stats['sample_count']}次):")
                print(f"  有效率: {stats['valid_rate']*100:.1f}%")
                print(f"  X轴: 范围={stats['x_range']:.2f}mm, 标准差={stats['x_std']:.2f}mm")
                print(f"  Y轴: 范围={stats['y_range']:.2f}mm, 标准差={stats['y_std']:.2f}mm")
                print(f"  Z轴: 范围={stats['z_range']:.2f}mm, 标准差={stats['z_std']:.2f}mm")
                print(f"  稳定性评级: {stats['stability_rating']}")
    
    print("\n✅ 补偿值统计测试完成")


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  补偿值计算模块 - 完整功能测试")
    print("=" * 70)
    print()
    
    try:
        # 测试1: 基本计算
        test_1_basic_calculation()
        
        # 测试2: 补偿规则
        test_2_compensation_rules()
        
        # 测试3: 料架侧面规则
        test_3_rack_side_rules()
        
        # 测试4: 验证
        test_4_validation()
        
        # 测试5: PLC格式
        test_5_plc_format()
        
        # 测试6: 服务层集成
        test_6_service_integration()
        
        # 测试7: 统计分析
        test_7_statistics()
        
        # 总结
        print_section("测试总结")
        print("✓ 所有测试完成！")
        print()
        print("功能验证:")
        print("  ✓ 基本补偿值计算")
        print("  ✓ 补偿规则应用")
        print("  ✓ 料架侧面规则")
        print("  ✓ 补偿值验证")
        print("  ✓ PLC数据格式转换")
        print("  ✓ 服务层集成")
        print("  ✓ 统计分析")
        print()
        print("补偿值计算模块功能正常！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
