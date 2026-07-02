"""
测试ROI裁剪修复 - 验证详细日志输出
"""
import os
import sys
import django
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.rack_location import PointCloudProcessor


def test_crop_with_logging():
    """测试ROI裁剪并查看日志"""
    print("=" * 70)
    print("测试ROI裁剪 - 查看详细日志")
    print("=" * 70)
    
    # 生成测试点云（机器人坐标系，单位mm）
    # 假设点云在料架位置附近：X~900, Y~530, Z~920
    np.random.seed(42)
    n_points = 10000
    
    # 生成一个接近标准位置的点云
    pointcloud = np.array([
        np.random.normal(900, 50, n_points),   # X: 900±50
        np.random.normal(530, 30, n_points),   # Y: 530±30
        np.random.normal(920, 20, n_points),   # Z: 920±20
    ]).T.astype(np.float32)
    
    print(f"\n生成测试点云: {pointcloud.shape[0]}点")
    print(f"  X范围: [{pointcloud[:, 0].min():.2f}, {pointcloud[:, 0].max():.2f}], 均值: {pointcloud[:, 0].mean():.2f}")
    print(f"  Y范围: [{pointcloud[:, 1].min():.2f}, {pointcloud[:, 1].max():.2f}], 均值: {pointcloud[:, 1].mean():.2f}")
    print(f"  Z范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}], 均值: {pointcloud[:, 2].mean():.2f}")
    
    processor = PointCloudProcessor()
    
    # 测试1: 合理的ROI
    print("\n" + "=" * 70)
    print("测试1: 使用合理的ROI范围")
    print("=" * 70)
    
    good_roi = {
        'x_min': 800,
        'x_max': 1000,
        'y_min': 450,
        'y_max': 600,
        'z_min': 850,
        'z_max': 1000,
    }
    
    try:
        cropped = processor.crop_by_roi_3d(pointcloud, good_roi)
        print(f"\n✓ 裁剪成功，点数: {cropped.shape[0]}")
        
        if cropped.shape[0] > 0:
            median_x, median_y, median_z = processor.calculate_median_xyz(cropped)
            print(f"✓ 中位数位置: X={median_x:.2f}, Y={median_y:.2f}, Z={median_z:.2f}")
        
    except Exception as e:
        print(f"✗ 裁剪失败: {e}")
    
    # 测试2: 过小的ROI（会导致点云为空）
    print("\n" + "=" * 70)
    print("测试2: 使用过小的ROI范围（模拟问题场景）")
    print("=" * 70)
    
    bad_roi = {
        'x_min': -100,
        'x_max': 100,
        'y_min': -100,
        'y_max': 100,
        'z_min': -100,
        'z_max': 100,
    }
    
    try:
        cropped = processor.crop_by_roi_3d(pointcloud, bad_roi)
        print(f"\n裁剪结果点数: {cropped.shape[0]}")
        
        if cropped.shape[0] == 0:
            print("✓ 成功检测到空点云问题")
            print("  日志中应该显示详细的错误信息")
        else:
            median_x, median_y, median_z = processor.calculate_median_xyz(cropped)
            print(f"中位数位置: X={median_x:.2f}, Y={median_y:.2f}, Z={median_z:.2f}")
        
    except Exception as e:
        print(f"✓ 成功捕获异常: {e}")
    
    # 测试3: 错误的坐标范围（点云在0附近）
    print("\n" + "=" * 70)
    print("测试3: 点云坐标接近0（错误的坐标系）")
    print("=" * 70)
    
    bad_pointcloud = np.random.normal(0, 10, (10000, 3)).astype(np.float32)
    
    print(f"\n生成错误坐标的点云: {bad_pointcloud.shape[0]}点")
    print(f"  X范围: [{bad_pointcloud[:, 0].min():.2f}, {bad_pointcloud[:, 0].max():.2f}]")
    print(f"  Y范围: [{bad_pointcloud[:, 1].min():.2f}, {bad_pointcloud[:, 1].max():.2f}]")
    print(f"  Z范围: [{bad_pointcloud[:, 2].min():.2f}, {bad_pointcloud[:, 2].max():.2f}]")
    
    try:
        cropped = processor.crop_by_roi_3d(bad_pointcloud, good_roi)
        print(f"\n裁剪结果点数: {cropped.shape[0]}")
        
        if cropped.shape[0] == 0:
            print("✓ 成功检测到坐标系不匹配问题")
            print("  日志中应该显示ROI与点云坐标不匹配的错误")
        
    except Exception as e:
        print(f"✓ 成功捕获异常: {e}")
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)
    print("\n修复说明:")
    print("1. 添加了详细的日志输出，显示:")
    print("   - 输入点云的坐标范围")
    print("   - ROI的裁剪范围")
    print("   - 裁剪后的点数")
    print("   - 如果点云为空，显示可能的原因和建议")
    print()
    print("2. 改进了错误处理:")
    print("   - 点云为空时不再返回0值")
    print("   - 明确标记为失败，并返回错误信息")
    print("   - 避免误导性的大偏差值")
    print()
    print("3. 下次出现大偏差时:")
    print("   - 查看Django日志中的详细信息")
    print("   - 检查点云坐标范围是否合理")
    print("   - 调整3D ROI范围以匹配实际点云")
    print()


if __name__ == '__main__':
    test_crop_with_logging()
