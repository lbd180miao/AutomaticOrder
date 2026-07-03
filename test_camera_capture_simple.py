"""
简单的相机拍照测试 - 不使用上下文管理器
"""
import sys
from pathlib import Path

try:
    import chg_hik
except ImportError:
    print("✗ chg_hik 模块未安装")
    sys.exit(1)

print("=" * 70)
print("海康威视相机拍照测试（手动管理）")
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
    camera.open()  # 不指定 IP，自动检测
    camera_opened = True
    print("✓ 相机打开成功")
    print()
    
    # 拍照
    print("【步骤 3】拍照...")
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
        raise
    print()
    
    # 再拍一张测试连拍
    print("【步骤 4】再拍一张（测试连拍）...")
    try:
        image_path2 = camera.capture()
        print(f"✓ 第二次拍照成功！")
        print(f"  图像路径: {image_path2}")
    except Exception as capture_error2:
        print(f"✗ 第二次拍照失败: {capture_error2}")
    print()
    
except RuntimeError as e:
    print(f"✗ 运行时错误: {e}")
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
            # 尝试不同的关闭方法
            if hasattr(camera, 'close_camera'):
                camera.close_camera()
                print("✓ 使用 close_camera() 关闭成功")
            elif hasattr(camera, '__exit__'):
                camera.__exit__(None, None, None)
                print("✓ 使用 __exit__() 关闭成功")
            else:
                print("! 未找到关闭方法，相机可能未释放")
        except Exception as close_error:
            print(f"⚠ 关闭相机时出现警告: {close_error}")
            print("  （这通常不影响拍照结果）")

print()
print("=" * 70)
print("测试完成")
print("=" * 70)
