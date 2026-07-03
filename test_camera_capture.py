"""
测试相机拍照功能
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.devices.adapters.camera import CameraAdapter


def test_camera_capture():
    """测试相机拍照"""
    
    print("=" * 60)
    print("🔍 测试相机拍照功能")
    print("=" * 60)
    print()
    
    try:
        adapter = CameraAdapter()
        
        print("⏳ 正在拍照...")
        result = adapter.capture(
            camera_code='CAM-INSPECT-FOAM-01',
            task_type='FOAM_INSPECTION'
        )
        
        print("✅ 拍照成功！")
        print(f"   - success: {result.get('success')}")
        print(f"   - image_path: {result.get('image_path')}")
        print(f"   - camera_code: {result.get('camera_code')}")
        print(f"   - task_type: {result.get('task_type')}")
        
        # 检查文件是否存在
        image_path = result.get('image_path')
        if image_path:
            from pathlib import Path
            path = Path(image_path)
            if path.exists():
                print(f"   - 文件大小: {path.stat().st_size} 字节")
            else:
                print(f"   ⚠️  文件不存在: {image_path}")
        
    except Exception as e:
        print(f"❌ 拍照失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_camera_capture()
