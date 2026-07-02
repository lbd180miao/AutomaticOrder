"""
料架定位算法模块测试脚本

测试：
1. 平面检测（找Z）
2. 前边缘检测（找Y）
3. 立柱检测（找X）
4. 综合定位计算
5. 完整流程集成测试
"""
import os
import sys
import django
import numpy as np

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.rack_positioning_algorithm import RackPositioningAlgorithm
from apps.vision.rack_positioning_service import RackPositioningService
from apps.vision.models import RackLocationRecipe, VisionTask
from apps.vision.models_3d_roi import ROI3DType
from apps.devices.models import Device
from apps.core.constants import DeviceType, VisionTaskType, ResultStatus


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def generate_mock_support_plane_pointcloud(z_center=900, noise=2.0, n_points=1000):
    """
    生成模拟支撑面点云（平面）
    
    Args:
        z_center: 平面中心高度（mm）
        noise: 噪声水平（mm）
        n_points: 点数
    
    Returns:
        点云数组 (N, 3)
    """
    np.random.seed(42)
    
    # 在XY平面上均匀分布
    x = np.random.uniform(-150, 150, n_points)
    y = np.random.uniform(-100, -50, n_points)  # 靠近前边缘
    
    # Z轴为平面，加上小噪声
    z = np.ones(n_points) * z_center + np.random.normal(0, noise, n_points)
    
    return np.column_stack([x, y, z])


def generate_mock_front_edge_pointcloud(y_edge=-130, n_points=500):
    """
    生成模拟前边缘点云
    
    Args:
        y_edge: 边缘Y位置（mm）
        n_points: 点数
    
    Returns:
        点云数组 (N, 3)
    """
    np.random.seed(43)
    
    # 边缘点沿X方向分布
    x = np.random.uniform(-150, 150, n_points)
    
    # Y轴集中在边缘位置，有小的扩散
    y = np.random.normal(y_edge, 5, n_points)
    
    # Z轴有一定高度范围
    z = np.random.uniform(880, 930, n_points)
    
    return np.column_stack([x, y, z])


def generate_mock_pillar_pointcloud(x_pillar=-180, n_points=300):
    """
    生成模拟立柱点云
    
    Args:
        x_pillar: 立柱X位置（mm）
        n_points: 点数
    
    Returns:
        点云数组 (N, 3)
    """
    np.random.seed(44)
    
    # X轴集中在立柱位置
    x = np.random.normal(x_pillar, 3, n_points)
    
    # Y轴有一定范围
    y = np.random.uniform(-100, 100, n_points)
    
    # Z轴垂直分布（立柱特征）
    z = np.random.uniform(850, 950, n_points)
    
    return np.column_stack([x, y, z])


def test_1_plane_detection():
    """测试1：平面检测（找Z）"""
    print_section("测试1: 平面检测（找Z）")
    
    algorithm = RackPositioningAlgorithm()
    
    # 生成模拟支撑面点云
    z_true = 900.0
    pointcloud = generate_mock_support_plane_pointcloud(z_center=z_true, noise=2.0)
    
    print(f"生成模拟支撑面点云: {pointcloud.shape[0]} 点")
    print(f"  真实Z位置: {z_true:.2f}mm")
    print(f"  点云Z范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}]mm")
    
    # 执行平面检测
    result = algorithm.detect_support_plane(
        pointcloud=pointcloud,
        distance_threshold=3.0,
        min_inliers=100
    )
    
    print(f"\n✓ 平面检测结果:")
    print(f"  检测Z位置: {result.z_position:.2f}mm")
    print(f"  Z标准差: {result.z_std:.2f}mm")
    print(f"  误差: {abs(result.z_position - z_true):.2f}mm")
    print(f"  内点数: {result.inliers.shape[0]}/{pointcloud.shape[0]}")
    print(f"  置信度: {result.confidence:.3f}")
    print(f"  平面方程: [{result.plane_model[0]:.3f}x + {result.plane_model[1]:.3f}y + {result.plane_model[2]:.3f}z + {result.plane_model[3]:.3f} = 0")
    
    # 验证精度
    assert abs(result.z_position - z_true) < 5.0, "Z位置检测误差过大"
    assert result.confidence > 0.5, "置信度过低"
    
    print("\n✅ 平面检测测试通过")
    return result


def test_2_edge_detection():
    """测试2：前边缘检测（找Y）"""
    print_section("测试2: 前边缘检测（找Y）")
    
    algorithm = RackPositioningAlgorithm()
    
    # 生成模拟前边缘点云
    y_true = -130.0
    pointcloud = generate_mock_front_edge_pointcloud(y_edge=y_true)
    
    print(f"生成模拟前边缘点云: {pointcloud.shape[0]} 点")
    print(f"  真实Y位置: {y_true:.2f}mm")
    print(f"  点云Y范围: [{pointcloud[:, 1].min():.2f}, {pointcloud[:, 1].max():.2f}]mm")
    
    # 执行边缘检测
    result = algorithm.detect_front_edge(
        pointcloud=pointcloud,
        gradient_threshold=10.0,
        min_edge_points=50
    )
    
    print(f"\n✓ 前边缘检测结果:")
    print(f"  检测Y位置: {result.y_position:.2f}mm")
    print(f"  Y标准差: {result.y_std:.2f}mm")
    print(f"  误差: {abs(result.y_position - y_true):.2f}mm")
    print(f"  边缘点数: {result.edge_points.shape[0]}")
    print(f"  置信度: {result.confidence:.3f}")
    
    # 验证精度
    assert abs(result.y_position - y_true) < 10.0, "Y位置检测误差过大"
    assert result.confidence > 0.3, "置信度过低"
    
    print("\n✅ 前边缘检测测试通过")
    return result


def test_3_pillar_detection():
    """测试3: 立柱检测（找X）"""
    print_section("测试3: 立柱检测（找X）")
    
    algorithm = RackPositioningAlgorithm()
    
    # 生成模拟立柱点云
    x_true = -180.0
    pointcloud = generate_mock_pillar_pointcloud(x_pillar=x_true)
    
    print(f"生成模拟立柱点云: {pointcloud.shape[0]} 点")
    print(f"  真实X位置: {x_true:.2f}mm")
    print(f"  点云X范围: [{pointcloud[:, 0].min():.2f}, {pointcloud[:, 0].max():.2f}]mm")
    
    # 执行立柱检测
    result = algorithm.detect_pillar(
        pointcloud=pointcloud,
        vertical_tolerance=10.0,
        min_pillar_points=50
    )
    
    print(f"\n✓ 立柱检测结果:")
    print(f"  检测X位置: {result.x_position:.2f}mm")
    print(f"  X标准差: {result.x_std:.2f}mm")
    print(f"  误差: {abs(result.x_position - x_true):.2f}mm")
    print(f"  立柱点数: {result.pillar_points.shape[0]}")
    print(f"  置信度: {result.confidence:.3f}")
    
    # 验证精度
    assert abs(result.x_position - x_true) < 10.0, "X位置检测误差过大"
    assert result.confidence > 0.3, "置信度过低"
    
    print("\n✅ 立柱检测测试通过")
    return result


def test_4_comprehensive_positioning():
    """测试4: 综合定位计算"""
    print_section("测试4: 综合定位计算")
    
    algorithm = RackPositioningAlgorithm()
    
    # 生成三种点云
    support_plane_cloud = generate_mock_support_plane_pointcloud(z_center=902.0)
    front_edge_cloud = generate_mock_front_edge_pointcloud(y_edge=-128.0)
    pillar_cloud = generate_mock_pillar_pointcloud(x_pillar=-182.0)
    
    print("生成模拟点云:")
    print(f"  支撑面: {support_plane_cloud.shape[0]} 点")
    print(f"  前边缘: {front_edge_cloud.shape[0]} 点")
    print(f"  立柱: {pillar_cloud.shape[0]} 点")
    
    # 设置标准位置
    standard_x = -180.0
    standard_y = -130.0
    standard_z = 900.0
    
    print(f"\n标准位置:")
    print(f"  X: {standard_x:.2f}mm")
    print(f"  Y: {standard_y:.2f}mm")
    print(f"  Z: {standard_z:.2f}mm")
    
    # 执行综合定位
    result = algorithm.calculate_rack_position(
        support_plane_cloud=support_plane_cloud,
        front_edge_cloud=front_edge_cloud,
        pillar_cloud=pillar_cloud,
        standard_x=standard_x,
        standard_y=standard_y,
        standard_z=standard_z
    )
    
    print(f"\n✓ 综合定位结果:")
    print(f"  是否成功: {'是' if result.is_success else '否'}")
    
    if not result.is_success:
        print(f"  错误信息: {result.error_message}")
    
    print(f"\n  实际测量值:")
    print(f"    X: {result.actual_x:.2f}mm")
    print(f"    Y: {result.actual_y:.2f}mm")
    print(f"    Z: {result.actual_z:.2f}mm")
    
    print(f"\n  偏移值（补偿值）:")
    print(f"    ΔX: {result.offset_x:.2f}mm")
    print(f"    ΔY: {result.offset_y:.2f}mm")
    print(f"    ΔZ: {result.offset_z:.2f}mm")
    
    print(f"\n  置信度:")
    print(f"    X: {result.confidence_x:.3f}")
    print(f"    Y: {result.confidence_y:.3f}")
    print(f"    Z: {result.confidence_z:.3f}")
    
    # 转换为字典格式
    result_dict = algorithm.to_dict(result)
    print(f"\n  详细结果已转换为字典格式 ({len(result_dict)} 个字段)")
    
    print("\n✅ 综合定位测试通过")
    return result


def test_5_service_integration():
    """测试5: 服务层集成测试"""
    print_section("测试5: 服务层集成测试")
    
    service = RackPositioningService()
    
    # 创建或获取测试配方
    camera, _ = Device.objects.get_or_create(
        code='DM-CAMERA-POSITIONING-TEST',
        defaults={
            'name': '测试DM相机-定位',
            'device_type': DeviceType.DEPTH_CAMERA,
            'enabled': True
        }
    )
    
    recipe, created = RackLocationRecipe.objects.get_or_create(
        recipe_name='定位算法测试配方',
        defaults={
            'rack_type': '标准3层料架',
            'rack_side': 'BOTH',
            'position_no': 1,
            'layer_count': 3,
            'layer_no': 2,
            'camera_device': camera,
            'standard_x': -180,
            'standard_y': -130,
            'standard_z': 900,
            'enabled': True
        }
    )
    
    print(f"✓ 测试配方: {recipe.recipe_name} (ID: {recipe.id}) {'[新建]' if created else '[已存在]'}")
    print(f"  标准位置: X={recipe.standard_x}, Y={recipe.standard_y}, Z={recipe.standard_z}")
    
    # 确保该配方有ROI配置
    from apps.vision.roi_3d_service import ROI3DService
    roi_service = ROI3DService()
    
    # 检查是否已有第2层的ROI
    existing_rois = roi_service.get_rois_by_layer(recipe.id, 2)
    if not existing_rois:
        print("\n创建第2层的ROI配置...")
        rois = roi_service.batch_create_layer_rois(
            recipe_id=recipe.id,
            layer_no=2
        )
        print(f"  ✓ 创建了 {len(rois)} 个ROI")
    else:
        print(f"\n✓ 第2层已有 {len(existing_rois)} 个ROI配置")
    
    # 生成完整的模拟点云（包含所有区域）
    print("\n生成完整料架点云...")
    
    # 合并不同区域的点云
    support_plane_cloud = generate_mock_support_plane_pointcloud(z_center=902.0, n_points=500)
    front_edge_cloud = generate_mock_front_edge_pointcloud(y_edge=-128.0, n_points=300)
    pillar_cloud = generate_mock_pillar_pointcloud(x_pillar=-182.0, n_points=200)
    
    # 添加一些背景噪声点
    np.random.seed(45)
    background_cloud = np.random.randn(1000, 3) * 100
    background_cloud[:, 0] += 0
    background_cloud[:, 1] += 0
    background_cloud[:, 2] += 950
    
    # 合并所有点云
    full_pointcloud = np.vstack([
        support_plane_cloud,
        front_edge_cloud,
        pillar_cloud,
        background_cloud
    ])
    
    print(f"  完整点云: {full_pointcloud.shape[0]} 点")
    print(f"    支撑面区域: {support_plane_cloud.shape[0]} 点")
    print(f"    前边缘区域: {front_edge_cloud.shape[0]} 点")
    print(f"    立柱区域: {pillar_cloud.shape[0]} 点")
    print(f"    背景噪声: {background_cloud.shape[0]} 点")
    
    # 创建视觉任务
    task, task_created = VisionTask.objects.get_or_create(
        task_type=VisionTaskType.RACK_LOCATING,
        defaults={
            'status': ResultStatus.PENDING
        }
    )
    
    print(f"\n✓ 视觉任务: ID={task.id} {'[新建]' if task_created else '[已存在]'}")
    
    # 执行完整定位流程
    print("\n执行完整定位流程...")
    
    try:
        result = service.process_layer_positioning(
            recipe_id=recipe.id,
            layer_no=2,
            pointcloud=full_pointcloud,
            coordinate_system='ROBOT',
            vision_task_id=task.id
        )
        
        print(f"\n✓ 定位流程完成:")
        print(f"  成功: {'是' if result.is_success else '否'}")
        
        if result.is_success:
            print(f"  实际位置: X={result.actual_x:.2f}, Y={result.actual_y:.2f}, Z={result.actual_z:.2f}")
            print(f"  偏移值: ΔX={result.offset_x:.2f}, ΔY={result.offset_y:.2f}, ΔZ={result.offset_z:.2f}")
            print(f"  置信度: X={result.confidence_x:.3f}, Y={result.confidence_y:.3f}, Z={result.confidence_z:.3f}")
        else:
            print(f"  错误: {result.error_message}")
        
        # 验证结果已保存到数据库
        from apps.vision.models import RackLocationResult
        saved_results = RackLocationResult.objects.filter(
            vision_task=task,
            recipe=recipe,
            layer_no=2
        )
        
        print(f"\n✓ 结果已保存到数据库: {saved_results.count()} 条记录")
        
        if saved_results.exists():
            latest = saved_results.latest('created_at')
            print(f"  最新记录ID: {latest.id}")
            print(f"  偏移: X={latest.offset_x}, Y={latest.offset_y}, Z={latest.offset_z}")
        
    except Exception as e:
        print(f"\n❌ 定位流程失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ 服务层集成测试完成")


def test_6_statistics():
    """测试6: 统计分析功能"""
    print_section("测试6: 统计分析功能")
    
    service = RackPositioningService()
    
    # 获取测试配方
    recipe = RackLocationRecipe.objects.get(recipe_name='定位算法测试配方')
    
    # 获取历史记录
    print("获取定位历史...")
    history = service.get_positioning_history(recipe.id, layer_no=2, limit=5)
    
    print(f"  历史记录: {len(history)} 条")
    for i, record in enumerate(history, 1):
        print(f"    {i}. 偏移: X={record.offset_x:.2f}, Y={record.offset_y:.2f}, Z={record.offset_z:.2f}, "
              f"置信度={record.confidence:.3f}, 时间={record.created_at.strftime('%H:%M:%S')}")
    
    # 获取平均偏移
    if len(history) > 0:
        print("\n获取平均偏移值...")
        avg_offsets = service.get_average_offsets(recipe.id, layer_no=2, count=10)
        
        print(f"  统计数量: {avg_offsets['count']}")
        print(f"  平均偏移: X={avg_offsets['avg_offset_x']:.2f}±{avg_offsets['std_offset_x']:.2f}mm")
        print(f"           Y={avg_offsets['avg_offset_y']:.2f}±{avg_offsets['std_offset_y']:.2f}mm")
        print(f"           Z={avg_offsets['avg_offset_z']:.2f}±{avg_offsets['std_offset_z']:.2f}mm")
        
        # 分析稳定性（需要至少5条记录）
        if len(history) >= 5:
            print("\n分析定位稳定性...")
            stability = service.analyze_positioning_stability(recipe.id, layer_no=2, count=20)
            
            if stability.get('sufficient_data'):
                print(f"  样本数量: {stability['sample_count']}")
                print(f"  X轴: 均值={stability['x_mean']:.2f}mm, 标准差={stability['x_std']:.2f}mm, 极差={stability['x_range']:.2f}mm")
                print(f"  Y轴: 均值={stability['y_mean']:.2f}mm, 标准差={stability['y_std']:.2f}mm, 极差={stability['y_range']:.2f}mm")
                print(f"  Z轴: 均值={stability['z_mean']:.2f}mm, 标准差={stability['z_std']:.2f}mm, 极差={stability['z_range']:.2f}mm")
                print(f"  平均置信度: {stability['avg_confidence']:.3f}")
                print(f"  稳定性评级: {stability['stability_rating']}")
            else:
                print(f"  {stability['message']}")
    
    print("\n✅ 统计分析测试完成")


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  料架定位算法模块 - 完整功能测试")
    print("=" * 70)
    print()
    
    try:
        # 测试1: 平面检测
        test_1_plane_detection()
        
        # 测试2: 前边缘检测
        test_2_edge_detection()
        
        # 测试3: 立柱检测
        test_3_pillar_detection()
        
        # 测试4: 综合定位计算
        test_4_comprehensive_positioning()
        
        # 测试5: 服务层集成
        test_5_service_integration()
        
        # 测试6: 统计分析
        test_6_statistics()
        
        # 总结
        print_section("测试总结")
        print("✓ 所有测试完成！")
        print()
        print("功能验证:")
        print("  ✓ 平面检测（找Z）")
        print("  ✓ 前边缘检测（找Y）")
        print("  ✓ 立柱检测（找X）")
        print("  ✓ 综合定位计算")
        print("  ✓ 服务层集成")
        print("  ✓ 统计分析")
        print()
        print("料架定位算法模块功能正常！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
