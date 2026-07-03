"""
智能相机问题修复工具
"""
import sys
import subprocess
import time
from pathlib import Path

print("=" * 70)
print("智能相机问题诊断与修复工具")
print("=" * 70)
print()

# 1. 检查当前 Python 进程数量
print("【步骤 1】检查 Python 进程...")
print("-" * 70)

try:
    result = subprocess.run(
        ['tasklist', '/FI', 'IMAGENAME eq python.exe'],
        capture_output=True,
        text=True,
        encoding='gbk',
        errors='ignore'
    )
    
    python_processes = [line for line in result.stdout.split('\n') if 'python.exe' in line.lower()]
    
    if len(python_processes) > 3:
        print(f"⚠ 警告: 发现 {len(python_processes)} 个 Python 进程在运行")
        print("  这可能导致相机被占用")
        print()
        print("建议: 关闭不必要的 Python 程序和终端窗口")
    else:
        print(f"✓ Python 进程数量正常 ({len(python_processes)} 个)")
except Exception as e:
    print(f"⚠ 无法检查进程: {e}")

print()

# 2. 检查 MVS 进程
print("【步骤 2】检查 MVS 软件...")
print("-" * 70)

mvs_processes = ['MVS.exe', 'MVViewer.exe', 'MVStudio.exe']
found_mvs = False

for proc_name in mvs_processes:
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {proc_name}'],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )
        
        if proc_name.lower() in result.stdout.lower():
            print(f"✗ 发现 {proc_name} 正在运行")
            found_mvs = True
            
            # 尝试关闭
            response = input(f"  是否关闭 {proc_name}？(y/n): ")
            if response.lower() == 'y':
                subprocess.run(['taskkill', '/F', '/IM', proc_name], 
                             capture_output=True)
                print(f"  ✓ 已关闭 {proc_name}")
                time.sleep(1)
    except Exception:
        pass

if not found_mvs:
    print("✓ 未发现 MVS 相关进程")

print()

# 3. 尝试测试相机
print("【步骤 3】测试相机访问...")
print("-" * 70)

try:
    import chg_hik
    
    output_dir = Path("temp_smart_fix")
    output_dir.mkdir(exist_ok=True)
    
    max_attempts = 3
    success = False
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n尝试 {attempt}/{max_attempts}...")
        
        try:
            result = chg_hik.capture_images(
                output_dir=str(output_dir),
                format="BMP",
                quality=5,
            )
            
            if result.get('success') and result.get('images_captured', 0) > 0:
                print("✓ 相机测试成功！")
                
                # 验证图片
                images = list(output_dir.glob("*.bmp"))
                if images:
                    img = images[0]
                    size = img.stat().st_size
                    print(f"✓ 图片已保存: {img.name} ({size:,} 字节)")
                    success = True
                    break
            else:
                print(f"✗ 测试失败: {result.get('message')}")
                
        except RuntimeError as e:
            error_msg = str(e)
            print(f"✗ 错误: {error_msg}")
            
            if "-2147483115" in error_msg or "打开设备失败" in error_msg:
                if attempt < max_attempts:
                    print(f"  相机仍被占用，等待 2 秒后重试...")
                    time.sleep(2)
                else:
                    print()
                    print("【建议的解决方案】")
                    print()
                    print("相机仍然被占用，请尝试以下方法：")
                    print()
                    print("1. 重启 Django 开发服务器")
                    print("   - 在运行服务器的终端按 Ctrl+C")
                    print("   - 重新运行: python manage.py runserver")
                    print()
                    print("2. 关闭所有 Python 终端窗口，只保留一个")
                    print()
                    print("3. 如果是网络相机，使用 IP 直连模式")
                    print("   - 编辑 settings.py")
                    print("   - 设置 CAMERA_IP 和 PC_IP")
                    print()
                    print("4. 重启计算机（最彻底的方法）")
                    sys.exit(1)
            else:
                break
    
    if success:
        print()
        print("=" * 70)
        print("✓ 相机问题已解决！")
        print("=" * 70)
        print()
        print("下一步：")
        print("1. 确保 Django 服务器正在运行")
        print("2. 访问: http://127.0.0.1:8083/vision/foam-inspector/")
        print("3. 点击「刷新预览」按钮测试")
    
except ImportError:
    print("✗ chg_hik 模块未安装")
    print()
    print("请先安装相机模块:")
    print("  pip install Hik_camera\\hik_camera-0.4.1-cp311-abi3-win_amd64.whl")
    sys.exit(1)
except Exception as e:
    print(f"✗ 未知错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
