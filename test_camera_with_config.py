"""
测试相机拍照 - 带参数配置
"""
import sys
from pathlib import Path

try:
    import chg_hik
except ImportError:
    print("✗ chg_hik 模块未安装")
    sys.exit(1)

print("=" * 70)
print("海康威视相机拍照测试（带参数配置）")
print("=" * 70)
print()

output_dir = Path("temp_test_output")
output_dir.mkdir(exist_ok=True)

camera = None
camera_opened = False

try:
    # 创建相机实例
    print("【步骤 1】创建 Camera 对象...")
    camera = chg_hik.Camera(output_dir=str(output_dir), format="BMP", quality=5)
    print("✓ Camera 对象创建成功")
    print()
    
    # 打开相机
    print("【步骤 2】打开相机（自动检测模式）...")
    camera.open()
    camera_opened = True
    print("✓ 相机打开成功")
    print()
    
    # 配置相机参数
    print("【步骤 3】配置相机参数...")
    try:
        config = chg_hik.CameraConfig()
        
        # 尝试自动曝光和自动增益
        print("  尝试启用自动曝光和自动增益...")
        config.exposure_auto = True
        config.gain_auto = True
        
        camera.configure(config)
        print("✓ 相机参数配置成功（自动模式）")
    except Exception as config_error:
        print(f"⚠ 配置失败，使用默认参数: {config_error}")
    print()
    
    # 拍照
    print("【步骤 4】拍照...")
    try:
        image_path = camera.capture()
        print(f"✓ 拍照成功！")
        print(f"  图像路径: {image_path}")
        
        # 检查文件
        img_file = Path(image_path)
        if img_file.exists():
            size = img_file.stat().st_size
            print(f"  文件大小: {size:,} 字节 ({size/1024/1024:.2f} MB)")
            if size > 0:
                print("✓ 图像文件有效")
            else:
                print("✗ 图像文件为空")
        else:
            print(f"✗ 图像文件不存在")
    except Exception as capture_error:
        print(f"✗ 拍照失败: {capture_error}")
        print()
        print("尝试手动设置曝光参数...")
        
        # 尝试手动曝光
        try:
            config2 = chg_hik.CameraConfig()
            config2.exposure_time = 5000.0  # 5ms
            config2.gain = 10.0  # 10dB
            camera.configure(config2)
            print("✓ 手动曝光参数设置成功")
            
            print("再次尝试拍照...")
            image_path = camera.capture()
            print(f"✓ 拍照成功！")
            print(f"  图像路径: {image_path}")
            
            img_file = Path(image_path)
            if img_file.exists():
                size = img_file.stat().st_size
                print(f"  文件大小: {size:,} 字节 ({size/1024/1024:.2f} MB)")
        except Exception as capture_error2:
            print(f"✗ 第二次拍照也失败: {capture_error2}")
            raise
    print()
    
except RuntimeError as e:
    print(f"✗ 运行时错误: {e}")
    print()
    print("可能的原因:")
    print("1. 相机可能处于异常状态")
    print("2. 相机可能需要在 MVS 软件中设置为软触发或连续模式")
    print("3. 相机固件可能需要更新")
    print()
    print("建议:")
    print("1. 打开海康威视 MVS 软件")
    print("2. 连接到相机")
    print("3. 检查相机的触发模式设置（建议设置为连续采集模式）")
    print("4. 在 MVS 中测试是否能正常拍照")
    sys.exit(1)
except Exception as e:
    print(f"✗ 未知错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # 关闭相机
    if camera and camera_opened:
        print("【步骤 5】关闭相机...")
        try:
            if hasattr(camera, 'close_camera'):
                camera.close_camera()
                print("✓ 相机关闭成功")
        except Exception as close_error:
            print(f"⚠ 关闭相机时出现警告: {close_error}")

print()
print("=" * 70)
print("测试完成")
print("=" * 70)
