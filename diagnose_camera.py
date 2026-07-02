"""
相机采集问题诊断脚本

运行此脚本可以快速诊断相机采集失败的原因
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.conf import settings
from apps.dm_camera.models import DMCameraConfig, DMCameraSession
from apps.dm_camera.services import DMCameraService


def diagnose():
    """诊断相机采集问题"""
    
    print("=" * 60)
    print("🔍 相机采集问题诊断")
    print("=" * 60)
    print()
    
    # ========== 1. 检查配置项 ==========
    print("【1】检查配置项")
    print("-" * 60)
    
    force_sample = getattr(settings, 'VISION_RACK_LOCATION_FORCE_SAMPLE', False)
    if force_sample:
        print("❌ VISION_RACK_LOCATION_FORCE_SAMPLE = True")
        print("   → 系统被强制设置为模拟模式")
        print("   → 解决方案：在 settings.py 中设置为 False 或删除此配置项")
        return
    else:
        print("✅ VISION_RACK_LOCATION_FORCE_SAMPLE = False（或未设置）")
    
    print()
    
    # ========== 2. 检查相机配置 ==========
    print("【2】检查相机配置")
    print("-" * 60)
    
    all_configs = DMCameraConfig.objects.all()
    active_configs = DMCameraConfig.objects.filter(is_active=True)
    
    print(f"   数据库中相机配置总数: {all_configs.count()}")
    print(f"   激活的相机配置数: {active_configs.count()}")
    
    if active_configs.count() == 0:
        print("❌ 没有激活的相机配置")
        print("   → 解决方案：")
        print("      1. 访问 http://127.0.0.1:8000/dm-camera/config/")
        print("      2. 创建或激活一个相机配置")
        if all_configs.count() > 0:
            print(f"      3. 现有配置：")
            for config in all_configs:
                print(f"         - {config.name} (SN: {config.device_sn}, 激活: {config.is_active})")
        return
    else:
        active_config = active_configs.first()
        print(f"✅ 找到激活的相机配置:")
        print(f"   - 配置名称: {active_config.name}")
        print(f"   - 设备SN: {active_config.device_sn or '未指定（将自动选择第一台）'}")
        print(f"   - TOF配置文件: {active_config.tofconfig_path or '无'}")
        print(f"   - 创建时间: {active_config.created_at}")
    
    print()
    
    # ========== 3. 检查相机会话 ==========
    print("【3】检查相机会话")
    print("-" * 60)
    
    sessions = DMCameraSession.objects.filter(is_active=True)
    if sessions.exists():
        session = sessions.first()
        print(f"⚠️  存在活动会话:")
        print(f"   - 设备SN: {session.device_sn}")
        print(f"   - 启动时间: {session.connected_at}")
        print(f"   - 状态: 已连接")
        print()
        print("   这可能是正常的（如果相机正在使用中）")
        print("   如果相机实际未连接，这可能是上次未正确断开导致的")
    else:
        print("✅ 没有活动会话")
    
    print()
    
    # ========== 4. 尝试查找设备 ==========
    print("【4】尝试查找物理设备")
    print("-" * 60)
    
    try:
        service = DMCameraService()
        devices = service.find_devices()
        
        if len(devices) == 0:
            print("❌ 未找到任何DM相机设备")
            print("   → 可能原因：")
            print("      1. 相机未上电")
            print("      2. 网络连接断开（网络相机）")
            print("      3. USB连接松动（USB相机）")
            print("      4. SDK驱动未正确安装")
            print()
            print("   → 解决方案：")
            print("      1. 检查相机电源和连接")
            print("      2. 检查网络配置（相机IP和本机IP在同一网段）")
            print("      3. 重新安装相机SDK驱动")
        else:
            print(f"✅ 找到 {len(devices)} 台设备:")
            for i, device in enumerate(devices, 1):
                print(f"   设备 {i}:")
                print(f"      - SN: {device['sn']}")
                print(f"      - 类型: {device['type']}")
                print(f"      - IP: {device['ip']}")
                print(f"      - 本地IP: {device['local_ip']}")
    except Exception as e:
        print(f"❌ 查找设备时出错: {e}")
        print("   → 可能原因：")
        print("      1. SDK库文件缺失（tofdevice.dll 等）")
        print("      2. SDK版本不兼容")
        print("      3. 驱动未正确安装")
        print()
        print(f"   → 错误详情: {type(e).__name__}")
        return
    
    print()
    
    # ========== 5. 尝试连接相机 ==========
    print("【5】尝试连接相机")
    print("-" * 60)
    
    if len(devices) == 0:
        print("⏭️  跳过（未找到设备）")
        return
    
    try:
        service = DMCameraService()
        
        if service.is_connected:
            print("✅ 相机已连接")
            print(f"   - 流状态: {'正在采集' if service.is_streaming else '未启动'}")
        else:
            print("⏳ 尝试连接相机...")
            result = service.connect(
                device_sn=active_config.device_sn,
                config_id=active_config.id
            )
            print("✅ 连接成功！")
            print(f"   - 设备SN: {result.get('device_sn')}")
            print(f"   - 设备类型: {result.get('device_type')}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print(f"   → 错误类型: {type(e).__name__}")
        
        if 'already occupied' in str(e).lower():
            print()
            print("   → 原因: 相机被其他进程占用")
            print("   → 解决方案:")
            print("      1. 关闭所有使用相机的程序")
            print("      2. 重启Django服务器")
            print("      3. 如果问题持续，重启相机电源")
        elif 'not found' in str(e).lower():
            print()
            print("   → 原因: 相机未找到或配置的SN不存在")
            print("   → 解决方案:")
            print("      1. 检查配置的SN是否正确")
            print("      2. 尝试不指定SN（系统会自动选择第一台）")
        return
    
    print()
    
    # ========== 6. 尝试采集数据 ==========
    print("【6】尝试采集点云数据")
    print("-" * 60)
    
    try:
        service = DMCameraService()
        
        if not service.is_streaming:
            print("⏳ 启动数据流...")
            service.start_stream()
            print("✅ 数据流已启动")
        
        print("⏳ 采集一帧点云...")
        frame = service.capture_frame_data(frame_type='POINTCLOUD', save_record=False)
        
        print("✅ 采集成功！")
        print(f"   - 帧类型: {frame.get('frame_type')}")
        print(f"   - 图像尺寸: {frame.get('width')}x{frame.get('height')}")
        
        data = frame.get('data')
        if data is not None:
            import numpy as np
            arr = np.asarray(data)
            print(f"   - 数据形状: {arr.shape}")
            print(f"   - 数据类型: {arr.dtype}")
            
            if arr.size > 0:
                valid_points = arr[~np.isnan(arr).any(axis=-1)] if arr.ndim > 1 else arr[~np.isnan(arr)]
                print(f"   - 有效点数: {len(valid_points)}")
        
        print()
        print("=" * 60)
        print("🎉 诊断完成：相机工作正常！")
        print("=" * 60)
        print()
        print("如果在网页上仍然显示回退到模拟数据，请：")
        print("1. 清除浏览器缓存（Ctrl+F5）")
        print("2. 重启Django服务器")
        print("3. 检查控制台是否有其他错误信息")
        
    except Exception as e:
        print(f"❌ 采集失败: {e}")
        print(f"   → 错误类型: {type(e).__name__}")
        print()
        print("   → 可能原因：")
        print("      1. 相机数据流异常")
        print("      2. 相机参数配置错误")
        print("      3. 相机硬件故障")
        return
    
    print()


if __name__ == '__main__':
    try:
        diagnose()
    except KeyboardInterrupt:
        print("\n\n⏹️  诊断已中断")
    except Exception as e:
        print(f"\n\n❌ 诊断过程出错: {e}")
        import traceback
        traceback.print_exc()
