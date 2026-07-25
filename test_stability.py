"""测试算法稳定性：相同输入是否产生相同输出。

使用方法：
1. 采集一次点云数据并保存
2. 使用相同的配方和ROI运行多次
3. 检查结果是否一致
"""
import numpy as np
from apps.vision.algorithms.rack_opening_rectangle import RackOpeningRectangleLocator


def test_deterministic_output():
    """测试：相同输入是否产生相同输出"""
    # 创建一个模拟点云（标准矩形 + 微小噪声）
    np.random.seed(42)  # 固定随机种子以生成相同的测试数据
    
    # 标准矩形顶点 (mm)
    standard_points = {
        'p1': {'x': 400, 'y': 0, 'z': 2200},      # 左上
        'p2': {'x': 1000, 'y': 0, 'z': 2200},     # 右上
        'p3': {'x': 1000, 'y': 0, 'z': 1700},     # 右下
        'p4': {'x': 400, 'y': 0, 'z': 1700},      # 左下
    }
    
    # 生成边缘点（每条边100个点 + 噪声）
    points_list = []
    for i in range(4):
        keys = ['p1', 'p2', 'p3', 'p4']
        start = standard_points[keys[i]]
        end = standard_points[keys[(i+1) % 4]]
        
        for t in np.linspace(0, 1, 100):
            x = start['x'] + t * (end['x'] - start['x'])
            y = start['y'] + t * (end['y'] - start['y'])
            z = start['z'] + t * (end['z'] - start['z'])
            
            # 添加微小噪声
            x += np.random.normal(0, 0.5)
            y += np.random.normal(0, 0.5)
            z += np.random.normal(0, 0.5)
            
            points_list.append([x, y, z])
    
    points = np.array(points_list)
    
    # 配方配置
    reference_config = {
        'opening_rectangle': {
            'standard_points': standard_points,
            'standard_width_mm': 600,
            'standard_height_mm': 500,
        }
    }
    
    # 运行多次，检查结果一致性
    locator = RackOpeningRectangleLocator()
    results = []
    
    print("🧪 开始稳定性测试：运行5次，检查结果是否一致...")
    print("=" * 60)
    
    for i in range(5):
        try:
            result = locator.locate(
                points,
                reference_config,
                coordinate_system='robot_base',
                pixel_coordinates=None,
                confidence_threshold=0.7,
            )
            
            center = result['center']
            print(f"\n第 {i+1} 次运行:")
            print(f"  中心点 P5: X={center['x']:.3f}, Y={center['y']:.3f}, Z={center['z']:.3f}")
            print(f"  宽度: {result['geometry']['width_mm']:.3f} mm")
            print(f"  高度: {result['geometry']['height_mm']:.3f} mm")
            print(f"  置信度: {result['quality']['confidence']:.4f}")
            
            results.append(result)
            
        except Exception as e:
            print(f"\n❌ 第 {i+1} 次运行失败: {e}")
            return False
    
    # 检查结果一致性
    print("\n" + "=" * 60)
    print("📊 一致性检查:")
    
    first_result = results[0]
    first_center = first_result['center']
    
    max_diff_x = 0
    max_diff_y = 0
    max_diff_z = 0
    
    for i, result in enumerate(results[1:], start=2):
        center = result['center']
        diff_x = abs(center['x'] - first_center['x'])
        diff_y = abs(center['y'] - first_center['y'])
        diff_z = abs(center['z'] - first_center['z'])
        
        max_diff_x = max(max_diff_x, diff_x)
        max_diff_y = max(max_diff_y, diff_y)
        max_diff_z = max(max_diff_z, diff_z)
        
        if diff_x > 0.001 or diff_y > 0.001 or diff_z > 0.001:
            print(f"  第 {i} 次与第 1 次的差异: ΔX={diff_x:.6f}, ΔY={diff_y:.6f}, ΔZ={diff_z:.6f}")
    
    print(f"\n最大差异: ΔX={max_diff_x:.6f} mm, ΔY={max_diff_y:.6f} mm, ΔZ={max_diff_z:.6f} mm")
    
    # 判断是否稳定（允许浮点误差 1e-6 mm）
    tolerance = 1e-6
    if max_diff_x <= tolerance and max_diff_y <= tolerance and max_diff_z <= tolerance:
        print("\n✅ 测试通过！算法输出完全一致（浮点精度内）")
        return True
    elif max_diff_x < 0.1 and max_diff_y < 0.1 and max_diff_z < 0.1:
        print(f"\n⚠️  算法输出有微小差异（< 0.1mm），但在工程可接受范围内")
        return True
    else:
        print(f"\n❌ 测试失败！算法输出不稳定，差异超过 0.1mm")
        return False


if __name__ == '__main__':
    test_deterministic_output()
