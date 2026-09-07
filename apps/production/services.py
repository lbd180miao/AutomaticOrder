"""生产数据服务：产品、料框、配方、批次的创建与绑定。"""
from django.db import transaction

from .models import Product, ProductionBatch, Rack, RackRecipe


class ProductionService:
    """Coordinates product, rack, and recipe records."""

    @transaction.atomic
    def create_product(self, product_code, batch=None, rack=None):
        product, _ = Product.objects.get_or_create(
            product_code=product_code,
            defaults={'batch': batch, 'rack': rack},
        )
        return product

    @transaction.atomic
    def get_or_create_rack(self, rack_code, rack_type='', position_side=''):
        rack, _ = Rack.objects.get_or_create(
            rack_code=rack_code,
            defaults={'rack_type': rack_type, 'position_side': position_side},
        )
        return rack

    @transaction.atomic
    def bind_product_to_rack(self, product, rack):
        """建立单件产品与料框的绑定关系。"""
        product.rack = rack
        product.save(update_fields=['rack', 'updated_at'])
        return product

    @transaction.atomic
    def upsert_recipe(self, recipe_code, **fields):
        """根据 MES 返回的配方数据创建或更新本地 RackRecipe。"""
        recipe, _ = RackRecipe.objects.update_or_create(
            recipe_code=recipe_code,
            defaults=fields,
        )
        return recipe

    @transaction.atomic
    def assign_recipe_to_rack(self, rack, recipe):
        rack.current_recipe = recipe
        if recipe and recipe.rack_type and not rack.rack_type:
            rack.rack_type = recipe.rack_type
        rack.save(update_fields=['current_recipe', 'rack_type', 'updated_at'])
        return rack

    def open_batch(self, batch_no, product_type=''):
        batch, _ = ProductionBatch.objects.get_or_create(
            batch_no=batch_no,
            defaults={'product_type': product_type},
        )
        return batch

    @transaction.atomic
    def update_or_create_rack_manual(self, rack_code: str, rack_id: int = None, sync_cycle: bool = True):
        """【新功能 1】：手动输入或修改料框码，执行三维校验并同步 MES 配方与当前工位。"""
        from apps.core.barcode_validator import validate_rack_barcode
        from apps.mes.services import MesService
        from apps.workflow.models import StationCycle, StationPhase

        val_res = validate_rack_barcode(rack_code, current_rack_id=rack_id, check_db_duplicate=True)
        cleaned_code = val_res.raise_if_invalid()

        if rack_id:
            rack = Rack.objects.get(pk=rack_id)
            if rack.rack_code != cleaned_code:
                conflict = Rack.objects.filter(rack_code=cleaned_code).exclude(pk=rack_id).first()
                if conflict:
                    rack = conflict
                else:
                    rack.rack_code = cleaned_code
                    rack.save(update_fields=['rack_code', 'updated_at'])
        else:
            rack, _ = Rack.objects.get_or_create(rack_code=cleaned_code)

        # 自动向 MES 获取装箱配方
        mes_svc = MesService()
        recipe_resp = mes_svc.get_rack_recipe(cleaned_code, rack=rack)
        if recipe_resp.get('success') and recipe_resp.get('recipe'):
            r_data = recipe_resp['recipe']
            recipe = self.upsert_recipe(
                r_data.get('recipe_code', f'RCP-{cleaned_code}'),
                name=r_data.get('name', f'{cleaned_code} 配方'),
                rack_type=r_data.get('rack_type', ''),
                layer_count=r_data.get('layer_count', 4),
                quantity_per_layer=r_data.get('quantity_per_layer', 6),
                total_quantity=r_data.get('total_quantity', 24),
                layer_height=r_data.get('layer_height', 120),
                layer_spacing=r_data.get('layer_spacing', 150),
                tolerance_x=r_data.get('tolerance_x', 0),
                tolerance_y=r_data.get('tolerance_y', 0),
                tolerance_z=r_data.get('tolerance_z', 3.0),
            )
            self.assign_recipe_to_rack(rack, recipe)

        # 同步更新当前活跃工位周期
        if sync_cycle:
            active_cycle = StationCycle.objects.exclude(phase=StationPhase.COMPLETED).order_by('-created_at').first()
            if active_cycle:
                active_cycle.rack = rack
                active_cycle.save(update_fields=['rack', 'updated_at'])

        return rack

    @transaction.atomic
    def mark_product_defective(
        self,
        product_id_or_code,
        defect_reason: str = '残次品人工剔除',
        replacement_code: str = None,
        rack_code: str = None,
    ):
        """
        【新功能 2】：标记产品为残次品/报废，从当前料框槽位中解绑；
        若提供了替换条码 replacement_code，则校验新条码并生成合格品补充绑定到原料框。
        """
        from apps.core.barcode_validator import validate_product_barcode
        from apps.core.constants import WorkflowState
        from django.utils import timezone

        if isinstance(product_id_or_code, int) or str(product_id_or_code).isdigit():
            product = Product.objects.get(pk=int(product_id_or_code))
        else:
            product = Product.objects.get(product_code=str(product_id_or_code).strip())

        orig_rack = product.rack
        target_rack_code = rack_code or (orig_rack.rack_code if orig_rack else None)

        # 1. 标记当前产品为残次品并解绑
        product.is_defective = True
        product.defect_reason = defect_reason or '残次品人工剔除'
        product.defect_at = timezone.now()
        product.current_state = WorkflowState.DEFECTIVE
        product.rack = None
        product.save(update_fields=[
            'is_defective', 'defect_reason', 'defect_at', 'current_state',
            'rack', 'bound_at', 'updated_at',
        ])

        # 2. 如果提供了替换条码，执行替换
        new_product = None
        if replacement_code and str(replacement_code).strip():
            rep_code_clean = str(replacement_code).strip()
            val_res = validate_product_barcode(
                rep_code_clean,
                rack_code=target_rack_code,
                current_product_id=product.pk,
                check_db_duplicate=True,
            )
            val_res.raise_if_invalid()

            target_rack = None
            if target_rack_code:
                target_rack, _ = Rack.objects.get_or_create(rack_code=target_rack_code)
            elif orig_rack:
                target_rack = orig_rack

            new_product, _ = Product.objects.get_or_create(
                product_code=rep_code_clean,
                defaults={'batch': product.batch, 'rack': target_rack},
            )
            if new_product.rack != target_rack:
                new_product.rack = target_rack
                new_product.save(update_fields=['rack', 'updated_at'])

            product.replaced_by = new_product
            product.save(update_fields=['replaced_by', 'updated_at'])

        return {
            'success': True,
            'defective_product': product,
            'replacement_product': new_product,
            'message': f'产品 {product.product_code} 已标记为残次品' + (f'，并由新合格品 {new_product.product_code} 替换绑定' if new_product else '并已从料框中移除'),
        }

    @transaction.atomic
    def update_product_barcode_manual(self, product_id: int, new_product_code: str, rack_code: str = None):
        """【新功能 2】：手动修改产品条码，执行严密三维校验。"""
        from apps.core.barcode_validator import validate_product_barcode

        product = Product.objects.get(pk=product_id)
        current_rack_code = rack_code or (product.rack.rack_code if product.rack else None)

        val_res = validate_product_barcode(
            new_product_code,
            rack_code=current_rack_code,
            current_product_id=product_id,
            check_db_duplicate=True,
        )
        cleaned_code = val_res.raise_if_invalid()

        old_code = product.product_code
        product.product_code = cleaned_code
        product.save(update_fields=['product_code', 'updated_at'])
        return {
            'success': True,
            'product': product,
            'message': f'产品条码已由 {old_code} 更新为 {cleaned_code}',
        }

