from django.test import TestCase

from apps.core.constants import MesAction
from apps.mes.client import SimulatedMesClient
from apps.mes.models import MesRecord
from apps.mes.services import MesService


class MesServiceTests(TestCase):
    def test_get_recipe_success_records(self):
        service = MesService(client=SimulatedMesClient())
        resp = service.get_rack_recipe('RK-1')
        self.assertTrue(resp['success'])
        self.assertIn('recipe', resp)
        self.assertTrue(MesRecord.objects.filter(action=MesAction.GET_RACK_RECIPE, success=True).exists())

    def test_get_recipe_failure_records(self):
        client = SimulatedMesClient(fail_actions=[MesAction.GET_RACK_RECIPE])
        service = MesService(client=client)
        resp = service.get_rack_recipe('RK-1')
        self.assertFalse(resp['success'])
        rec = MesRecord.objects.get(action=MesAction.GET_RACK_RECIPE)
        self.assertFalse(rec.success)
        self.assertTrue(rec.error_message)

    def test_upload_barcode(self):
        service = MesService(client=SimulatedMesClient())
        resp = service.upload_product_barcode('P-1', 'RK-1')
        self.assertTrue(resp['success'])
