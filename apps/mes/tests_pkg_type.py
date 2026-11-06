from unittest.mock import Mock

from django.test import TestCase

from apps.production.models import Rack, RackRecipe
from apps.production.services import ProductionService
from .models import MesRecord, PkgTypeMapping
from .services import MesService
from .yfpo_soap_client import YfpoSoapMesClient


class PkgTypeTests(TestCase):
    def setUp(self):
        self.client = YfpoSoapMesClient('http://example.invalid/service', 'F', 'L')
        self.client._invoke = Mock(return_value={'success': True, 'mes_data': {
            'RackStatus': 1, 'IsSealed': False, 'PkgTypeCode': '31231321'}})
        self.service = MesService(client=self.client)

    def test_seed_and_raw_response(self):
        self.assertEqual(PkgTypeMapping.objects.count(), 16)
        response = self.service.get_rack_recipe('RK1')
        self.assertTrue(response['success'])
        self.assertEqual(response['rack_type'], '三层')
        self.assertEqual(response['mes_data']['PkgTypeCode'], '31231321')
        self.assertEqual(MesRecord.objects.get().response_payload['pkg_type_code'], '31231321')

    def test_unknown_missing_disabled_and_retry(self):
        for code in ('unknown', None, ''):
            self.client._invoke.return_value['mes_data']['PkgTypeCode'] = code
            self.assertFalse(self.service.get_rack_recipe('RK1')['success'])
        self.client._invoke.return_value['mes_data'].pop('PkgTypeCode')
        self.assertFalse(self.service.get_rack_recipe('RK1')['success'])
        self.client._invoke.return_value['mes_data']['PkgTypeCode'] = '31231321'
        PkgTypeMapping.objects.filter(pkg_type_code='31231321').update(enabled=False)
        self.assertFalse(self.service.get_rack_recipe('RK1')['success'])
        record = MesRecord.objects.latest('pk')
        PkgTypeMapping.objects.filter(pkg_type_code='31231321').update(enabled=True)
        self.assertEqual(self.service.retry_record(record.pk)['rack_type'], '三层')

    def test_all_types_and_live_configuration(self):
        for code, rack_type in [('8888812312', '两层'), ('31231322', '三层'), ('00005', '五层')]:
            PkgTypeMapping.objects.update_or_create(pkg_type_code=code, defaults={'rack_type': rack_type})
            self.client._invoke.return_value['mes_data']['PkgTypeCode'] = code
            self.assertEqual(self.service.get_rack_recipe('RK1')['rack_type'], rack_type)
        PkgTypeMapping.objects.filter(pkg_type_code='00005').update(rack_type='两层')
        self.assertEqual(self.service.get_rack_recipe('RK1')['rack_type'], '两层')

    def test_recipe_selection_replaces_stale_binding_and_rejects_ambiguity(self):
        old = RackRecipe.objects.create(recipe_code='OLD', rack_type='两层', layer_count=2)
        rack = Rack.objects.create(rack_code='RK1', current_recipe=old, rack_type='两层')
        service = ProductionService()
        response = self.service.get_rack_recipe('RK1')
        self.assertIsNone(service.sync_recipe_from_mes(rack, response))
        rack.refresh_from_db()
        self.assertIsNone(rack.current_recipe)
        self.assertEqual(rack.rack_type, '三层')
        correct = RackRecipe.objects.create(recipe_code='THREE', rack_type='三层', layer_count=3)
        self.assertEqual(service.sync_recipe_from_mes(rack, response), correct)
        correct.is_active = False
        correct.save()
        self.assertIsNone(service.sync_recipe_from_mes(rack, response))
        for code in ('A', 'B'):
            RackRecipe.objects.create(recipe_code=code, rack_type='三层', layer_count=3)
        self.assertIsNone(service.sync_recipe_from_mes(rack, response))

    def test_following_interfaces_keep_original_contract(self):
        self.client._invoke.return_value = {'success': True, 'mes_data': {'BinCode': 'BIN'}}
        self.service.upload_product_barcode('PRODUCT', 'RK1')
        self.client._invoke.assert_called_with('20260802', {'RackCode': 'RK1', 'Barcode': 'PRODUCT'})
        response = self.service.upload_boxing_result({'rack_code': 'RK1'})
        self.client._invoke.assert_called_with('20260803', {'RackCode': 'RK1'})
        self.assertEqual(response['bin_code'], 'BIN')
