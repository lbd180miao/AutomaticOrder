"""
测试采集点云API是否正常工作
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.test import RequestFactory
from apps.vision.views import api_rack_location_workbench_capture
import json

def test_capture_api():
    """测试采集点云API"""
    factory = RequestFactory()
    
    # 创建POST请求
    request = factory.post(
        '/api/rack-location/workbench/capture/',
        data=json.dumps({'recipe_id': None}),
        content_type='application/json'
    )
    
    # 添加CSRF token (测试环境)
    request.META['HTTP_X_CSRFTOKEN'] = 'test-token'
    
    print("=" * 60)
    print("测试采集点云API...")
    print("=" * 60)
    
    try:
        response = api_rack_location_workbench_capture(request)
        print(f"✓ HTTP状态码: {response.status_code}")
        print(f"✓ Content-Type: {response.get('Content-Type')}")
        
        # 解析响应内容
        content = response.content.decode('utf-8')
        print(f"\n响应内容:\n{content[:500]}...")  # 只显示前500个字符
        
        # 尝试解析为JSON
        try:
            data = json.loads(content)
            print(f"\n✓ JSON解析成功!")
            print(f"  - success: {data.get('success')}")
            if data.get('success'):
                print(f"  - pointcloud_token: {data.get('pointcloud_token', 'N/A')}")
                print(f"  - source: {data.get('source', 'N/A')}")
                print(f"  - image_width: {data.get('image_width', 'N/A')}")
                print(f"  - image_height: {data.get('image_height', 'N/A')}")
            else:
                print(f"  - error: {data.get('error')}")
        except json.JSONDecodeError as e:
            print(f"\n✗ JSON解析失败: {e}")
            print(f"  返回的不是JSON格式，可能是HTML错误页面")
            
    except Exception as e:
        print(f"✗ API调用失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_capture_api()
