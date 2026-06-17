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
