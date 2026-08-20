import os
import django
import random
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.utils import timezone
from apps.core.constants import (
    WorkflowState, MesUploadStatus, MarkStatus,
    VisionTaskType, ResultStatus, RackSide, MesAction
)
from apps.production.models import ProductionBatch, Rack, RackRecipe, Product
from apps.vision.models import VisionTask, RackLocationResult, FoamInspectionResult
from apps.mes.models import MesRecord


def seed_demo_data():
    now = timezone.now()

    # 1. 生产批次
    batch_a, _ = ProductionBatch.objects.get_or_create(
        batch_no='BATCH-202608-A',
        defaults={'product_type': '汽车前保险杠', 'status': 'PROCESSING', 'started_at': now - timedelta(days=2)}
    )
    batch_b, _ = ProductionBatch.objects.get_or_create(
        batch_no='BATCH-202608-B',
        defaults={'product_type': '汽车后保险杠', 'status': 'PROCESSING', 'started_at': now - timedelta(days=1)}
    )

    # 2. 料框配方
    recipe_12, _ = RackRecipe.objects.get_or_create(
        recipe_code='RCP-BUMPER-3x4',
        defaults={
            'name': '标准保险杠料架配方 (3层x4件)',
            'rack_type': 'TYPE-RACK-STD',
            'layer_count': 3,
            'quantity_per_layer': 4,
            'total_quantity': 12,
            'layer_height': 350.0,
            'layer_spacing': 280.0,
            'tolerance_x': 5.0,
            'tolerance_y': 5.0,
            'tolerance_z': 5.0,
            'is_active': True,
        }
    )

    recipe_8, _ = RackRecipe.objects.get_or_create(
        recipe_code='RCP-BUMPER-2x4',
        defaults={
            'name': '小料架配方 (2层x4件)',
            'rack_type': 'TYPE-RACK-COMPACT',
            'layer_count': 2,
            'quantity_per_layer': 4,
            'total_quantity': 8,
            'layer_height': 350.0,
            'layer_spacing': 280.0,
            'tolerance_x': 5.0,
            'tolerance_y': 5.0,
            'tolerance_z': 5.0,
            'is_active': True,
        }
    )

    # 3. 创建 3 个典型料框
    racks_config = [
        ('RACK-20260820-001', 'FULL', recipe_12, batch_a, 12, 12),      # 满框已完成 (12/12)
        ('RACK-20260820-002', 'LOADING', recipe_12, batch_a, 8, 12),    # 装箱中 (8/12)
        ('RACK-20260820-003', 'FULL', recipe_8, batch_b, 8, 8),         # 满框已完成 (8/8)
    ]

    for rack_code, status, recipe, batch, count, total_cap in racks_config:
        rack, _ = Rack.objects.get_or_create(
            rack_code=rack_code,
            defaults={
                'rack_type': recipe.rack_type,
                'current_recipe': recipe,
                'status': status,
                'position_side': 'LEFT',
            }
        )
        rack.current_recipe = recipe
        rack.status = status
        rack.save()

        # 生成料框的 3D 定位记录 (每一层定位一次)
        for layer_no in range(1, recipe.layer_count + 1):
            vtask, _ = VisionTask.objects.get_or_create(
                task_type=VisionTaskType.RACK_LOCATING,
                rack=rack,
                status=ResultStatus.SUCCESS,
                defaults={'started_at': now - timedelta(hours=3), 'finished_at': now - timedelta(hours=3, seconds=-2)}
            )
            RackLocationResult.objects.get_or_create(
                vision_task=vtask,
                rack=rack,
                position_no=1,
                layer_no=layer_no,
                defaults={
                    'side': RackSide.LEFT,
                    'offset_x': round(random.uniform(-1.8, 2.3), 3),
                    'offset_y': round(random.uniform(-1.5, 1.9), 3),
                    'offset_z': round(random.uniform(-2.5, 3.1), 3),
                    'offset_rz': round(random.uniform(-0.5, 0.5), 3),
                    'measured_layer_height': recipe.layer_height + round(random.uniform(-0.8, 0.8), 2),
                    'measured_layer_spacing': recipe.layer_spacing + round(random.uniform(-0.5, 0.5), 2),
                    'recipe_layer_height': recipe.layer_height,
                    'recipe_layer_spacing': recipe.layer_spacing,
                    'confidence': 0.9650,
                    'is_recipe_matched': True,
                    'is_success': True,
                    'plc_write_status': 'SUCCESS',
                }
            )

        # 为该料框生成绑定的多个产品条码 (1个料框 -> count 个产品)
        prefix = rack_code.replace('RACK-', 'P-')
        for i in range(1, count + 1):
            prod_code = f"{prefix}-{i:04d}"
            layer_no = (i - 1) // recipe.quantity_per_layer + 1
            slot_no = (i - 1) % recipe.quantity_per_layer + 1

            is_done = (status == 'FULL' or i < count)
            state = WorkflowState.COMPLETED if is_done else WorkflowState.BOXING
            mes_status = MesUploadStatus.UPLOADED if is_done else MesUploadStatus.PENDING

            product, _ = Product.objects.get_or_create(
                product_code=prod_code,
                defaults={
                    'batch': batch,
                    'rack': rack,
                    'current_state': state,
                    'mark_status': MarkStatus.MARKED,
                    'mes_upload_status': mes_status,
                }
            )
            product.batch = batch
            product.rack = rack
            product.current_state = state
            product.mes_upload_status = mes_status
            product.save()

            # 生成泡棉检测记录
            vtask_foam, _ = VisionTask.objects.get_or_create(
                task_type=VisionTaskType.FOAM_INSPECTION,
                product=product,
                rack=rack,
                status=ResultStatus.SUCCESS,
                defaults={'started_at': now - timedelta(hours=1), 'finished_at': now - timedelta(hours=1, seconds=-1)}
            )
            FoamInspectionResult.objects.get_or_create(
                vision_task=vtask_foam,
                product=product,
                rack=rack,
                position_index=i,
                defaults={
                    'is_present': True,
                    'is_aligned': True,
                    'has_lifted_edge': False,
                    'score': round(random.uniform(92.5, 99.8), 2),
                    'is_passed': True,
                    'offset_x_mm': round(random.uniform(-0.8, 0.8), 3),
                    'offset_y_mm': round(random.uniform(-0.6, 0.6), 3),
                    'coverage_ratio': round(random.uniform(0.950, 0.995), 4),
                    'defect_type': 'NONE',
                }
            )

            # 生成 MES 上传记录
            if is_done:
                MesRecord.objects.get_or_create(
                    action=MesAction.UPLOAD_PRODUCT_BARCODE,
                    product=product,
                    rack=rack,
                    defaults={
                        'request_payload': {'product_code': prod_code, 'rack_code': rack_code, 'position_index': i},
                        'response_payload': {'status': 'OK', 'mes_id': f'MES-{random.randint(100000, 999999)}'},
                        'success': True,
                    }
                )

    print("演示数据生成完毕！已生成 3 个料框与共计 28 个绑定产品记录。")

if __name__ == '__main__':
    seed_demo_data()
