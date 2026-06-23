#!/usr/bin/env python
"""
清理视觉模块记录，只保留最近的3条记录
运行: python cleanup_vision_records.py
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import VisionTask


def cleanup_vision_records():
    """清理视觉记录，只保留最近的3条"""
    print("=" * 60)
    print("清理视觉模块记录")
    print("=" * 60)
    
    # 获取所有记录数量
    total_count = VisionTask.objects.count()
    print(f"\n当前总记录数: {total_count}")
    
    if total_count <= 3:
        print("记录数量 <= 3，无需清理")
        return
    
    # 获取最近的3条记录的ID（按created_at降序）
    recent_ids = list(
        VisionTask.objects
        .order_by('-created_at')[:3]
        .values_list('id', flat=True)
    )
    
    print(f"\n保留的记录ID: {recent_ids}")
    
    # 删除除了最近3条之外的所有记录
    # 由于设置了CASCADE，关联的RackLocationResult、FoamInspectionResult、VisionImage会自动删除
    deleted_count, deleted_details = VisionTask.objects.exclude(id__in=recent_ids).delete()
    
    print(f"\n删除操作完成:")
    print(f"  - 总共删除: {deleted_count} 条记录")
    print(f"  - 详细信息: {deleted_details}")
    
    # 确认剩余记录
    remaining_count = VisionTask.objects.count()
    print(f"\n剩余记录数: {remaining_count}")
    
    # 显示保留的记录
    print("\n保留的记录:")
    for task in VisionTask.objects.order_by('-created_at'):
        print(f"  - ID={task.id}, 类型={task.task_type}, 状态={task.status}, 创建时间={task.created_at}")
    
    print("\n" + "=" * 60)
    print("清理完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        cleanup_vision_records()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
