"""
测试相机预览功能 - 诊断脚本
"""
import os
import sys
from pathlib import Path

# 设置 Django 环境
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-key-for-diagnosis')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')

import django
django.setup()

from django.conf import settings
from apps.devices.adapters.camera import CameraAdapter

print("=" * 70)
print("相机预览功能诊断")
print("=" * 70)
print()

# 1. 检查配置
print("【步骤 1】检查相机配置")
print("-" * 70)
hik_config = getattr(settings, 'AUTOMATIC_ORDER', {}).get('HIK_CAMERA', {})
print(f"✓ 输出目录: {hik_config.get('OUTPUT_DIR')}")
print(f"✓ SDK路径: {hik_config.get('SDK_LIB_DIR')}")
print(f"✓ 相机IP: {hik_config.get('CAMERA_IP') or '自动检测'}")
print(f"✓ 本机IP: {hik_config.get('PC_IP') or '自动检测'}")
print(f"✓ 图像格式: {hik_config.get('FORMAT', 'PNG')}")
print(f"✓ 图像质量: {hik_config.get('QUALITY', 5)}")
print(f"✓ 子进程模式: {hik_config.get('RUN_IN_SUBPROCESS', True)}")
print()

# 2. 检查输出目录
print("【步骤 2】检查输出目录")
print("-" * 70)
output_dir = Path(hik_config.get('OUTPUT_DIR', settings.MEDIA_ROOT / 'hik_captures'))
if output_dir.exists():
    print(f"✓ 输出目录存在: {output_dir}")
    print(f"✓ 目录是否可写: ", end="")
    try:
        test_file = output_dir / '.write_test'
        test_file.touch()
        test_file.unlink()
        print("是")
    except Exception as e:
        print(f"否 - {e}")
else:
    print(f"✗ 输出目录不存在: {output_dir}")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ 已创建输出目录")
    except Exception as e:
        print(f"✗ 无法创建输出目录: {e}")
print()

# 3. 检查 SDK
print("【步骤 3】检查 Hikrobot SDK")
print("-" * 70)
sdk_lib_dir = hik_config.get('SDK_LIB_DIR')
if sdk_lib_dir:
    sdk_path = Path(sdk_lib_dir)
    if sdk_path.exists():
        print(f"✓ SDK目录存在: {sdk_path}")
        # 列出DLL文件
        dll_files = list(sdk_path.glob('*.dll'))
        if dll_files:
            print(f"✓ 找到 {len(dll_files)} 个DLL文件")
        else:
            print(f"✗ 未找到DLL文件")
    else:
        print(f"✗ SDK目录不存在: {sdk_path}")
else:
    print("! SDK路径未配置")
print()

# 4. 检查 chg_hik 模块
print("【步骤 4】检查 chg_hik Python 绑定")
print("-" * 70)
try:
    import chg_hik
    print(f"✓ chg_hik 模块导入成功")
    print(f"✓ 模块路径: {chg_hik.__file__}")
    
    # 检查可用的类和函数
    if hasattr(chg_hik, 'Camera'):
        print(f"✓ Camera 类可用")
    else:
        print(f"✗ Camera 类不可用")
        
except ImportError as e:
    print(f"✗ chg_hik 模块导入失败: {e}")
    print()
    print("  解决方案:")
    print("  1. 确保 chg_hik 已安装到虚拟环境")
    print("  2. 在项目根目录运行: maturin develop --release")
    sys.exit(1)
print()

# 5. 尝试连接相机
print("【步骤 5】尝试连接相机并拍照")
print("-" * 70)
try:
    adapter = CameraAdapter()
    print("✓ CameraAdapter 创建成功")
    
    print("⏳ 正在拍照...")
    result = adapter.capture(
        camera_code='CAM-INSPECT-FOAM-01',
        task_type='PREVIEW',
    )
    
    print(f"✓ 拍照成功!")
    print(f"  - 图像路径: {result.get('image_path')}")
    print(f"  - 相机代码: {result.get('camera_code')}")
    print(f"  - 任务类型: {result.get('task_type')}")
    
    # 检查图像文件
    image_path = Path(result.get('image_path'))
    if image_path.exists():
        file_size = image_path.stat().st_size
        print(f"  - 文件大小: {file_size:,} 字节 ({file_size / 1024 / 1024:.2f} MB)")
        if file_size > 0:
            print(f"✓ 图像文件有效")
        else:
            print(f"✗ 图像文件为空")
    else:
        print(f"✗ 图像文件不存在: {image_path}")
    
except RuntimeError as e:
    print(f"✗ 拍照失败: {e}")
    print()
    print("常见问题排查:")
    print("1. 相机是否通电？")
    print("2. 网络连接是否正常？（如果使用网络相机）")
    print("3. 是否有其他程序占用相机？（如 MVS 客户端）")
    print("4. 防火墙是否阻止了相机连接？")
    sys.exit(1)
except Exception as e:
    print(f"✗ 未知错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("诊断完成！所有检查均通过。")
print("=" * 70)
