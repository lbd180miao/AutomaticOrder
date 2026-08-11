
from django.test import TestCase
from django.urls import reverse

from apps.production.models import Product, ProductionBatch, Rack, RackRecipe


class TraceabilityViewTests(TestCase):
    def setUp(self):
        recipe = RackRecipe.objects.create(
            recipe_code='TRACE-RCP', name='追溯配方', rack_type='STANDARD',
        )
        rack = Rack.objects.create(
            rack_code='TRACE-RACK', current_recipe=recipe, status='IN_USE',
        )
        batch = ProductionBatch.objects.create(
            batch_no='TRACE-BATCH', product_type='保险杠',
        )
        self.product = Product.objects.create(
            product_code='TRACE-PRODUCT', rack=rack, batch=batch,
        )

    def test_product_search_links_to_detail(self):
        response = self.client.get(reverse('traceability:search'), {
            'mode': 'product', 'q': self.product.product_code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.product_code)
        self.assertContains(response, reverse(
            'traceability:product_detail', args=[self.product.product_code],
        ))

    def test_rack_search_lists_bound_products(self):
        response = self.client.get(reverse('traceability:search'), {
            'mode': 'rack', 'q': self.product.rack.rack_code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TRACE-RACK')
        self.assertContains(response, self.product.product_code)

    def test_product_detail_displays_trace_sections(self):
        response = self.client.get(reverse(
            'traceability:product_detail', args=[self.product.product_code],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '产品全流程追溯')
        self.assertContains(response, '流程事件')
        self.assertContains(response, '3D 料架定位')
        self.assertContains(response, 'MES 通讯记录')
