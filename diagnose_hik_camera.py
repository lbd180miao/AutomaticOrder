"""
海康威视相机诊断脚本

运行此脚本可以快速诊断 HIK 相机无法拍照的原因
"""

import os
import sys
import subprocess
import django
import sys
sys.path.insert(0, '.venv/Lib/site-packages')
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.conf import settings


def diagnose():
    """诊断 HIK 相机问题"""
    
    print("=" * 70)
    print("🔍 海康威视相机诊断工具")
    print("=" * 70)
    print()
    
    # ========== 1. 检查配置 ==========
    print("【1】检查相机配置")
    print("-" * 70)
    
    hik_settings = getattr(settings, 'AUTOMATIC_ORDER', {}).get('HIK_CAMERA', {})
    
    if not hik_settings:
        print("❌ HIK_CAMERA 配置未找到")
        print("   → 请检查 settings.py 中的 AUTOMATIC_ORDER['HIK_CAMERA'] 配置")
        return
    
    print("✅ 配置信息：")
    print(f"   - OUTPUT_DIR: {hik_settings.get('OUTPUT_DIR')}")
    print(f"   - SDK_LIB_DIR: {hik_settings.get('SDK_LIB_DIR')}")
    print(f"   - CAMERA_IP: {hik_settings.get('CAMERA_IP')}")
    print(f"   - PC_IP: {hik_settings.get('PC_IP')}")
    print(f"   - FORMAT: {hik_settings.get('FORMAT')}")
    print(f"   - QUALITY: {hik_settings.get('QUALITY')}")
    print(f"   - RUN_IN_SUBPROCESS: {hik_settings.get('RUN_IN_SUBPROCESS')}")
    
    print()
    
    # ========== 2. 检查 SDK 路径 ==========
    print("【2】检查 SDK 路径")
    print("-" * 70)
    
    sdk_lib_dir = hik_settings.get('SDK_LIB_DIR')
    if sdk_lib_dir:
        sdk_path = Path(sdk_lib_dir)
        if sdk_path.exists():
            print(f"✅ SDK 目录存在: {sdk_lib_dir}")
            
            # 检查关键 DLL 文件
            key_dlls = [
                'MvCameraControl.dll',
                'MVGigEVisionSDK.dll',
                'MvUsb3vTL.dll',
            ]
            missing_dlls = []
            for dll in key_dlls:
                dll_path = sdk_path / dll
                if dll_path.exists():
                    print(f"   ✅ {dll}")
                else:
                    print(f"   ❌ {dll} (未找到)")
                    missing_dlls.append(dll)
            
            if missing_dlls:
                print()
                print("⚠️  缺少关键 DLL 文件，可能需要重新安装 MVS SDK")
        else:
            print(f"❌ SDK 目录不存在: {sdk_lib_dir}")
            print("   → 请安装海康威视 MVS SDK")
            print("   → 或修改 settings.py 中的 SDK_LIB_DIR 路径")
    else:
        print("⚠️  SDK_LIB_DIR 未配置")
    
    print()
    
    # ========== 3. 检查 chg_hik 模块 ==========
    print("【3】检查 chg_hik Python 绑定")
    print("-" * 70)
    
    try:
        import importlib
        chg_hik = importlib.import_module('chg_hik')
        print(f"✅ chg_hik 已安装")
        print(f"   - 路径: {chg_hik.__file__}")
        
        # 尝试访问 Camera 类
        if hasattr(chg_hik, 'Camera'):
            print(f"   - Camera 类: 可用")
        else:
            print(f"   - Camera 类: 不可用 (可能是旧版本)")
        
        if hasattr(chg_hik, 'capture_images'):
            print(f"   - capture_images 函数: 可用 (legacy API)")
    except ImportError as e:
        print(f"❌ chg_hik 未安装")
        print(f"   错误: {e}")
        print()
        print("   → 解决方案：")
        print("      1. cd 到项目 Hik_camera 目录")
        print("      2. 激活虚拟环境: .venv\\Scripts\\activate")
        print("      3. 编译安装: maturin develop --release")
        return
    
    print()
    
    # ========== 4. 检查网络配置 ==========
    print("【4】检查网络配置")
    print("-" * 70)
    
    camera_ip = hik_settings.get('CAMERA_IP')
    pc_ip = hik_settings.get('PC_IP')
    
    if camera_ip and pc_ip:
        print(f"相机 IP: {camera_ip}")
        print(f"本机 IP: {pc_ip}")
        print()
        
        # Ping 测试
        print(f"⏳ 测试相机网络连通性...")
        try:
            result = subprocess.run(
                ['ping', '-n', '1', '-w', '2000', camera_ip],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                print(f"✅ 相机 {camera_ip} 网络可达")
            else:
                print(f"❌ 相机 {camera_ip} 无法 ping 通")
                print("   → 可能原因：")
                print("      1. 相机未通电")
                print("      2. 网线未连接")
                print("      3. IP 地址配置错误")
                print("      4. 网络防火墙阻止")
        except subprocess.TimeoutExpired:
            print(f"⚠️  Ping 超时")
        except Exception as e:
            print(f"⚠️  无法执行 ping: {e}")
        
        print()
        
        # 检查本机 IP
        print("⏳ 检查本机网卡配置...")
        try:
            result = subprocess.run(
                ['ipconfig'],
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
            )
            
            if pc_ip in result.stdout:
                print(f"✅ 找到配置的本机 IP: {pc_ip}")
            else:
                print(f"❌ 未找到配置的本机 IP: {pc_ip}")
                print("   → 需要手动配置网卡：")
                print("      1. 控制面板 -> 网络和共享中心")
                print("      2. 更改适配器设置")
                print("      3. 右键网卡 -> 属性 -> IPv4 -> 手动配置")
                print(f"      4. IP: {pc_ip}, 子网掩码: 255.255.0.0")
        except Exception as e:
            print(f"⚠️  无法执行 ipconfig: {e}")
    else:
        print("⏳ USB 模式（未配置网络 IP）")
        print("   系统将自动检测第一台连接的相机")
    
    print()
    
    # ========== 5. 检查输出目录 ==========
    print("【5】检查输出目录")
    print("-" * 70)
    
    output_dir = Path(hik_settings.get('OUTPUT_DIR', settings.MEDIA_ROOT / 'hik_captures'))
    
    if output_dir.exists():
        print(f"✅ 输出目录存在: {output_dir}")
        
        # 测试写入权限
        try:
            test_file = output_dir / '.write_test'
            test_file.touch()
            test_file.unlink()
            print(f"   ✅ 目录可写")
        except Exception as e:
            print(f"   ❌ 目录不可写: {e}")
            print("   → 请检查目录权限")
    else:
        print(f"⚠️  输出目录不存在: {output_dir}")
        print("   → 系统会自动创建")
    
    print()
    
    # ========== 6. 尝试连接相机 ==========
    print("【6】尝试连接相机并拍照")
    print("-" * 70)
    
    print("⏳ 正在测试相机捕获...")
    print()
    
    try:
        from apps.devices.adapters.camera import CameraAdapter
        
        adapter = CameraAdapter()
        result = adapter.capture(
            camera_code='CAM-INSPECT-FOAM-01',
            task_type='FOAM_INSPECTION'
        )
        
        print("✅ 相机捕获成功！")
        print(f"   - 图像路径: {result.get('image_path')}")
        
        image_path = result.get('image_path')
        if image_path:
            path = Path(image_path)
            if path.exists():
                size_mb = path.stat().st_size / 1024 / 1024
                print(f"   - 文件大小: {size_mb:.2f} MB")
                print(f"   - 格式: {path.suffix}")
            else:
                print(f"   ⚠️  图像文件不存在: {image_path}")
        
        print()
        print("=" * 70)
        print("🎉 诊断完成：相机工作正常！")
        print("=" * 70)
        print()
        print("✅ 现在可以在网页上点击「拍照检测」按钮测试")
        
    except RuntimeError as e:
        error_msg = str(e)
        print(f"❌ 相机捕获失败")
        print(f"   错误: {error_msg}")
        print()
        
        # 根据错误信息给出具体建议
        if '错误码: -2147483115' in error_msg or '0x80070005' in error_msg:
            print("📌 错误码 -2147483115 (MV_E_ACCESS_DENIED)")
            print("   含义: 设备被占用或权限不足")
            print()
            print("   🔧 解决方案：")
            print("   【方案1】关闭占用相机的程序")
            print("      1. 打开任务管理器 (Ctrl+Shift+Esc)")
            print("      2. 结束以下进程（如果存在）：")
            print("         - MVS Client")
            print("         - MVSClient.exe")
            print("         - Hikrobot.exe")
            print("         - 其他视觉检测程序")
            print("      3. 重启 Django 服务器")
            print("      4. 重新运行此诊断脚本")
            print()
            print("   【方案2】检查防火墙")
            print("      1. 临时关闭 Windows 防火墙测试")
            print("      2. 如果可以工作，添加防火墙例外")
            print()
            print("   【方案3】相机电源重启")
            print("      1. 断开相机电源")
            print("      2. 等待 10 秒")
            print("      3. 重新接通电源")
            print("      4. 等待相机初始化完成（约 30 秒）")
            print("      5. 重新运行此诊断脚本")
            
        elif '错误码: -2147483644' in error_msg or 'not found' in error_msg.lower():
            print("📌 设备未找到")
            print()
            print("   🔧 解决方案：")
            print("   1. 检查相机电源是否开启")
            print("   2. 检查网线/USB 线是否连接")
            print("   3. 使用 MVS Client 软件扫描设备")
            print("   4. 检查 IP 地址配置是否正确")
            
        elif 'timeout' in error_msg.lower():
            print("📌 连接超时")
            print()
            print("   🔧 解决方案：")
            print("   1. 检查网络连接")
            print("   2. 确认相机 IP 和本机 IP 在同一网段")
            print("   3. 关闭防火墙测试")
            
        elif 'chg_hik' in error_msg:
            print("📌 chg_hik 模块问题")
            print()
            print("   🔧 解决方案：")
            print("   1. 重新编译安装 chg_hik:")
            print("      cd <Hik_camera_project_dir>")
            print("      maturin develop --release")
            
        else:
            print("   🔧 通用解决方案：")
            print("   1. 重启相机电源")
            print("   2. 重启 Django 服务器")
            print("   3. 重启电脑（如果问题持续）")
            print("   4. 检查 MVS Client 是否能正常工作")
        
        print()
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ 未预期的错误: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # ========== 7. 检查历史捕获记录 ==========
    print("【7】检查历史捕获记录")
    print("-" * 70)
    
    if output_dir.exists():
        # 查找最近的成功捕获
        image_files = list(output_dir.glob('*.bmp')) + list(output_dir.glob('*.png')) + list(output_dir.glob('*.jpg'))
        if image_files:
            latest = max(image_files, key=lambda p: p.stat().st_mtime)
            import datetime
            mtime = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
            print(f"✅ 最近一次成功捕获:")
            print(f"   - 文件: {latest.name}")
            print(f"   - 时间: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   - 大小: {latest.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("⚠️  没有历史捕获记录")
        
        # 查找失败的捕获记录
        failed_captures = list(output_dir.glob('.hik_capture_*.json.tmp'))
        if failed_captures:
            print()
            print(f"⚠️  发现 {len(failed_captures)} 个失败的捕获记录")
            print("   这可能表示最近的捕获尝试失败了")
    
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
