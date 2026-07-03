"""
直接测试 chg_hik 相机连接（不通过 Django adapter）
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
print("🔍 直接测试 chg_hik 相机连接")
print("=" * 70)
print()

try:
    import chg_hik
    print("✅ chg_hik 模块导入成功")
    print(f"   路径: {chg_hik.__file__}")
    print()
except ImportError as e:
    print(f"❌ 无法导入 chg_hik: {e}")
    sys.exit(1)

# 测试 1: 尝试使用 camera_ip 和 pc_ip 打开
print("【测试 1】使用 IP 地址打开相机")
print("-" * 70)
print(f"   相机 IP: 169.254.160.253")
print(f"   本机 IP: 169.254.160.95")
print()

camera = None
try:
    camera = chg_hik.Camera(
        output_dir='media/hik_captures',
        format='BMP',
        quality=5,
    )
    print("✅ Camera 对象创建成功")
    
    print("⏳ 尝试打开相机...")
    camera.open(camera_ip='169.254.160.253', pc_ip='169.254.160.95')
    print("✅ 相机打开成功！")
    
    print("⏳ 尝试拍照...")
    image_path = camera.capture()
    print(f"✅ 拍照成功！图像路径: {image_path}")
    
    # 验证文件
    if Path(image_path).exists():
        size_mb = Path(image_path).stat().st_size / 1024 / 1024
        print(f"   文件大小: {size_mb:.2f} MB")
    
    print()
    print("🎉 测试 1 完全成功！")
    
except Exception as e:
    print(f"❌ 测试 1 失败: {e}")
    print(f"   错误类型: {type(e).__name__}")
    
    # 测试 2: 尝试不使用 IP 地址打开（自动检测第一台相机）
    print()
    print("【测试 2】自动检测并打开第一台相机")
    print("-" * 70)
    print()
    
    try:
        if camera is None:
            camera = chg_hik.Camera(
                output_dir='media/hik_captures',
                format='BMP',
                quality=5,
            )
            print("✅ Camera 对象创建成功")
        
        print("⏳ 尝试打开相机（不指定 IP）...")
        camera.open()
        print("✅ 相机打开成功！")
        
        print("⏳ 尝试拍照...")
        image_path = camera.capture()
        print(f"✅ 拍照成功！图像路径: {image_path}")
        
        # 验证文件
        if Path(image_path).exists():
            size_mb = Path(image_path).stat().st_size / 1024 / 1024
            print(f"   文件大小: {size_mb:.2f} MB")
        
        print()
        print("🎉 测试 2 完全成功！")
        
    except Exception as e2:
        print(f"❌ 测试 2 也失败: {e2}")
        print(f"   错误类型: {type(e2).__name__}")
        print()
        print("=" * 70)
        print("💡 诊断建议")
        print("=" * 70)
        print()
        
        error_str = str(e2)
        if '-2147483115' in error_str or '0x80070005' in error_str:
            print("错误码 -2147483115 (MV_E_ACCESS_DENIED) 表示设备被占用或权限不足")
            print()
            print("🔧 解决方案：")
            print()
            print("1. **关闭 MVS 客户端**")
            print("   - 即使你看到 MVS 可以打开相机，也必须关闭它")
            print("   - MVS 打开相机后会独占设备")
            print("   - 请完全退出 MVS 软件")
            print()
            print("2. **重启相机电源**")
            print("   - 相机可能处于锁定状态")
            print("   - 断电 10 秒")
            print("   - 重新上电")
            print("   - 等待 30-60 秒初始化完成")
            print()
            print("3. **检查是否有隐藏的 MVS 进程**")
            print("   - 打开任务管理器")
            print("   - 切换到「详细信息」标签页")
            print("   - 查找 MVSClient.exe 或类似进程")
            print("   - 如果找到，结束它")
            print()
            print("4. **尝试使用 MVS 测试**")
            print("   - 打开 MVS 客户端")
            print("   - 连接相机并拍照（确认硬件正常）")
            print("   - **完全关闭 MVS**")
            print("   - 等待 5-10 秒")
            print("   - 重新运行此测试脚本")
        else:
            print(f"未知错误: {e2}")
            print("请检查:")
            print("  - 相机是否通电")
            print("  - 网络连接是否正常")
            print("  - SDK 是否正确安装")

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
