#!/usr/bin/env python
"""测试泡棉检测API接口"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')

import django
django.setup()

from django.test import RequestFactory
from apps.vision.views import api_foam_capture_inspect, api_foam_upload_inspect
import json


def test_capture_inspect_api():
    """测试拍照检测API"""
    print("=== 测试拍照检测API ===\n")
    
    factory = RequestFactory()
    
    # 创建POST请求
    request = factory.post(
        '/vision/api/foam/capture-inspect/',
        data=json.dumps({'position_index': 0}),
        content_type='application/json'
    )
    
    try:
        response = api_foam_capture_inspect(request)
        data = json.loads(response.content)
        
        if data.get('success'):
            print("✓ API调用成功")
            result = data.get('result', {})
            print(f"  - 任务ID: {result.get('task_id')}")
            print(f"  - 位置索引: {result.get('position_index')}")
            print(f"  - 泡棉存在: {result.get('is_present')}")
            print(f"  - 位置对齐: {result.get('is_aligned')}")
            print(f"  - 边缘起翘: {result.get('has_lifted_edge')}")
            print(f"  - 分数: {result.get('score')}")
            print(f"  - 判定: {'合格' if result.get('is_passed') else '不合格'}")
            print(f"  - X偏移: {result.get('offset_x_px')} px")
            print(f"  - Y偏移: {result.get('offset_y_px')} px")
            print(f"  - 覆盖率: {result.get('coverage_ratio')}")
            print(f"  - 缺陷类型: {result.get('defect_type')}")
            print(f"  - 结果图: {result.get('result_image_url')}\n")
            return True
        else:
            print(f"✗ API调用失败: {data.get('error')}\n")
            return False
            
    except Exception as e:
        print(f"✗ 测试失败: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_upload_inspect_api():
    """测试上传图片检测API"""
    print("=== 测试上传图片检测API ===\n")
    
    # 创建测试图片
    import cv2
    import numpy as np
    
    width, height = 640, 480
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = (200, 200, 200)
    
    # 绘制模拟泡棉
    foam_x1, foam_y1 = 250, 180
    foam_x2, foam_y2 = 390, 300
    cv2.rectangle(image, (foam_x1, foam_y1), (foam_x2, foam_y2), (80, 100, 200), -1)
    
    # 保存为临时文件
    temp_path = BASE_DIR / 'media' / 'test_upload.jpg'
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(temp_path), image)
    
    print(f"创建测试图片: {temp_path}")
    
    factory = RequestFactory()
    
    # 模拟文件上传
    with open(temp_path, 'rb') as f:
        request = factory.post(
            '/vision/api/foam/upload-inspect/',
            data={
                'image': f,
                'position_index': 0,
            },
        )
        
        try:
            response = api_foam_upload_inspect(request)
            data = json.loads(response.content)
            
            if data.get('success'):
                print("✓ API调用成功")
                result = data.get('result', {})
                print(f"  - 任务ID: {result.get('task_id')}")
                print(f"  - 判定: {'合格' if result.get('is_passed') else '不合格'}")
                print(f"  - 分数: {result.get('score')}")
                print(f"  - 缺陷类型: {result.get('defect_type')}\n")
                return True
            else:
                print(f"✗ API调用失败: {data.get('error')}\n")
                return False
                
        except Exception as e:
            print(f"✗ 测试失败: {e}\n")
            import traceback
            traceback.print_exc()
            return False


def main():
    print("=" * 60)
    print("泡棉检测API接口测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 注意：拍照检测需要相机连接，这里会失败
    # 但上传检测应该能通过
    print("注意: 拍照检测API需要相机连接，可能会失败")
    print("      上传检测API使用模拟图片，应该能通过\n")
    
    # test1 = test_capture_inspect_api()
    # results.append(('拍照检测API', test1))
    
    test2 = test_upload_inspect_api()
    results.append(('上传检测API', test2))
    
    print("=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\n通过: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n✓ 所有测试通过！")
        return 0
    else:
        print("\n部分测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
