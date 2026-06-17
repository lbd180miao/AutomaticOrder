#!/usr/bin/env python
"""海康威视相机诊断工具 - 检测常见问题并提供修复建议"""

import os
import sys
from pathlib import Path

# 添加项目路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')

import django
django.setup()

from django.conf import settings


def check_output_directory():
    """检查输出目录权限和空间"""
    print("\n=== 检查输出目录 ===")
    hik_settings = settings.AUTOMATIC_ORDER.get('HIK_CAMERA', {})
    output_dir = Path(hik_settings.get('OUTPUT_DIR', settings.MEDIA_ROOT / 'hik_captures'))
    
    print(f"输出目录: {output_dir}")
    
    # 检查目录是否存在
    if not output_dir.exists():
        print(f"  ✗ 目录不存在，尝试创建...")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ 成功创建目录")
        except Exception as e:
            print(f"  ✗ 创建失败: {e}")
            return False
    else:
        print(f"  ✓ 目录存在")
    
    # 检查写入权限
    test_file = output_dir / '.write_test'
    try:
        test_file.write_text('test')
        test_file.unlink()
        print(f"  ✓ 具有写入权限")
    except Exception as e:
        print(f"  ✗ 无写入权限: {e}")
        return False
    
    # 检查磁盘空间
    try:
        import shutil
        stat = shutil.disk_usage(output_dir)
        free_gb = stat.free / (1024**3)
        print(f"  ✓ 可用空间: {free_gb:.2f} GB")
        if free_gb < 1:
            print(f"  ⚠ 警告: 磁盘空间不足 1GB")
    except Exception as e:
        print(f"  ⚠ 无法检查磁盘空间: {e}")
    
    return True


def check_sdk_library():
    """检查SDK库文件"""
    print("\n=== 检查海康SDK ===")
    hik_settings = settings.AUTOMATIC_ORDER.get('HIK_CAMERA', {})
    sdk_lib_dir = hik_settings.get('SDK_LIB_DIR')
    
    if not sdk_lib_dir:
        print("  ✗ SDK_LIB_DIR 未配置")
        return False
    
    sdk_path = Path(sdk_lib_dir)
    print(f"SDK目录: {sdk_path}")
    
    if not sdk_path.exists():
        print(f"  ✗ SDK目录不存在")
        return False
    else:
        print(f"  ✓ SDK目录存在")
    
    # 检查关键DLL文件
    required_dlls = ['MvCameraControl.dll', 'MVGigEVisionSDK.dll']
    all_found = True
    for dll in required_dlls:
        dll_path = sdk_path / dll
        if dll_path.exists():
            print(f"  ✓ 找到 {dll}")
        else:
            print(f"  ✗ 缺失 {dll}")
            all_found = False
    
    return all_found


def check_camera_binding():
    """检查Python绑定模块"""
    print("\n=== 检查chg_hik模块 ===")
    try:
        import chg_hik
        print(f"  ✓ chg_hik 模块已安装")
        print(f"  模块路径: {chg_hik.__file__}")
        return True
    except ImportError as e:
        print(f"  ✗ 无法导入chg_hik: {e}")
        print("\n修复建议:")
        print("  1. 进入 Hik_camera 目录")
        print("  2. 激活虚拟环境: .venv\\Scripts\\activate")
        print("  3. 重新编译: maturin develop --release")
        return False


def check_network_config():
    """检查网络配置"""
    print("\n=== 检查网络配置 ===")
    hik_settings = settings.AUTOMATIC_ORDER.get('HIK_CAMERA', {})
    camera_ip = hik_settings.get('CAMERA_IP')
    pc_ip = hik_settings.get('PC_IP')
    
    print(f"相机IP: {camera_ip}")
    print(f"PC IP: {pc_ip}")
    
    if not camera_ip or not pc_ip:
        print("  ⚠ 网络参数未配置（将使用默认相机）")
        return True
    
    # 检查IP格式
    import ipaddress
    try:
        ipaddress.ip_address(camera_ip)
        print(f"  ✓ 相机IP格式正确")
    except ValueError:
        print(f"  ✗ 相机IP格式错误: {camera_ip}")
        return False
    
    try:
        ipaddress.ip_address(pc_ip)
        print(f"  ✓ PC IP格式正确")
    except ValueError:
        print(f"  ✗ PC IP格式错误: {pc_ip}")
        return False
    
    return True


def check_image_format():
    """检查图像格式配置"""
    print("\n=== 检查图像格式配置 ===")
    hik_settings = settings.AUTOMATIC_ORDER.get('HIK_CAMERA', {})
    image_format = hik_settings.get('FORMAT', 'PNG')
    quality = hik_settings.get('QUALITY', 5)
    
    print(f"格式: {image_format}")
    print(f"质量: {quality}")
    
    valid_formats = ['BMP', 'PNG', 'JPEG', 'JPG']
    if image_format.upper() not in valid_formats:
        print(f"  ✗ 不支持的格式: {image_format}")
        print(f"  支持的格式: {', '.join(valid_formats)}")
        return False
    else:
        print(f"  ✓ 格式有效")
    
    if not (0 <= quality <= 10):
        print(f"  ✗ 质量参数超出范围 (0-10): {quality}")
        return False
    else:
        print(f"  ✓ 质量参数有效")
    
    # BMP格式建议
    if image_format.upper() != 'BMP':
        print(f"  ⚠ 建议: 如果遇到保存错误，尝试使用 BMP 格式")
    
    return True


def main():
    print("=" * 60)
    print("海康威视相机诊断工具")
    print("=" * 60)
    
    checks = [
        ("输出目录", check_output_directory),
        ("SDK库", check_sdk_library),
        ("Python绑定", check_camera_binding),
        ("网络配置", check_network_config),
        ("图像格式", check_image_format),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n✗ 检查 {name} 时发生错误: {e}")
            results[name] = False
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断结果总结")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}: {name}")
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n✓ 所有检查通过！")
        print("\n如果仍然遇到错误码 -2147483646，请尝试:")
        print("  1. 重启相机设备")
        print("  2. 检查相机固件版本")
        print("  3. 确认相机网络连接正常")
        print("  4. 尝试使用官方 MVS 客户端测试相机")
    else:
        print("\n✗ 存在问题需要修复")
        print("\n常见错误码 -2147483646 (0x80000002) 解决方案:")
        print("  1. 确保输出目录存在且有写入权限")
        print("  2. 检查磁盘空间充足")
        print("  3. 尝试使用 BMP 格式而非 PNG")
        print("  4. 确认SDK库路径正确")
        print("  5. 重启Django服务器")


if __name__ == '__main__':
    main()
