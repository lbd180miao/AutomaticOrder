"""测试ROI API端点"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe

print("=" * 60)
print("检查配方ROI数据")
print("=" * 60)

recipes = RackLocationRecipe.objects.all()[:3]

if not recipes:
    print("❌ 数据库中没有配方")
else:
    for recipe in recipes:
        print(f"\n配方 #{recipe.id}: {recipe.recipe_name}")
        print(f"  位置: POS{recipe.position_no} Layer{recipe.layer_no}")
        print(f"  roi_config存在: {'✅' if recipe.roi_config else '❌'}")
        
        if recipe.roi_config:
            target_roi = recipe.roi_config.get('target_roi')
            print(f"  target_roi存在: {'✅' if target_roi else '❌'}")
            
            if target_roi:
                print(f"  target_roi内容:")
                print(f"    x: {target_roi.get('x')}")
                print(f"    y: {target_roi.get('y')}")
                print(f"    w: {target_roi.get('w')}")
                print(f"    h: {target_roi.get('h')}")

print("\n" + "=" * 60)
print("测试API端点")
print("=" * 60)

# 测试API视图
from django.test import RequestFactory
from apps.vision import views

factory = RequestFactory()

if recipes:
    recipe_id = recipes[0].id
    request = factory.get(f'/vision/api/rack-location/recipes/{recipe_id}/')
    
    try:
        response = views.api_rack_location_recipe_detail(request, recipe_id)
        print(f"\nAPI响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            import json
            data = json.loads(response.content)
            print(f"API响应成功: {data.get('success')}")
            
            if data.get('success'):
                recipe_data = data.get('data', {}).get('recipe', {})
                roi_config = recipe_data.get('roi_config', {})
                target_roi = roi_config.get('target_roi')
                
                print(f"\n✅ API返回的roi_config: {roi_config}")
                print(f"✅ API返回的target_roi: {target_roi}")
            else:
                print(f"❌ API返回错误: {data.get('error')}")
        else:
            print(f"❌ API请求失败")
            
    except Exception as e:
        print(f"❌ 调用API时出错: {e}")
        import traceback
        traceback.print_exc()
else:
    print("跳过API测试（无配方数据）")

print("\n" + "=" * 60)
print("建议")
print("=" * 60)

if not recipes:
    print("1. 先创建至少一个配方")
    print("2. 在工作台中采集点云并绘制ROI")
    print("3. 点击「计算偏差」保存ROI")
elif not any(r.roi_config and r.roi_config.get('target_roi') for r in recipes):
    print("1. 现有配方中没有保存的ROI")
    print("2. 请在工作台中：")
    print("   - 选择配方")
    print("   - 采集点云")
    print("   - 手动绘制ROI")
    print("   - 点击「计算偏差」（会自动保存ROI）")
else:
    print("✅ 配方数据正常，可以测试自动加载ROI功能")
    print("   打开工作台: http://127.0.0.1:8083/vision/rack-locator-panel/")
    print("   打开浏览器控制台，查看[自动ROI]日志")
