"""
扫描并查找相机的实际 IP 地址
"""
import sys
import os

# 设置环境
sdk_lib_dir = 'C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64'
os.environ['HCMVS_LIB'] = sdk_lib_dir
path_parts = os.environ.get('PATH', '').split(os.pathsep)
if sdk_lib_dir not in path_parts:
    os.environ['PATH'] = os.pathsep.join([sdk_lib_dir, *path_parts])

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(sdk_lib_dir)

print("=" * 70)
print("🔍 扫描并查找相机")
print("=" * 70)
print()

try:
    import chg_hik
    print("✅ chg_hik 模块导入成功")
    print()
except ImportError as e:
    print(f"❌ 无法导入 chg_hik: {e}")
    sys.exit(1)

# 尝试枚举设备
print("⏳ 正在扫描网络上的相机...")
print()

try:
    # 创建相机对象（不指定 IP，使用自动检测）
    camera = chg_hik.Camera(
        output_dir='media/hik_captures',
        format='BMP',
        quality=5,
    )
    
    # 尝试打开第一台相机
    print("⏳ 尝试打开第一台检测到的相机...")
    camera.open()  # 不指定 IP，自动检测
    print("✅ 相机打开成功！")
    print()
    
    # 尝试获取相机信息
    print("📋 相机信息:")
    print("-" * 70)
    
    # 尝试拍照来确认相机工作
    print("⏳ 测试拍照...")
    image_path = camera.capture()
    print(f"✅ 拍照成功！")
    print(f"   图像路径: {image_path}")
    print()
    
    print("=" * 70)
    print("✅ 找到可用的相机！")
    print("=" * 70)
    print()
    print("💡 建议:")
    print("   1. 打开 MVS 客户端")
    print("   2. 扫描设备列表，查看相机的 IP 地址")
    print("   3. 使用实际的 IP 地址更新 settings.py")
    print()
    print("   或者:")
    print("   将 settings.py 中的 CAMERA_IP 和 PC_IP 都设置为 None")
    print("   让系统自动检测相机（推荐）")
    
    # 关闭相机
    camera.close_camera()
    
except Exception as e:
    print(f"❌ 扫描失败: {e}")
    print(f"   错误类型: {type(e).__name__}")
    print()
    
    error_str = str(e)
    if '-2147483115' in error_str:
        print("💡 错误码 -2147483115 (设备被占用)")
        print("   → MVS 客户端可能正在使用相机")
        print("   → 请关闭 MVS 后重试")
    elif 'no device' in error_str.lower() or 'not found' in error_str.lower():
        print("💡 未找到相机")
        print("   可能原因:")
        print("   1. 相机未通电")
        print("   2. 网络连接断开")
        print("   3. SDK 驱动问题")
        print()
        print("   解决方案:")
        print("   1. 检查相机电源")
        print("   2. 打开 MVS 客户端，查看能否发现相机")
        print("   3. 如果 MVS 能发现，请提供相机的 IP 地址")

print()
print("=" * 70)
