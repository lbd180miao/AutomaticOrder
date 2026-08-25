import json

from django.test import TestCase
from django.urls import reverse

from .models import FoamProductLayout, FoamRackSpec, VisionRecipe
from .views_foam_profile import ensure_default_foam_profiles


class FoamRecipeStructureTests(TestCase):
    def setUp(self):
        self.layout = ensure_default_foam_profiles()

    def test_default_structure_preserves_and_links_legacy_recipes(self):
        legacy = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='旧配方',
            pos=7,
            roi_config={'leftFoamROI': {'x': 1}},
        )

        ensure_default_foam_profiles()

        legacy.refresh_from_db()
        self.assertEqual(legacy.foam_product_layout_id, self.layout.id)
        self.assertEqual(legacy.rack_type, 'RACK-3L')
        self.assertEqual(legacy.product_code, 'PROD-A')

    def test_rack_and_product_crud_builds_capacity(self):
        rack_response = self.client.post(
            reverse('vision:api_foam_rack_specs'),
            data=json.dumps({'name': '五层料架', 'rack_type': 'RACK-5L', 'layer_count': 5}),
            content_type='application/json',
        )
        self.assertEqual(rack_response.status_code, 201)
        rack_id = rack_response.json()['rack_spec']['id']

        product_response = self.client.post(
            reverse('vision:api_foam_product_layouts', args=[rack_id]),
            data=json.dumps({'product_code': 'PROD-X', 'product_name': 'X 产品', 'qty_per_layer': 6}),
            content_type='application/json',
        )
        self.assertEqual(product_response.status_code, 201)
        product = product_response.json()['product_layout']
        self.assertEqual(product['total_positions'], 30)

        updated = self.client.patch(
            reverse('vision:api_foam_product_layout_detail', args=[product['id']]),
            data=json.dumps({'qty_per_layer': 4}),
            content_type='application/json',
        )
        self.assertEqual(updated.json()['product_layout']['total_positions'], 20)

    def test_copy_recipe_across_products_creates_independent_recipe(self):
        source = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='A 产品源配方',
            foam_product_layout=self.layout,
            rack_type=self.layout.rack_spec.rack_type,
            product_code=self.layout.product_code,
            pos=0,
            roi_config={'leftFoamROI': {'x': 10}, 'rightFoamROI': {'x': 20}},
            threshold_config={'minCoverage': 0.73},
            algorithm_config={'mode': 'template'},
            standard_template_config={'sides': {'left': {'path': 'left.png'}}},
        )
        target = FoamProductLayout.objects.create(
            rack_spec=self.layout.rack_spec,
            product_code='PROD-B',
            product_name='B 产品',
            qty_per_layer=4,
        )

        response = self.client.post(
            reverse('vision:api_foam_recipe_create'),
            data=json.dumps({
                'name': 'B 产品复制配方',
                'layout_id': target.id,
                'pos': 5,
                'source_recipe_id': source.id,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        copied = VisionRecipe.objects.get(pk=response.json()['recipe']['id'])
        self.assertNotEqual(copied.id, source.id)
        self.assertEqual(copied.foam_product_layout_id, target.id)
        self.assertEqual(copied.product_code, 'PROD-B')
        self.assertEqual(copied.roi_config, source.roi_config)
        self.assertEqual(copied.threshold_config, source.threshold_config)
        self.assertEqual(copied.algorithm_config, source.algorithm_config)
        self.assertEqual(copied.standard_template_config, source.standard_template_config)

    def test_capacity_reduction_keeps_overflow_recipe(self):
        overflow = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name='必须保留的 POS 4',
            foam_product_layout=self.layout,
            rack_type=self.layout.rack_spec.rack_type,
            product_code=self.layout.product_code,
            pos=4,
            is_active=True,
        )
        response = self.client.patch(
            reverse('vision:api_foam_product_layout_detail', args=[self.layout.id]),
            data=json.dumps({'qty_per_layer': 1}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['product_layout']['total_positions'], 3)

        matrix = self.client.get(reverse('vision:api_foam_layout_recipes', args=[self.layout.id])).json()
        self.assertEqual(matrix['layout']['overflow_count'], 1)
        self.assertEqual(matrix['overflow_recipes'][0]['id'], overflow.id)
        self.assertTrue(VisionRecipe.objects.filter(pk=overflow.id).exists())

    def test_recipe_list_can_be_scoped_to_selected_product_layout(self):
        other = FoamProductLayout.objects.create(
            rack_spec=self.layout.rack_spec,
            product_code='PROD-C',
            product_name='C 产品',
            qty_per_layer=2,
        )
        selected = VisionRecipe.objects.create(
            recipe_type='FOAM_2D', name='C 配方', foam_product_layout=other,
            rack_type=other.rack_spec.rack_type, product_code=other.product_code, pos=0,
        )
        VisionRecipe.objects.create(
            recipe_type='FOAM_2D', name='A 配方', foam_product_layout=self.layout,
            rack_type=self.layout.rack_spec.rack_type, product_code=self.layout.product_code, pos=0,
        )

        response = self.client.get(
            reverse('vision:api_vision_recipes'),
            {'recipe_type': 'FOAM_2D', 'layout_id': other.id},
        )
        ids = [item['id'] for item in response.json()['recipes']]
        self.assertEqual(ids, [selected.id])


class FoamRecipePageTests(TestCase):
    def test_management_and_workbench_pages_render(self):
        self.assertContains(self.client.get(reverse('vision:recipe_management')), 'foam-rack-profile-list')
        self.assertContains(self.client.get(reverse('vision:foam_inspector_interactive')), 'foam-recipe-select')
