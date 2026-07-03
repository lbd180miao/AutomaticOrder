"""
修复相机访问问题 - 检测并释放被占用的相机
"""
import sys
import subprocess
import time
from pathlib import Path

try:
    import chg_hik
except ImportError:
    print("✗ chg_hik 模块未安装")
    sys.exit(1)

print("=" * 70)
print("海康威视相机访问问题诊断与修复")
print("=" * 70)
print()

print("【问题诊断】错误码 -2147483115 表示：")
print("  - 相机正在被其他程序占用")
print("  - 可能的占用者：MVS 客户端、其他 Python 进程、崩溃未释放的连接")
print()

# 1. 检查是否有 MVS 进程
print("【步骤 1】检查是否有 MVS 或其他相机程序运行...")
print("-" * 70)

def check_processes():
    """检查可能占用相机的进程"""
    process_names = ['MVS.exe', 'MVViewer.exe', 'python.exe', 'pythonw.exe']
    found_processes = []
    
    try:
        result = subprocess.run(
            ['tasklist'],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )
        
        for proc_name in process_names:
            if proc_name.lower() in result.stdout.lower():
                found_processes.append(proc_name)
        
        return found_processes
    except Exception as e:
        print(f"⚠ 无法检查进程: {e}")
        return []

processes = check_processes()
if processes:
    print(f"✗ 发现以下可能占用相机的进程:")
    for proc in processes:
        print(f"  - {proc}")
    print()
    print("建议操作:")
    print("  1. 关闭 MVS 客户端软件（如果打开）")
    print("  2. 关闭其他可能使用相机的程序")
    print("  3. 如果是 Python 进程，可能是之前崩溃未释放")
    print()
    
    response = input("是否已关闭相关程序？(y/n): ")
    if response.lower() != 'y':
        print("\n请先关闭占用相机的程序，然后重新运行此脚本")
        sys.exit(0)
else:
    print("✓ 未发现明显占用相机的进程")
print()

# 2. 尝试等待并重试
print("【步骤 2】尝试连接相机（带重试机制）...")
print("-" * 70)

output_dir = Path("temp_test_fix")
output_dir.mkdir(exist_ok=True)

max_retries = 3
for attempt in range(1, max_retries + 1):
    print(f"\n尝试 {attempt}/{max_retries}...")
    
    try:
        result = chg_hik.capture_images(
            output_dir=str(output_dir),
            format="BMP",
            quality=5,
        )
        
        if result.get('success') and result.get('images_captured', 0) > 0:
            print("✓ 拍照成功！")
            print(f"  采集图片数: {result.get('images_captured')}")
            
            # 检查图片
            images = list(output_dir.glob("*.bmp"))
            if images:
                print(f"✓ 找到 {len(images)} 张图片:")
                for img in images:
                    size = img.stat().st_size
                    print(f"  - {img.name}: {size:,} 字节 ({size/1024/1024:.2f} MB)")
            
            print()
            print("=" * 70)
            print("✓ 相机访问问题已解决！")
            print("=" * 70)
            print()
            print("现在可以在 Web 界面使用「刷新预览」功能了。")
            print("如果 Web 界面仍然失败，请确保：")
            print("  1. Django 开发服务器已重启")
            print("  2. 没有其他 Python 进程占用相机")
            sys.exit(0)
        else:
            print(f"✗ 拍照失败: {result.get('message')}")
            
    except RuntimeError as e:
        error_msg = str(e)
        print(f"✗ 错误: {error_msg}")
        
        if "-2147483115" in error_msg or "打开设备失败" in error_msg:
            print()
            print("  ⚠ 相机仍被占用，可能的原因：")
            print("  1. MVS 软件仍在运行（在后台）")
            print("  2. 之前的 Python 进程崩溃未正常释放相机")
            print("  3. 系统缓存未清理")
            
            if attempt < max_retries:
                wait_time = 3
                print(f"\n  等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        else:
            print(f"\n  这是不同的错误，不是设备占用问题")
            break
    
    except Exception as e:
        print(f"✗ 未知错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        break

print()
print("=" * 70)
print("所有尝试均失败")
print("=" * 70)
print()
print("【高级解决方案】")
print()
print("1. 重启计算机（最彻底的方法）")
print("   - 这会清除所有占用相机的进程")
print()
print("2. 检查设备管理器")
print("   - 打开「设备管理器」")
print("   - 找到相机设备")
print("   - 右键 → 禁用设备")
print("   - 等待 5 秒")
print("   - 右键 → 启用设备")
print()
print("3. 使用任务管理器强制结束进程")
print("   - 打开任务管理器 (Ctrl+Shift+Esc)")
print("   - 找到所有 Python 进程和 MVS 相关进程")
print("   - 右键 → 结束任务")
print()
print("4. 检查相机连接")
print("   - 拔掉相机连接线（USB/网线）")
print("   - 等待 10 秒")
print("   - 重新连接")
print()
print("5. 修改代码使用 IP 直连模式（如果是网络相机）")
print("   - 在 settings.py 中配置相机 IP 地址")
print("   - IP 直连模式更稳定，不容易被占用")
