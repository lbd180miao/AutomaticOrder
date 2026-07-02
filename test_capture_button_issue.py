"""
诊断「采集点云」按钮失效问题
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.urls import reverse
from apps.vision.models import RackLocationRecipe

print("=" * 60)
print("「采集点云」按钮诊断")
print("=" * 60)

# 1. 检查配方数据
print("\n1. 检查配方数据:")
recipes = RackLocationRecipe.objects.filter(enabled=True)
print(f"   活跃配方数量: {recipes.count()}")
if recipes.exists():
    first = recipes.first()
    print(f"   第一个配方: {first.recipe_name} (POS{first.position_no}, L{first.layer_no})")
    print(f"   配方ID: {first.id}")
else:
    print("   ⚠️  警告：没有活跃的配方")

# 2. 检查URL配置
print("\n2. 检查URL配置:")
try:
    capture_url = reverse('vision:api_rack_location_workbench_capture')
    print(f"   ✓ 采集点云API URL: {capture_url}")
except Exception as e:
    print(f"   ✗ 采集点云API URL错误: {e}")

try:
    workbench_url = reverse('vision:rack_location_workbench')
    print(f"   ✓ 工作台页面URL: {workbench_url}")
except Exception as e:
    print(f"   ✗ 工作台页面URL错误: {e}")

try:
    panel_url = reverse('vision:rack_locator_panel')
    print(f"   ✓ 面板页面URL: {panel_url}")
except Exception as e:
    print(f"   ✗ 面板页面URL错误: {e}")

# 3. 检查视图函数
print("\n3. 检查视图函数:")
try:
    from apps.vision import views
    
    # 检查采集点云视图
    if hasattr(views, 'api_rack_location_workbench_capture'):
        print("   ✓ api_rack_location_workbench_capture 视图存在")
    else:
        print("   ✗ api_rack_location_workbench_capture 视图不存在")
    
    # 检查工作台视图
    if hasattr(views, 'rack_location_workbench'):
        print("   ✓ rack_location_workbench 视图存在")
    else:
        print("   ✗ rack_location_workbench 视图不存在")
        
    # 检查面板视图
    if hasattr(views, 'rack_locator_panel'):
        print("   ✓ rack_locator_panel 视图存在")
    else:
        print("   ✗ rack_locator_panel 视图不存在")
        
except Exception as e:
    print(f"   ✗ 导入视图模块失败: {e}")

# 4. 检查静态文件
print("\n4. 检查静态文件:")
import pathlib
base_dir = pathlib.Path(__file__).parent

js_file = base_dir / "static" / "vision" / "js" / "rack_locator_workbench.js"
if js_file.exists():
    print(f"   ✓ JS文件存在: {js_file}")
    content = js_file.read_text(encoding='utf-8')
    
    # 检查关键代码
    if 'btn-capture' in content:
        print("   ✓ JS文件包含 btn-capture 按钮处理")
    if 'setButton(\'btn-capture\', true)' in content:
        print("   ✓ JS文件设置 btn-capture 为始终可用")
    if 'captureUrl' in content or 'CFG.captureUrl' in content:
        print("   ✓ JS文件包含 captureUrl 配置")
else:
    print(f"   ✗ JS文件不存在: {js_file}")

# 5. 检查模板文件
print("\n5. 检查模板文件:")
template_file = base_dir / "templates" / "vision" / "rack_locator_panel.html"
if template_file.exists():
    print(f"   ✓ 模板文件存在: {template_file}")
    content = template_file.read_text(encoding='utf-8')
    
    # 检查按钮定义
    if 'id="btn-capture"' in content:
        print("   ✓ 模板包含 btn-capture 按钮")
    else:
        print("   ✗ 模板未找到 btn-capture 按钮")
    
    # 检查JS配置
    if 'rackLocatorConfig' in content:
        print("   ✓ 模板包含 rackLocatorConfig 配置")
    else:
        print("   ✗ 模板未找到 rackLocatorConfig 配置")
    
    # 检查captureUrl配置
    if 'captureUrl' in content:
        print("   ✓ 模板包含 captureUrl 配置")
    else:
        print("   ⚠️  模板未找到 captureUrl 配置")
else:
    print(f"   ✗ 模板文件不存在: {template_file}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)

# 6. 测试API端点
print("\n6. 测试API端点:")
print("   使用Django test client测试...")

from django.test import Client
client = Client()

try:
    # 测试POST请求
    response = client.post(
        '/vision/api/rack-location/workbench/capture/',
        data='{}',
        content_type='application/json'
    )
    print(f"   HTTP状态码: {response.status_code}")
    print(f"   Content-Type: {response.get('Content-Type', 'N/A')}")
    
    if response.status_code == 200:
        import json
        try:
            data = json.loads(response.content)
            print(f"   ✓ API返回JSON: {list(data.keys())}")
        except:
            print(f"   ✗ API返回非JSON: {response.content[:200]}")
    else:
        print(f"   响应内容: {response.content[:200]}")
        
except Exception as e:
    print(f"   ✗ API测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("建议:")
print("=" * 60)
print("1. 在浏览器中按 Ctrl+Shift+I 打开开发者工具")
print("2. 切换到 Console 标签，查看是否有 JavaScript 错误")
print("3. 切换到 Network 标签，点击「采集点云」按钮")
print("4. 查看是否发送了请求，以及请求的URL和响应")
print("5. 检查按钮的 disabled 属性是否为 true")
print("6. 在 Console 中执行: document.getElementById('btn-capture').disabled")
print("=" * 60)
