"""
诊断「计算偏差」功能问题
"""
import os
import sys
import django
import json

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.urls import reverse
from django.test import Client

print("=" * 60)
print("「计算偏差」功能诊断")
print("=" * 60)

# 1. 检查URL配置
print("\n1. 检查URL配置:")
try:
    calculate_url = reverse('vision:api_rack_location_workbench_calculate')
    print(f"   ✓ 计算偏差API URL: {calculate_url}")
except Exception as e:
    print(f"   ✗ 计算偏差API URL错误: {e}")

try:
    test_locate_url = reverse('vision:api_vision_3d_test_locate')
    print(f"   ✓ 通用定位API URL: {test_locate_url}")
except Exception as e:
    print(f"   ✗ 通用定位API URL错误: {e}")

# 2. 检查视图函数
print("\n2. 检查视图函数:")
try:
    from apps.vision import views
    
    if hasattr(views, 'api_rack_location_workbench_calculate'):
        print("   ✓ api_rack_location_workbench_calculate 视图存在")
    else:
        print("   ✗ api_rack_location_workbench_calculate 视图不存在")
        
    if hasattr(views, 'api_vision_3d_test_locate'):
        print("   ✓ api_vision_3d_test_locate 视图存在")
    else:
        print("   ✗ api_vision_3d_test_locate 视图不存在")
        
except Exception as e:
    print(f"   ✗ 导入视图模块失败: {e}")

# 3. 模拟完整流程测试
print("\n3. 模拟完整流程测试:")
print("   步骤1: 采集点云...")

client = Client()

try:
    # 步骤1: 采集点云
    capture_response = client.post(
        '/vision/api/rack-location/workbench/capture/',
        data=json.dumps({
            'recipe_id': None,
            'rack_side': 'LEFT',
            'locate_type': 'LAYER',
            'layer_index': 1,
        }),
        content_type='application/json'
    )
    
    print(f"   采集点云状态码: {capture_response.status_code}")
    
    if capture_response.status_code == 200:
        capture_data = json.loads(capture_response.content)
        print(f"   ✓ 采集成功: {capture_data.get('success')}")
        
        if capture_data.get('success'):
            token = capture_data.get('pointcloud_token')
            print(f"   ✓ 获得token: {token}")
            
            # 步骤2: 计算偏差
            print("\n   步骤2: 计算偏差...")
            
            # 模拟ROI参数
            test_payload = {
                'pointcloud_token': token,
                'roi_config': {
                    'target_roi': {
                        'x': 100,
                        'y': 100,
                        'w': 200,
                        'h': 150,
                        'feature_type': 'rack_reference'
                    }
                },
                'roi': {
                    'x_min': -100,
                    'x_max': 100,
                    'y_min': -100,
                    'y_max': 100,
                    'z_min': -100,
                    'z_max': 100,
                },
                'recipe_id': None,
                'rack_side': 'LEFT',
                'locate_type': 'LAYER',
                'layer_index': 1,
                'recipe_data': {
                    'standard_x': 0,
                    'standard_y': 0,
                    'standard_z': 0,
                    'max_offset_x': 20,
                    'max_offset_y': 20,
                    'max_offset_z': 20,
                    'confidence_threshold': 0.7,
                }
            }
            
            calculate_response = client.post(
                '/vision/api/rack-location/workbench/calculate/',
                data=json.dumps(test_payload),
                content_type='application/json'
            )
            
            print(f"   计算偏差状态码: {calculate_response.status_code}")
            print(f"   Content-Type: {calculate_response.get('Content-Type', 'N/A')}")
            
            if calculate_response.status_code == 200:
                try:
                    calc_data = json.loads(calculate_response.content)
                    print(f"   ✓ 计算成功: {calc_data.get('success')}")
                    
                    if calc_data.get('success'):
                        result = calc_data.get('result', {})
                        print(f"   ✓ 定位结果: OK={result.get('locate_ok')}")
                        print(f"   ✓ 偏差 X: {result.get('offset_x', result.get('final_offset_x'))}")
                        print(f"   ✓ 偏差 Y: {result.get('offset_y', result.get('final_offset_y'))}")
                        print(f"   ✓ 偏差 Z: {result.get('offset_z', result.get('final_offset_z'))}")
                        print(f"   ✓ 置信度: {result.get('confidence')}")
                    else:
                        print(f"   ✗ 计算失败: {calc_data.get('error')}")
                except json.JSONDecodeError:
                    print(f"   ✗ 响应不是JSON: {calculate_response.content[:200]}")
            else:
                print(f"   ✗ HTTP错误: {calculate_response.content[:500]}")
        else:
            print(f"   ✗ 采集失败: {capture_data.get('error')}")
    else:
        print(f"   ✗ 采集失败，状态码: {capture_response.status_code}")
        print(f"   响应: {capture_response.content[:200]}")
        
except Exception as e:
    print(f"   ✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()

# 4. 检查常见问题
print("\n" + "=" * 60)
print("常见问题检查:")
print("=" * 60)

print("\n问题1: 是否先采集了点云？")
print("   → 必须先点击「采集点云」，获得 pointcloud_token")
print("   → 在浏览器Console中检查是否有token")

print("\n问题2: 是否绘制了ROI？")
print("   → 必须在画布上拖拽绘制ROI框")
print("   → 或者配方中包含预设的ROI")

print("\n问题3: 按钮是否被禁用？")
print("   → 在Console中执行: document.getElementById('btn-calculate').disabled")
print("   → 应该返回 false")

print("\n问题4: 浏览器Console是否有错误？")
print("   → 按F12打开开发者工具")
print("   → 切换到Console标签查看错误信息")

print("\n问题5: Network请求是否发送成功？")
print("   → 切换到Network标签")
print("   → 点击「计算偏差」按钮")
print("   → 查看是否有 workbench/calculate/ 请求")
print("   → 检查请求URL、状态码和响应")

print("\n" + "=" * 60)
print("调试步骤:")
print("=" * 60)
print("1. 打开工作台页面: http://localhost:8000/vision/rack-locator/")
print("2. 按F12打开开发者工具")
print("3. 在Console中执行以下命令查看状态:")
print("   - 检查token: console.log(window.state || 'state未定义')")
print("   - 检查ROI: console.log(window.state?.roi || 'ROI未定义')")
print("   - 检查按钮: document.getElementById('btn-calculate').disabled")
print("4. 完整流程:")
print("   a) 选择配方")
print("   b) 点击「采集点云」")
print("   c) 等待点云图像显示")
print("   d) 在画布上拖拽绘制ROI（或自动加载）")
print("   e) 点击「计算偏差」")
print("5. 查看Console和Network的详细信息")
print("=" * 60)
