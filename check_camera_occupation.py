"""
检查相机是否被其他程序占用
"""
import subprocess
import sys

def check_camera_processes():
    print("=" * 70)
    print("🔍 检查相机占用情况")
    print("=" * 70)
    print()
    
    # 查找可能占用相机的进程
    camera_process_keywords = [
        'MVS',
        'mvs',
        'MVSClient',
        'Hikrobot',
        'hikrobot',
        'GigE',
        'MvCamera',
    ]
    
    print("⏳ 正在扫描进程...")
    print()
    
    try:
        # 使用 tasklist 命令获取所有进程
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
        )
        
        lines = result.stdout.strip().split('\n')
        found_processes = []
        
        for line in lines:
            if not line.strip():
                continue
            
            # CSV 格式: "进程名","PID","会话名","会话#","内存使用"
            parts = line.split(',')
            if len(parts) < 2:
                continue
            
            process_name = parts[0].strip('"')
            pid = parts[1].strip('"')
            
            # 检查是否匹配关键字
            for keyword in camera_process_keywords:
                if keyword.lower() in process_name.lower():
                    found_processes.append({
                        'name': process_name,
                        'pid': pid,
                    })
                    break
        
        if found_processes:
            print("❌ 发现以下可能占用相机的进程：")
            print()
            for proc in found_processes:
                print(f"   🔴 {proc['name']} (PID: {proc['pid']})")
            
            print()
            print("=" * 70)
            print("🛠️  解决方案")
            print("=" * 70)
            print()
            print("请执行以下操作之一：")
            print()
            print("【方案 1】手动关闭进程（推荐）")
            print("   1. 按 Ctrl + Shift + Esc 打开任务管理器")
            print("   2. 在「进程」或「详细信息」标签页找到以下进程：")
            for proc in found_processes:
                print(f"      - {proc['name']}")
            print("   3. 右键每个进程 -> 结束任务")
            print()
            
            print("【方案 2】使用命令行结束进程")
            print("   以管理员身份运行命令提示符，然后执行：")
            for proc in found_processes:
                print(f"      taskkill /F /PID {proc['pid']}")
            print()
            
            print("【方案 3】如果是 MVS 客户端")
            print("   1. 正常关闭 MVS 客户端窗口")
            print("   2. 如果无法关闭，使用方案 1 或 2 强制结束")
            print()
            
            return False
        else:
            print("✅ 未发现占用相机的进程")
            print()
            print("相机应该可用，如果仍然无法拍照，可能是：")
            print("   1. 相机未通电或网络未连接")
            print("   2. IP 地址配置错误")
            print("   3. 相机固件异常，需要重启相机电源")
            print()
            return True
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        print()
        print("请手动检查任务管理器中是否有 MVS 或 Hikrobot 相关进程")
        return None


def suggest_next_steps():
    print("=" * 70)
    print("📋 下一步操作")
    print("=" * 70)
    print()
    print("1. 关闭所有占用相机的进程（如果有）")
    print("2. 确保相机通电且网络连接正常")
    print("3. 重新运行测试:")
    print("   python test_camera_capture.py")
    print()
    print("4. 如果问题持续，尝试：")
    print("   - 重启相机电源（断电 10 秒后重新上电）")
    print("   - 重启电脑")
    print()


if __name__ == '__main__':
    is_clear = check_camera_processes()
    suggest_next_steps()
    
    if is_clear:
        print("✅ 相机应该可用，正在测试连接...")
        print()
        
        # 尝试运行测试
        result = subprocess.run(
            [sys.executable, 'test_camera_capture.py'],
            cwd='.',
        )
        
        if result.returncode == 0:
            print()
            print("🎉 相机测试成功！")
        else:
            print()
            print("⚠️  相机测试仍然失败，请检查硬件连接和网络配置")
