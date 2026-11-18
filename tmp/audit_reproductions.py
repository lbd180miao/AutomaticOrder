from django.test import TestCase, SimpleTestCase, override_settings
from apps.production.models import Product, Rack
from apps.production.services import ProductionService
from apps.mes.services import get_mes_client
from apps.mes.client import SimulatedMesClient
from apps.vision.recipe_utils import foam_offset_config

class AuditReproductions(TestCase):
    def test_replacement_can_reuse_defective_barcode(self):
        rack = Rack.objects.create(rack_code='AUDIT-RACK')
        product = Product.objects.create(product_code='AUDIT-PRODUCT', rack=rack)
        result = ProductionService().mark_product_defective(product.pk, replacement_code=product.product_code)
        product.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(product.replaced_by_id, product.pk)
        self.assertEqual(product.rack_id, rack.pk)
        self.assertTrue(product.is_defective)

class AuditConfiguration(SimpleTestCase):
    @override_settings(MES_GATEWAY_ENABLED=False, AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES':False,'MES_BASE_URL':''})
    def test_missing_mes_url_returns_simulated_success(self):
        client = get_mes_client()
        self.assertIsInstance(client, SimulatedMesClient)
        self.assertTrue(client.upload_product_barcode('AUDIT-PRODUCT','AUDIT-RACK')['success'])

    def test_pixel_edit_cannot_change_existing_mm_limit(self):
        thresholds={'pixels_per_mm_x':12,'pixels_per_mm_y':12,'max_offset_x_mm':10,'max_offset_y_mm':10}
        thresholds.update(max_offset_x_px=1,max_offset_y_px=1)
        config=foam_offset_config(thresholds)
        self.assertEqual(config['max_offset_x_mm'],10)
        self.assertEqual(config['max_offset_y_mm'],10)
