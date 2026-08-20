from django.test import TestCase

from apps.production.models import Product, Rack, RackRecipe, RackRecipeVisionMapping
from apps.production.rack_recipe_service import RackPositionResolver, validate_rack_recipe
from apps.production.services import ProductionService
from apps.vision.models import RackLocationRecipe


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


class RackRecipePositionResolverTests(TestCase):
    def setUp(self):
        self.recipe = RackRecipe.objects.create(
            recipe_code='RACK-MASTER-01',
            name='三层料架',
            rack_type='RACK-A',
            station_position_count=2,
            layer_count=3,
            quantity_per_layer=5,
            total_quantity=15,
            layer_height=120,
            layer_spacing=150,
        )

    def test_resolves_current_and_next_position_from_completed_quantity(self):
        result = RackPositionResolver(self.recipe).resolve(5, station_position_no=1)

        self.assertEqual(result['current']['layer_no'], 2)
        self.assertEqual(result['current']['slot_no'], 1)
        self.assertEqual(result['next']['slot_no'], 2)
        self.assertFalse(result['is_full'])

    def test_loading_direction_changes_layer_and_slot_order(self):
        self.recipe.loading_direction = RackRecipe.LoadingDirection.TOP_DOWN_RIGHT_LEFT
        self.recipe.save(update_fields=['loading_direction'])

        result = RackPositionResolver(self.recipe).resolve(0, station_position_no=2)

        self.assertEqual(result['current']['layer_no'], 3)
        self.assertEqual(result['current']['slot_no'], 5)

    def test_mapping_is_additive_and_selected_for_current_layer(self):
        vision_recipe = RackLocationRecipe.objects.create(
            recipe_name='P1-L2', rack_type='RACK-A', position_no=1, layer_no=2,
        )
        RackRecipeVisionMapping.objects.create(
            rack_recipe=self.recipe,
            station_position_no=1,
            layer_no=2,
            rack_location_recipe=vision_recipe,
        )

        result = RackPositionResolver(self.recipe).resolve(5, station_position_no=1)

        self.assertEqual(result['rack_location_recipe_id'], vision_recipe.id)
        self.assertEqual(RackRecipe.objects.count(), 1)
        self.assertEqual(RackLocationRecipe.objects.count(), 1)

    def test_validation_reports_unmapped_layers_without_creating_rows(self):
        result = validate_rack_recipe(self.recipe)

        self.assertFalse(result['valid'])
        self.assertEqual(result['mapping_total_count'], 6)
        self.assertEqual(RackRecipeVisionMapping.objects.count(), 0)
