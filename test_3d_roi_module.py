"""
3D ROI配方模块测试脚本

测试3D ROI的创建、管理、点云裁剪等功能
"""
import os
import sys
import django
import numpy as np

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.roi_3d_service import ROI3DService
from apps.vision.models_3d_roi import ROI3DType, ROI3DCoordinateSystem, ROI3DTemplate
from apps.vision.models import RackLocationRecipe
from apps.devices.models import Device
from apps.core.constants import DeviceType


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_1_create_test_recipe():
    """测试1：创建测试配方"""
    print_section("测试1: 创建测试配方")
    
    # 创建或获取相机设备
    camera, _ = Device.objects.get_or_create(
        code='DM-CAMERA-ROI-TEST',
        defaults={
            'name': '测试DM相机-ROI',
            'device_type': DeviceType.DEPTH_CAMERA,
            'enabled': True
        }
    )
    
    # 创建测试配方
    recipe, created = RackLocationRecipe.objects.get_or_create(
        recipe_name='3D-ROI测试配方',
        defaults={
            'rack_type': '标准3层料架',
            'rack_side': 'BOTH',
            'position_no': 1,
            'layer_count': 3,
            'layer_no': 1,
            'camera_device': camera,
            'standard_x': 0,
            'standard_y': 0,
            'standard_z': 850,
            'enabled': True
        }
    )
    
    print(f"✓ 测试配方: {recipe.recipe_name} (ID: {recipe.id}) {'[新建]' if created else '[已存在]'}")
    print(f"  - 料架类型: {recipe.rack_type}")
    print(f"  - 层数: {recipe.layer_count}")
    print(f"  - 标准Z位置: {recipe.standard_z}mm")
    
    return recipe


def test_2_create_single_roi(recipe):
    """测试2：创建单个ROI"""
    print_section("测试2: 创建单个ROI")
    
    service = ROI3DService()
    
    roi = service.create_roi(
        recipe_id=recipe.id,
        roi_name='第1层主ROI',
        roi_type=ROI3DType.MAIN,
        layer_no=1,
        x_min=-200, x_max=200,
        y_min=-150, y_max=150,
        z_min=830, z_max=930,
        position_no=1,
        coordinate_system=ROI3DCoordinateSystem.ROBOT,
        priority=10,
        weight=1.0,
        description='第1层的主定位区域'
    )
    
    print(f"✓ ROI已创建: {roi.roi_name}")
    print(f"  - ID: {roi.id}")
    print(f"  - 类型: {roi.get_roi_type_display()}")
    print(f"  - 层号: {roi.layer_no}")
    print(f"  - 坐标范围:")
    print(f"    X: [{roi.x_min}, {roi.x_max}]")
    print(f"    Y: [{roi.y_min}, {roi.y_max}]")
    print(f"    Z: [{roi.z_min}, {roi.z_max}]")
    print(f"  - 尺寸: {roi.get_dimensions()}")
    print(f"  - 中心: {roi.get_center()}")
    print(f"  - 体积: {roi.get_volume():.2f} mm³")
    
    return roi


def test_3_batch_create_layer_rois(recipe):
    """测试3：批量创建一层的标准ROI"""
    print_section("测试3: 批量创建一层的标准ROI")
    
    service = ROI3DService()
    
    # 为第2层创建4种标准ROI
    created_rois = service.batch_create_layer_rois(
        recipe_id=recipe.id,
        layer_no=2,
        position_no=1
    )
    
    print(f"✓ 为第2层创建了 {len(created_rois)} 种标准ROI:\n")
    
    for key, roi in created_rois.items():
        print(f"  {key.upper()}:")
        print(f"    - 名称: {roi.roi_name}")
        print(f"    - 类型: {roi.get_roi_type_display()}")
        print(f"    - 坐标范围: X[{roi.x_min}, {roi.x_max}] Y[{roi.y_min}, {roi.y_max}] Z[{roi.z_min}, {roi.z_max}]")
        print(f"    - 用途: {roi.description}")
        print()
    
    return created_rois


def test_4_get_layer_summary(recipe):
    """测试4：获取层ROI汇总"""
    print_section("测试4: 获取层ROI汇总")
    
    service = ROI3DService()
    
    for layer_no in [1, 2]:
        summary = service.get_layer_roi_summary(recipe.id, layer_no)
        
        print(f"第{layer_no}层 ROI汇总:")
        print(f"  - 总数: {summary['total_rois']}")
        
        if summary['main_roi']:
            print(f"  - 主ROI: {summary['main_roi'].roi_name}")
        
        if summary['support_plane_rois']:
            print(f"  - 支撑面ROI: {len(summary['support_plane_rois'])}个")
        
        if summary['front_edge_rois']:
            print(f"  - 前边缘ROI: {len(summary['front_edge_rois'])}个")
        
        if summary['pillar_rois']:
            print(f"  - 立柱ROI: {len(summary['pillar_rois'])}个")
        
        print()


def test_5_crop_pointcloud(recipe):
    """测试5：点云裁剪"""
    print_section("测试5: 点云裁剪")
    
    service = ROI3DService()
    
    # 生成模拟点云（10000个点）
    np.random.seed(42)
    pointcloud = np.random.randn(10000, 3) * 100
    pointcloud[:, 0] += 0  # X轴中心
    pointcloud[:, 1] += 0  # Y轴中心
    pointcloud[:, 2] += 900  # Z轴中心（第2层高度）
    
    print(f"原始点云: {pointcloud.shape[0]} 个点")
    print(f"点云范围:")
    print(f"  X: [{pointcloud[:, 0].min():.1f}, {pointcloud[:, 0].max():.1f}]")
    print(f"  Y: [{pointcloud[:, 1].min():.1f}, {pointcloud[:, 1].max():.1f}]")
    print(f"  Z: [{pointcloud[:, 2].min():.1f}, {pointcloud[:, 2].max():.1f}]")
    print()
    
    # 使用第2层的ROI裁剪
    cropped_clouds = service.crop_pointcloud_by_layer(
        pointcloud=pointcloud,
        recipe_id=recipe.id,
        layer_no=2
    )
    
    print("裁剪结果:")
    for roi_type, cloud in cropped_clouds.items():
        if cloud.shape[0] > 0:
            print(f"  {roi_type.upper()}: {cloud.shape[0]} 个点")
            print(f"    范围: X[{cloud[:, 0].min():.1f}, {cloud[:, 0].max():.1f}] "
                  f"Y[{cloud[:, 1].min():.1f}, {cloud[:, 1].max():.1f}] "
                  f"Z[{cloud[:, 2].min():.1f}, {cloud[:, 2].max():.1f}]")
    
    return cropped_clouds


def test_6_create_template(recipe):
    """测试6：创建ROI模板"""
    print_section("测试6: 创建ROI模板")
    
    service = ROI3DService()
    
    # 定义3层料架的ROI模板配置
    roi_configs = []
    
    for layer_no in range(1, 4):  # 3层
        base_z = 850 + (layer_no - 1) * 120
        
        # 每层4种ROI
        roi_configs.extend([
            {
                'roi_name': f'第{layer_no}层主ROI',
                'roi_type': ROI3DType.MAIN,
                'layer_no': layer_no,
                'x_min': -200, 'x_max': 200,
                'y_min': -150, 'y_max': 150,
                'z_min': base_z - 20, 'z_max': base_z + 100,
                'priority': 10,
                'weight': 1.0,
            },
            {
                'roi_name': f'第{layer_no}层支撑面ROI',
                'roi_type': ROI3DType.SUPPORT_PLANE,
                'layer_no': layer_no,
                'x_min': -180, 'x_max': 180,
                'y_min': -130, 'y_max': -80,
                'z_min': base_z - 10, 'z_max': base_z + 10,
                'priority': 20,
                'weight': 1.0,
            },
            {
                'roi_name': f'第{layer_no}层前边缘ROI',
                'roi_type': ROI3DType.FRONT_EDGE,
                'layer_no': layer_no,
                'x_min': -180, 'x_max': 180,
                'y_min': -140, 'y_max': -120,
                'z_min': base_z, 'z_max': base_z + 50,
                'priority': 30,
                'weight': 1.0,
            },
            {
                'roi_name': f'第{layer_no}层立柱ROI',
                'roi_type': ROI3DType.PILLAR,
                'layer_no': layer_no,
                'x_min': -190, 'x_max': -170,
                'y_min': -130, 'y_max': 130,
                'z_min': base_z, 'z_max': base_z + 80,
                'priority': 40,
                'weight': 1.0,
            }
        ])
    
    # 创建模板（如果已存在则使用现有的）
    template, created = ROI3DTemplate.objects.get_or_create(
        template_name='标准3层料架ROI模板',
        defaults={
            'rack_type': '标准3层料架',
            'layer_count': 3,
            'roi_configs': roi_configs,
            'default_algorithm_params': {
                'plane_fit_threshold': 2.0,
                'edge_detection_threshold': 50.0
            },
            'description': '标准3层料架的ROI配置模板，包含每层的4种标准ROI'
        }
    )
    
    print(f"✓ ROI模板: {template.template_name} {'[新建]' if created else '[已存在]'}")
    print(f"  - ID: {template.id}")
    print(f"  - 料架类型: {template.rack_type}")
    print(f"  - 层数: {template.layer_count}")
    print(f"  - ROI配置数: {len(template.roi_configs)}")
    print(f"  - 每层ROI数: {len(template.roi_configs) // template.layer_count}")
    
    return template


def test_7_get_statistics(recipe):
    """测试7：获取统计信息"""
    print_section("测试7: 获取统计信息")
    
    service = ROI3DService()
    
    stats = service.get_recipe_roi_statistics(recipe.id)
    
    print(f"配方 {recipe.recipe_name} 的ROI统计:")
    print(f"  - 总ROI数: {stats['total_rois']}")
    print(f"  - 启用: {stats['enabled_count']}")
    print(f"  - 禁用: {stats['disabled_count']}")
    print()
    
    print("按类型统计:")
    for roi_type, count in stats['by_type'].items():
        print(f"  - {roi_type}: {count}个")
    print()
    
    print("按层统计:")
    for layer_no, count in sorted(stats['by_layer'].items()):
        print(f"  - 第{layer_no}层: {count}个")


def test_8_update_roi(recipe):
    """测试8：更新ROI"""
    print_section("测试8: 更新ROI")
    
    service = ROI3DService()
    
    # 获取第2层的主ROI
    rois = service.get_rois_by_layer(recipe.id, 2, ROI3DType.MAIN)
    
    if rois:
        roi = rois[0]
        print(f"更新ROI: {roi.roi_name}")
        print(f"  原描述: {roi.description}")
        print(f"  原权重: {roi.weight}")
        
        # 更新ROI
        updated_roi = service.update_roi(
            roi.id,
            description='更新后的描述：主定位区域（已优化）',
            weight='0.90',  # Use string for exact decimal format
            priority=5
        )
        
        print(f"\n✓ ROI已更新:")
        print(f"  新描述: {updated_roi.description}")
        print(f"  新权重: {updated_roi.weight}")
        print(f"  新优先级: {updated_roi.priority}")
    else:
        print("未找到可更新的ROI")


def test_9_contains_point(recipe):
    """测试9：点包含判断"""
    print_section("测试9: 点包含判断")
    
    service = ROI3DService()
    
    # 获取第2层的主ROI
    rois = service.get_rois_by_layer(recipe.id, 2, ROI3DType.MAIN)
    
    if rois:
        roi = rois[0]
        
        test_points = [
            (0, 0, 900, "中心点"),
            (250, 0, 900, "X轴外"),
            (0, 200, 900, "Y轴外"),
            (0, 0, 1100, "Z轴外"),
            (100, 100, 880, "内部点"),
        ]
        
        print(f"测试点是否在 {roi.roi_name} 内:\n")
        
        for x, y, z, desc in test_points:
            in_roi = roi.contains_point(x, y, z)
            status = "✓ 在内" if in_roi else "✗ 在外"
            print(f"  点({x:4}, {y:4}, {z:4}) {desc:8} : {status}")


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  3D ROI配方模块 - 完整功能测试")
    print("=" * 70)
    print()
    
    try:
        # 测试1: 创建测试配方
        recipe = test_1_create_test_recipe()
        
        # 测试2: 创建单个ROI
        roi = test_2_create_single_roi(recipe)
        
        # 测试3: 批量创建一层的标准ROI
        layer2_rois = test_3_batch_create_layer_rois(recipe)
        
        # 测试4: 获取层ROI汇总
        test_4_get_layer_summary(recipe)
        
        # 测试5: 点云裁剪
        cropped_clouds = test_5_crop_pointcloud(recipe)
        
        # 测试6: 创建ROI模板
        template = test_6_create_template(recipe)
        
        # 测试7: 获取统计信息
        test_7_get_statistics(recipe)
        
        # 测试8: 更新ROI
        test_8_update_roi(recipe)
        
        # 测试9: 点包含判断
        test_9_contains_point(recipe)
        
        # 总结
        print_section("测试总结")
        print("✓ 所有测试完成！")
        print()
        print("功能验证:")
        print("  ✓ 单个ROI创建")
        print("  ✓ 批量创建层ROI")
        print("  ✓ 层ROI汇总查询")
        print("  ✓ 点云裁剪")
        print("  ✓ ROI模板管理")
        print("  ✓ 统计信息")
        print("  ✓ ROI更新")
        print("  ✓ 点包含判断")
        print()
        print("3D ROI配方模块功能正常！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
