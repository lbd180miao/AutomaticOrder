"""
测试计算偏差是否保存到视觉记录
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import VisionTask, RackLocationResult
from apps.core.constants import VisionTaskType

print("=" * 60)
print("查询视觉记录")
print("=" * 60)

# 查询所有料架定位任务
tasks = VisionTask.objects.filter(
    task_type=VisionTaskType.RACK_LOCATING
).order_by('-created_at')[:10]

print(f"\n找到 {tasks.count()} 条料架定位记录\n")

if tasks.count() == 0:
    print("❌ 没有找到任何料架定位记录！")
    print("\n请按以下步骤测试：")
    print("1. 访问 http://127.0.0.1:8083/vision/rack-locator-panel/")
    print("2. 选择一个配方")
    print("3. 点击「📡 采集点云」")
    print("4. 点击「🎯 计算偏差」")
    print("5. 再次运行此脚本")
else:
    print("✅ 找到料架定位记录：\n")
    
    for i, task in enumerate(tasks, 1):
        print(f"{i}. 任务 ID: {task.id}")
        print(f"   状态: {task.status}")
        print(f"   创建时间: {task.created_at}")
        
        # 查询关联的结果
        results = task.rack_results.all()
        if results:
            for result in results:
                print(f"   配方: {result.recipe.recipe_name if result.recipe else 'N/A'}")
                print(f"   偏差: X={result.offset_x}, Y={result.offset_y}, Z={result.offset_z}")
                print(f"   置信度: {result.confidence}")
                print(f"   成功: {'✅' if result.is_success else '❌'}")
        else:
            print("   ⚠️ 无关联结果")
        print()

print("=" * 60)
print("\n如需查看完整记录，请访问:")
print("http://127.0.0.1:8083/vision/tasks/")
print("=" * 60)
