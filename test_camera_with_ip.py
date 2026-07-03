"""
使用指定 IP 地址测试相机连接
"""
import sys
import os
from pathlib import Path

# 设置环境
sdk_lib_dir = 'C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64'
os.environ['HCMVS_LIB'] = sdk_lib_dir
path_parts = os.environ.get('PATH', '').split(os.pathsep)
if sdk_lib_dir not in path_parts:
    os.environ['PATH'] = os.pathsep.join([sdk_lib_dir, *path_parts])

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(sdk_lib_dir)

print("=" * 70)
print("🔍 测试相机连接 - 使用指定 IP")
print("=" * 70)
print()

# 测试参数
CAMERA_IP = '192.168.1.245'
PC_IP = '192.168.1.123'  # 以太网适配器的 IP

print(f"测试配置:")
print(f"  相机 IP: {CAMERA_IP}")
print(f"  本机 IP: {PC_IP if PC_IP else '自动检测'}")
print()

try:
    import chg_hik
    print("✅ chg_hik 模块导入成功")
    print()
except ImportError as e:
    print(f"❌ 无法导入 chg_hik: {e}")
    sys.exit(1)

camera = None
try:
    camera = chg_hik.Camera(
        output_dir='media/hik_captures',
        format='BMP',
        quality=5,
    )
    print("✅ Camera 对象创建成功")
    
    print(f"⏳ 尝试打开相机 {CAMERA_IP}...")
    camera.open(camera_ip=CAMERA_IP, pc_ip=PC_IP)
    
    print("✅ 相机打开成功！")
    
    print("⏳ 尝试拍照...")
    image_path = camera.capture()
    print(f"✅ 拍照成功！")
    print(f"   图像路径: {image_path}")
    
    # 验证文件
    if image_path and Path(image_path).exists():
        size_mb = Path(image_path).stat().st_size / 1024 / 1024
        print(f"   文件大小: {size_mb:.2f} MB")
    else:
        print(f"   ⚠️  文件不存在: {image_path}")
    
    print()
    print("🎉 测试完全成功！")
    print()
    print("下一步：更新 settings.py 配置为这个 IP 地址")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    print(f"   错误类型: {type(e).__name__}")
    
    error_str = str(e)
    print()
    print("=" * 70)
    print("💡 可能的原因")
    print("=" * 70)
    print()
    
    if '-2147483115' in error_str or '0x80070005' in error_str:
        print("❌ 错误码 -2147483115 (设备被占用)")
        print("   解决方案：")
        print("   1. 关闭 MVS 客户端")
        print("   2. 重启相机电源")
    elif '-2147483644' in error_str or 'not found' in error_str.lower():
        print("❌ 设备未找到")
        print("   可能原因：")
        print(f"   1. 相机 IP {CAMERA_IP} 配置错误")
        print("   2. 相机未通电")
        print("   3. 网络连接断开")
        print()
        print("   解决方案：")
        print(f"   1. 验证相机 IP: ping {CAMERA_IP}")
        print("   2. 检查相机网络配置（在 MVS 中查看）")
        print("   3. 确保本机和相机在同一网段")
    elif 'timeout' in error_str.lower():
        print("❌ 连接超时")
        print("   解决方案：")
        print("   1. 检查网络连接")
        print(f"   2. Ping 测试: ping {CAMERA_IP}")
        print("   3. 检查防火墙设置")
    else:
        print(f"❌ 未知错误: {e}")

finally:
    # 确保关闭相机
    if camera:
        try:
            print()
            print("⏳ 正在关闭相机...")
            if hasattr(camera, 'close_camera'):
                camera.close_camera()
                print("✅ 相机已关闭")
        except Exception as close_exc:
            print(f"⚠️  关闭相机时出错: {close_exc}")

print()
print("=" * 70)
