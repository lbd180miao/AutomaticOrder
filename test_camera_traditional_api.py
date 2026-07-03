"""
测试相机拍照 - 使用传统 API
"""
import sys
from pathlib import Path

try:
    import chg_hik
except ImportError:
    print("✗ chg_hik 模块未安装")
    sys.exit(1)

print("=" * 70)
print("海康威视相机拍照测试（传统 API - capture_images）")
print("=" * 70)
print()

output_dir = Path("temp_test_traditional")
output_dir.mkdir(exist_ok=True)

try:
    print("【测试】使用 capture_images() 函数拍照...")
    print(f"输出目录: {output_dir}")
    print()
    
    result = chg_hik.capture_images(
        output_dir=str(output_dir),
        format="BMP",
        quality=5,
    )
    
    print("=" * 70)
    print("采集结果:")
    print(f"  成功: {result.get('success')}")
    print(f"  找到相机数: {result.get('cameras_found', 'N/A')}")
    print(f"  成功初始化相机数: {result.get('cameras_initialized')}")
    print(f"  采集图片总数: {result.get('images_captured')}")
    print(f"  消息: {result.get('message')}")
    print("=" * 70)
    print()
    
    if result.get('success'):
        print("✓ 拍照成功！")
        # 列出输出目录中的图片
        images = list(output_dir.glob("*.bmp"))
        if images:
            print(f"✓ 找到 {len(images)} 张图片:")
            for img in images:
                size = img.stat().st_size
                print(f"  - {img.name}: {size:,} 字节 ({size/1024/1024:.2f} MB)")
        else:
            print("⚠ 输出目录中没有找到图片文件")
    else:
        print(f"✗ 拍照失败: {result.get('message')}")
        sys.exit(1)
        
except Exception as e:
    print(f"✗ 错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("测试完成！")
print("=" * 70)
