"""
测试 vision task 查询
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import VisionTask

print("开始测试 VisionTask 查询...")
print("=" * 60)

try:
    # 测试基本查询
    print("\n[1] 测试基本查询...")
    tasks = VisionTask.objects.all()[:5]
    count = tasks.count()
    print(f"✓ 成功查询到 {count} 条记录")
    
    # 测试 select_related
    print("\n[2] 测试 select_related('product', 'rack')...")
    tasks = VisionTask.objects.select_related('product', 'rack')[:5]
    for task in tasks:
        product_code = task.product.product_code if task.product else "无"
        rack_code = task.rack.rack_code if task.rack else "无"
        print(f"  Task #{task.id}: product={product_code}, rack={rack_code}")
    print("✓ select_related 查询成功")
    
    # 测试 prefetch_related
    print("\n[3] 测试 prefetch_related('images', 'foam_results', 'rack_results')...")
    tasks = (
        VisionTask.objects
        .select_related('product', 'rack')
        .prefetch_related('images', 'foam_results', 'rack_results')
        .order_by('-created_at')[:5]
    )
    for task in tasks:
        images_count = task.images.count()
        foam_count = task.foam_results.count()
        rack_count = task.rack_results.count()
        print(f"  Task #{task.id}: images={images_count}, foam={foam_count}, rack={rack_count}")
    print("✓ prefetch_related 查询成功")
    
    # 测试完整的视图查询
    print("\n[4] 测试完整的视图查询...")
    tasks = (
        VisionTask.objects
        .select_related('product', 'rack')
        .prefetch_related('images', 'foam_results', 'rack_results')
        .order_by('-created_at')[:200]
    )
    # 强制执行查询
    task_list = list(tasks)
    print(f"✓ 查询成功，共 {len(task_list)} 条记录")
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过！/vision/tasks/ 页面应该可以正常工作。")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ 查询失败：{type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
