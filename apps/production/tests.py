from django.test import TestCase

from apps.production.models import Product, Rack, RackRecipe
from apps.production.services import ProductionService


class ProductionServiceTests(TestCase):
    def setUp(self):
        self.service = ProductionService()

    def test_create_product(self):
        p = self.service.create_product('P-001')
        self.assertIsInstance(p, Product)
        self.assertEqual(p.product_code, 'P-001')

    def test_get_or_create_rack_idempotent(self):
        r1 = self.service.get_or_create_rack('RK-1')
        r2 = self.service.get_or_create_rack('RK-1')
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(Rack.objects.count(), 1)

    def test_bind_product_to_rack(self):
        p = self.service.create_product('P-002')
        r = self.service.get_or_create_rack('RK-2')
        self.service.bind_product_to_rack(p, r)
        p.refresh_from_db()
        self.assertEqual(p.rack_id, r.pk)

    def test_upsert_recipe(self):
        recipe = self.service.upsert_recipe(
            'RCP-1', name='测试', rack_type='STD', layer_count=4,
            quantity_per_layer=6, total_quantity=24, layer_height=120,
            layer_spacing=150, tolerance_x=2, tolerance_y=2, tolerance_z=3,
        )
        self.assertIsInstance(recipe, RackRecipe)
        # 再次 upsert 更新而非新建。
        self.service.upsert_recipe('RCP-1', name='更新', rack_type='STD', layer_count=5,
                                   quantity_per_layer=6, total_quantity=30, layer_height=120,
                                   layer_spacing=150, tolerance_x=2, tolerance_y=2, tolerance_z=3)
        self.assertEqual(RackRecipe.objects.count(), 1)
