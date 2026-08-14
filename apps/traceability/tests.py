
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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

    def test_time_range_filters_recent_records(self):
        old_product = Product.objects.create(product_code='TRACE-OLD-PRODUCT')
        Product.objects.filter(pk=old_product.pk).update(
            created_at=timezone.now() - timedelta(days=40),
        )
        today = timezone.localdate().isoformat()

        response = self.client.get(reverse('traceability:search'), {
            'start_date': today,
            'end_date': today,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.product_code)
        self.assertNotContains(response, old_product.product_code)
        self.assertEqual(response.context['record_stats']['total_products'], 1)
        self.assertTrue(response.context['time_filter_active'])

    def test_invalid_time_range_shows_message(self):
        response = self.client.get(reverse('traceability:search'), {
            'start_date': '2026-08-14',
            'end_date': '2026-08-01',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '开始日期不能晚于结束日期')
