"""测试采集点云功能"""
import requests
import json

print("=" * 60)
print("🧪 测试采集点云功能")
print("=" * 60)

# 1. 检查服务状态
print("\n1️⃣ 检查 RVC 服务状态...")
try:
    response = requests.get("http://127.0.0.1:8001/status", timeout=3)
    status = response.json()
    print(f"   连接状态: {status['data']['connected']}")
    print(f"   曝光参数: 2D={status['data']['exposure_2d']}, 3D={status['data']['exposure_3d']}")
    print(f"   最近错误: {status['data'].get('last_error', '无')}")
except Exception as e:
    print(f"   ❌ 服务不可达: {e}")
    exit(1)

# 2. 模拟前端采集请求
print("\n2️⃣ 模拟前端采集点云请求...")
try:
    # 这是前端发送的实际请求
    response = requests.post(
        "http://127.0.0.1:8082/vision/api/vision/3d/capture/",
        headers={
            "Content-Type": "application/json",
            # 注意：实际请求需要 CSRF token，这里先测试 API 逻辑
        },
        json={
            "recipe_id": None,
            "rack_side": "LEFT",
            "layer_no": 1
        },
        timeout=30
    )
    
    print(f"   HTTP 状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print(f"   ✅ 采集成功！")
            print(f"   Token: {data.get('pointcloud_token', 'N/A')}")
            print(f"   预览图: {data.get('pointcloud_preview_url', 'N/A')}")
            print(f"   数据源: {data.get('source', 'N/A')}")
        else:
            print(f"   ❌ 采集失败: {data.get('error', '未知错误')}")
    else:
        print(f"   ❌ 服务器错误")
        print(f"   响应: {response.text[:500]}")
        
except requests.exceptions.Timeout:
    print(f"   ⏱️  请求超时（采集时间较长是正常的）")
except Exception as e:
    print(f"   ❌ 请求失败: {e}")

print("\n" + "=" * 60)
