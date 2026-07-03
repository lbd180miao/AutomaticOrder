"""
检查相机连接状态
"""
import sys
from pathlib import Path

try:
    import chg_hik
except ImportError:
    print("✗ chg_hik 模块未安装")
    sys.exit(1)

print("=" * 70)
print("海康威视相机连接状态检查")
print("=" * 70)
print()

print("【方法 1】枚举模式 - 自动检测所有相机")
print("-" * 70)
try:
    # 创建一个临时相机实例来测试
    output_dir = Path("temp_test_output")
    output_dir.mkdir(exist_ok=True)
    
    with chg_hik.Camera(output_dir=str(output_dir), format="BMP") as cam:
        print("✓ Camera 对象创建成功")
        
        # 尝试打开相机（自动检测模式）
        print("⏳ 尝试自动检测并打开相机...")
        cam.open()  # 不指定 IP，自动检测
        print("✓ 相机打开成功！")
        
        # 尝试拍照
        print("⏳ 尝试拍照...")
        image_path = cam.capture()
        print(f"✓ 拍照成功！图像保存至: {image_path}")
        
        # 检查文件
        img_file = Path(image_path)
        if img_file.exists():
            size = img_file.stat().st_size
            print(f"✓ 图像文件大小: {size:,} 字节 ({size/1024/1024:.2f} MB)")
        
except RuntimeError as e:
    print(f"✗ 错误: {e}")
    print()
    print("可能的原因:")
    print("1. 没有找到相机设备")
    print("2. 相机未通电")
    print("3. USB 或网络连接断开")
    print("4. 相机被其他程序占用（如 MVS 客户端）")
    print()
    print("建议操作:")
    print("1. 确认相机已通电并连接")
    print("2. 关闭 MVS 或其他相机软件")
    print("3. 使用 MVS 客户端确认能否看到相机")
    sys.exit(1)
except Exception as e:
    print(f"✗ 未知错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("✓ 相机连接正常，可以正常拍照！")
print("=" * 70)
print()
print("如果此脚本成功但 Web 界面失败，请检查:")
print("1. Django 服务是否使用正确的虚拟环境运行")
print("2. Web 服务器是否有权限访问相机")
print("3. 浏览器控制台是否有 JavaScript 错误")
