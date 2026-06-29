"""测试相机修复后的点云采集"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.dm_camera.services import DMCameraService

service = DMCameraService()

try:
    print("1. 查找设备...")
    devices = service.find_devices()
    print(f"   找到 {len(devices)} 个设备")
    for dev in devices:
        print(f"   - SN: {dev['sn']}, IP: {dev['ip']}")
    
    if not devices:
        print("⚠ 未找到设备，请检查相机连接")
        exit(1)
    
    print("\n2. 连接设备...")
    result = service.connect()
    print(f"   ✓ 已连接: {result['device_sn']}")
    
    print("\n3. 开启数据流...")
    service.start_stream()
    print("   ✓ 数据流已开启")
    
    print("\n4. 采集点云...")
    capture_result = service.capture(frame_type='DEPTH', save_record=True)
    print(f"   ✓ 采集成功!")
    print(f"   - 分辨率: {capture_result['width']}x{capture_result['height']}")
    print(f"   - 帧序号: {capture_result['frame_index']}")
    if 'preview_url' in capture_result:
        print(f"   - 预览图: {capture_result['preview_url']}")
    
    print("\n5. 停止数据流...")
    service.stop_stream()
    
    print("\n6. 断开连接...")
    service.disconnect()
    
    print("\n✅ 测试成功！相机已正常工作")
    
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
    
    # 清理
    try:
        if service.is_streaming:
            service.stop_stream()
        if service.is_connected:
            service.disconnect()
    except:
        pass
