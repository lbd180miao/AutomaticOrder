"""
测试3D料架定位离线测试功能
"""
import os
import sys
import django
import numpy as np

# 设置Django环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()


def test_generate_sample_data():
    """生成测试用的点云数据"""
    print("\n" + "=" * 60)
    print("生成测试点云数据")
    print("=" * 60)
    
    # 生成模拟点云数据（640x480的深度图）
    width, height = 640, 480
    total_points = width * height
    
    # 创建规则网格
    x = np.linspace(-100, 100, width)
    y = np.linspace(-100, 100, height)
    xx, yy = np.meshgrid(x, y)
    
    # 生成模拟的深度值（一个倾斜的平面加上一些噪声）
    zz = 800 + 0.1 * xx + 0.2 * yy + np.random.randn(height, width) * 2
    
    # 组合成点云 (N, 3)
    pointcloud = np.stack([
        xx.flatten(),
        yy.flatten(),
        zz.flatten()
    ], axis=1).astype(np.float32)
    
    print(f"✓ 生成点云: {pointcloud.shape}")
    print(f"  X 范围: [{pointcloud[:, 0].min():.2f}, {pointcloud[:, 0].max():.2f}]")
    print(f"  Y 范围: [{pointcloud[:, 1].min():.2f}, {pointcloud[:, 1].max():.2f}]")
    print(f"  Z 范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}]")
    
    # 保存为.npy文件
    test_file = os.path.join(os.path.dirname(__file__), 'test_pointcloud.npy')
    np.save(test_file, pointcloud)
    print(f"✓ 已保存到: {test_file}")
    
    return pointcloud, test_file


def test_offline_api():
    """测试离线测试API"""
    print("\n" + "=" * 60)
    print("测试离线测试API")
    print("=" * 60)
    
    from django.test import Client
    import json
    
    # 生成测试数据
    pointcloud, _ = test_generate_sample_data()
    
    # 只取前1000个点进行测试（减少数据量）
    sample_pointcloud = pointcloud[:1000].tolist()
    
    client = Client()
    
    response = client.post(
        '/vision/api/rack/offline-test/',
        data=json.dumps({
            'pointcloud': sample_pointcloud,
            'image_width': 640,
            'image_height': 480
        }),
        content_type='application/json'
    )
    
    print(f"HTTP 状态: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 成功: {data.get('message')}")
        print(f"  深度文件: {data['files']['depth']}")
        print(f"  图片文件: {data['files']['image']}")
        print(f"  点云形状: {data['pointcloud_shape']}")
        
        # 检查文件是否确实创建了
        depth_file = data['files']['depth']
        image_file = data['files']['image']
        
        if os.path.exists(depth_file):
            file_size = os.path.getsize(depth_file) / 1024
            print(f"✓ 深度文件已创建: {file_size:.2f} KB")
        else:
            print(f"✗ 深度文件未找到")
        
        if os.path.exists(image_file):
            file_size = os.path.getsize(image_file) / 1024
            print(f"✓ 图片文件已创建: {file_size:.2f} KB")
        else:
            print(f"✗ 图片文件未找到")
    else:
        print(f"✗ 失败: {response.content.decode()}")


def test_import_npy_api():
    """测试.npy文件导入API"""
    print("\n" + "=" * 60)
    print("测试.npy文件导入API")
    print("=" * 60)
    
    from django.test import Client
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    # 生成测试数据
    pointcloud, test_file = test_generate_sample_data()
    
    client = Client()
    
    # 读取.npy文件
    with open(test_file, 'rb') as f:
        file_content = f.read()
    
    uploaded_file = SimpleUploadedFile(
        name='test_pointcloud.npy',
        content=file_content,
        content_type='application/octet-stream'
    )
    
    response = client.post(
        '/vision/api/rack/import-npy/',
        data={'file': uploaded_file},
        format='multipart'
    )
    
    print(f"HTTP 状态: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 成功解析.npy文件")
        print(f"  原始形状: {data['shape']}")
        print(f"  点数: {data['point_count']}")
        print(f"  返回点云前3个点:")
        for i, point in enumerate(data['pointcloud'][:3]):
            print(f"    [{i}] {point}")
    else:
        print(f"✗ 失败: {response.content.decode()}")


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  3D 料架定位离线测试功能 - 测试脚本")
    print("=" * 70)
    
    try:
        # 测试1: 生成测试数据
        test_generate_sample_data()
        
        # 测试2: 测试离线API
        test_offline_api()
        
        # 测试3: 测试.npy导入API
        test_import_npy_api()
        
        print("\n" + "=" * 70)
        print("  所有测试完成！")
        print("=" * 70)
        print("\n使用说明:")
        print("1. 打开浏览器访问: http://localhost:8000/vision/rack-locator/")
        print("2. 选择一个配方")
        print("3. 点击「📂 导入数据」按钮")
        print("4. 选择点云文件（支持.npy/.json/.txt格式）")
        print("5. 数据将自动保存到 C:\\Users\\11410\\Desktop\\pic")
        print("   - depth_YYYYMMDD_HHMMSS_mmm.npy (深度数据)")
        print("   - image_YYYYMMDD_HHMMSS_mmm.png (2D伪彩色图)")
        print()
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
