"""测试 RVC 相机连接状态的诊断脚本

使用方法：
    python test_rvc_connection.py
"""
import sys
import os
import django

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置 Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

import requests
from django.conf import settings


def test_rvc_service_connection():
    """测试 RVC 相机服务是否可达"""
    print("=" * 60)
    print("🔍 测试 RVC 相机服务连接")
    print("=" * 60)
    
    cfg = settings.AUTOMATIC_ORDER.get('RVC_CAMERA', {})
    service_url = cfg.get('SERVICE_URL', 'http://127.0.0.1:8001')
    
    print(f"\n1. 配置的服务地址: {service_url}")
    print(f"   自动启动: {cfg.get('AUTO_START', False)}")
    print(f"   相机 IP: {cfg.get('CAMERA_IP', '169.254.10.202')}")
    
    # 测试 /status 端点
    print(f"\n2. 测试服务状态端点: {service_url}/status")
    try:
        response = requests.get(f"{service_url}/status", timeout=3)
        print(f"   ✅ 服务响应成功 (HTTP {response.status_code})")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n   返回数据:")
            print(f"   - connected: {data.get('connected', False)}")
            print(f"   - streaming: {data.get('streaming', False)}")
            print(f"   - sdk_version: {data.get('sdk_version', 'N/A')}")
            print(f"   - capture_count: {data.get('capture_count', 0)}")
            
            if data.get('device'):
                dev = data['device']
                print(f"   - device.sn: {dev.get('sn', 'N/A')}")
                print(f"   - device.ip: {dev.get('ip', 'N/A')}")
                print(f"   - device.name: {dev.get('name', 'N/A')}")
            
            if data.get('last_error'):
                print(f"   ⚠️  最近的错误: {data['last_error']}")
                
            return data
        else:
            print(f"   ❌ 服务返回非 200 状态码")
            print(f"   响应内容: {response.text[:200]}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ 无法连接到 RVC 服务")
        print(f"   错误: {e}")
        print(f"\n   💡 解决方案:")
        print(f"      1. 打开新的 PowerShell 窗口")
        print(f"      2. 激活虚拟环境: .venv\\Scripts\\Activate.ps1")
        print(f"      3. 运行: python -m rvc_service")
        return None
        
    except requests.exceptions.Timeout as e:
        print(f"   ❌ 连接超时")
        print(f"   错误: {e}")
        return None
        
    except Exception as e:
        print(f"   ❌ 发生错误: {type(e).__name__}: {e}")
        return None


def test_rvc_camera_service():
    """测试 Django 集成的 RvcCameraService"""
    print("\n" + "=" * 60)
    print("🔍 测试 Django RvcCameraService")
    print("=" * 60)
    
    try:
        from apps.rvc_camera.services import RvcCameraService
        
        service = RvcCameraService()
        print(f"\n✅ RvcCameraService 实例化成功")
        
        status = service.get_status()
        print(f"\n服务状态:")
        print(f"  - connected: {status.get('connected', False)}")
        print(f"  - streaming: {status.get('streaming', False)}")
        
        if status.get('device'):
            dev = status['device']
            print(f"  - device.sn: {dev.get('sn', 'N/A')}")
            print(f"  - device.ip: {dev.get('ip', 'N/A')}")
        
        return True
        
    except ImportError as e:
        print(f"❌ 无法导入 RvcCameraService: {e}")
        return False
        
    except Exception as e:
        print(f"❌ 调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_frame_provider():
    """测试 frame_provider 配置"""
    print("\n" + "=" * 60)
    print("🔍 测试 Frame Provider")
    print("=" * 60)
    
    try:
        from apps.vision.rack_location import Rack3DLocator
        
        locator = Rack3DLocator()
        provider_type = type(locator.frame_provider).__name__
        
        print(f"\n当前使用的 frame_provider: {provider_type}")
        
        if 'RVC' in provider_type:
            print(f"✅ 使用 RVC 相机提供器")
        elif 'DM' in provider_type:
            print(f"✅ 使用 DM 相机提供器")
        elif 'Sample' in provider_type:
            print(f"⚠️  使用模拟数据提供器（测试模式）")
        else:
            print(f"❓ 未知的提供器类型")
            
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n🚀 RVC 相机连接诊断工具\n")
    
    # 测试 1: RVC 服务连接
    status_data = test_rvc_service_connection()
    
    # 测试 2: Django 服务集成
    test_rvc_camera_service()
    
    # 测试 3: Frame Provider
    test_frame_provider()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 诊断总结")
    print("=" * 60)
    
    if status_data and status_data.get('connected'):
        print("\n✅ RVC 相机服务运行正常，相机已连接")
        print("   可以正常使用「采集点云」功能")
    elif status_data and not status_data.get('connected'):
        print("\n⚠️  RVC 服务运行正常，但相机未连接")
        print("\n   可能的原因:")
        print("   1. 相机未上电")
        print("   2. 网线未连接")
        print("   3. 网卡 IP 配置不正确（应为 169.254.x.x）")
        print("   4. RVCManager 软件占用相机")
        print("\n   解决步骤:")
        print("   1. 检查相机电源和网线")
        print("   2. ping 169.254.10.202")
        print("   3. 关闭 RVCManager（如果正在运行）")
        print("   4. 在服务窗口运行: curl http://127.0.0.1:8001/connect")
    else:
        print("\n❌ RVC 相机服务未运行")
        print("\n   启动方法:")
        print("   1. 打开新的 PowerShell 窗口")
        print("   2. cd d:\\workspace2\\AutomaticOrder")
        print("   3. .venv\\Scripts\\Activate.ps1")
        print("   4. python -m rvc_service")
        print("\n   或者直接双击运行: run_rvc_camera.py")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
