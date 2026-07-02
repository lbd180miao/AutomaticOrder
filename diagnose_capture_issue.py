"""
诊断采集点云问题的详细脚本
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.test import RequestFactory, Client
from django.urls import reverse
import json

def test_with_client():
    """使用Django测试客户端"""
    client = Client()
    
    print("=" * 80)
    print("使用Django测试客户端测试两个采集点云API")
    print("=" * 80)
    
    # 测试URL
    urls_to_test = [
        ('api_vision_3d_capture', 'vision:api_vision_3d_capture'),
        ('api_rack_location_workbench_capture', 'vision:api_rack_location_workbench_capture'),
    ]
    
    for name, url_name in urls_to_test:
        print(f"\n{'=' * 80}")
        print(f"测试: {name}")
        print(f"{'=' * 80}")
        
        try:
            url = reverse(url_name)
            print(f"✓ URL: {url}")
            
            # 发送POST请求
            response = client.post(
                url,
                data=json.dumps({'recipe_id': None, 'rack_side': 'LEFT', 'layer_no': 1}),
                content_type='application/json',
            )
            
            print(f"✓ HTTP状态码: {response.status_code}")
            print(f"✓ Content-Type: {response.get('Content-Type')}")
            
            # 尝试解析响应
            if response.get('Content-Type', '').startswith('application/json'):
                try:
                    data = json.loads(response.content)
                    print(f"✓ JSON解析成功")
                    print(f"  响应摘要: {json.dumps({k: (str(v)[:50] + '...') if len(str(v)) > 50 else v for k, v in list(data.items())[:5]}, indent=2, ensure_ascii=False)}")
                except json.JSONDecodeError as e:
                    print(f"✗ JSON解析失败: {e}")
                    print(f"  响应内容: {response.content.decode('utf-8')[:200]}...")
            else:
                print(f"✗ 返回的不是JSON格式")
                content = response.content.decode('utf-8')
                print(f"  Content-Type: {response.get('Content-Type')}")
                print(f"  响应内容前200字符: {content[:200]}...")
                
                # 检查是否是HTML错误页面
                if content.startswith('<!DOCTYPE') or content.startswith('<html'):
                    print(f"  ⚠️ 这是一个HTML页面，可能是错误页面！")
                    # 尝试提取错误信息
                    if '404' in content:
                        print(f"  ❌ 404 Not Found - URL路由可能不存在")
                    elif '403' in content:
                        print(f"  ❌ 403 Forbidden - 可能是CSRF验证失败")
                    elif '500' in content:
                        print(f"  ❌ 500 Internal Server Error - 服务器内部错误")
                        
        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()

def check_views_exist():
    """检查视图函数是否存在"""
    print(f"\n{'=' * 80}")
    print("检查视图函数是否存在")
    print("=" * 80)
    
    try:
        from apps.vision import views
        
        views_to_check = [
            'api_vision_3d_capture',
            'api_rack_location_workbench_capture',
        ]
        
        for view_name in views_to_check:
            if hasattr(views, view_name):
                print(f"✓ {view_name} 存在")
            else:
                print(f"✗ {view_name} 不存在!")
                
    except Exception as e:
        print(f"✗ 导入视图模块失败: {e}")

def check_url_patterns():
    """检查URL模式"""
    print(f"\n{'=' * 80}")
    print("检查URL配置")
    print("=" * 80)
    
    from django.urls import get_resolver
    
    resolver = get_resolver()
    
    patterns_to_find = [
        'api/vision/3d/capture/',
        'api/rack-location/workbench/capture/',
    ]
    
    print("\n查找URL模式:")
    for pattern in patterns_to_find:
        found = False
        for url_pattern in resolver.url_patterns:
            if hasattr(url_pattern, 'pattern'):
                if pattern in str(url_pattern.pattern):
                    print(f"✓ 找到: {pattern}")
                    found = True
                    break
        if not found:
            print(f"✗ 未找到: {pattern}")

def check_middleware():
    """检查中间件配置"""
    print(f"\n{'=' * 80}")
    print("检查中间件配置")
    print("=" * 80)
    
    from django.conf import settings
    
    middleware = settings.MIDDLEWARE
    print(f"中间件数量: {len(middleware)}")
    
    # 检查关键中间件
    key_middleware = [
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ]
    
    for mw in key_middleware:
        if mw in middleware:
            print(f"✓ {mw}")
        else:
            print(f"✗ {mw} 未启用")

if __name__ == '__main__':
    check_views_exist()
    check_url_patterns()
    check_middleware()
    test_with_client()
    
    print(f"\n{'=' * 80}")
    print("诊断完成")
    print("=" * 80)
    print("\n如果看到HTML响应，说明请求没有到达视图函数，可能原因：")
    print("1. URL路由配置问题")
    print("2. 中间件拦截（如需要登录）")
    print("3. CSRF验证失败")
    print("\n建议：")
    print("1. 检查浏览器开发者工具的Network标签")
    print("2. 查看Django服务器控制台的输出")
    print("3. 访问调试页面: http://127.0.0.1:8000/vision/test-capture-debug/")
