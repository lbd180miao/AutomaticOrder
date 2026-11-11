from unittest.mock import Mock, patch

from django.test import TestCase

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.mes.client import SimulatedMesClient
from apps.mes.services import MesService
from apps.mes.remote_client import RemoteMesClient, RemotePending
from apps.production.models import Product, Rack
from .models import StationCycle, StationPhase
from .station_service import StationWorkflowService


class DB2ContractTests(TestCase):
    def setUp(self):
        self.plc = PLCAdapter(MemoryPLCTransport())
        self.client = SimulatedMesClient(recipe_overrides={'total_quantity': 2})
        self.mes = MesService(client=self.client)
        self.vision = Mock()
        self.vision.calculate_position_offsets.side_effect = self.calculate
        self.vision.inspect_foam.return_value = (True, None)
        self.service = StationWorkflowService(plc=self.plc, mes_service=self.mes,
            vision_gateway=self.vision, device_service=Mock(), alarm_service=Mock())

    def calculate(self, cycle, *, on_captured):
        self.assertFalse(self.plc.read_point('position_trigger'))
        on_captured()
        self.assertTrue(self.plc.read_point('position_done'))
        self.plc.write_point('position_done', False)
        return {'x': 1, 'y': 2, 'z': 3}

    def poll(self):
        cycle, _ = self.service._poll_once_owned()
        cycle.refresh_from_db()
        return cycle

    def rack(self):
        self.poll()
        self.plc.write_point('rack_barcode', 'INN010144')
        self.plc.write_point('rack_trigger', True)
        cycle = self.poll()
        self.assertFalse(self.plc.read_point('rack_trigger'))
        self.assertTrue(self.plc.read_point('rack_done'))
        self.assertEqual(self.plc.read_point('rack_type_code'), 1)
        self.assertEqual(self.poll().phase, StationPhase.WAIT_RACK_RESET)
        self.plc.write_point('rack_done', False)
        return self.poll()

    def product(self, code):
        self.plc.write_point('product_barcode', code)
        self.plc.write_point('mark_trigger', True)
        cycle = self.poll()
        self.assertFalse(self.plc.read_point('mark_trigger'))
        self.assertTrue(self.plc.read_point('product_mes_upload_done'))
        self.assertTrue(self.plc.read_point('product_mes_upload_success'))
        self.assertEqual(self.poll().phase, StationPhase.WAIT_MARK_RESET)
        self.plc.write_point('product_mes_upload_done', False)
        return self.poll()

    def test_complete_rack_with_repeat_position_and_plc_owned_ack(self):
        cycle = self.rack()
        self.assertEqual(cycle.phase, StationPhase.WAIT_PRODUCT)
        for code in ('PROD001', 'PROD002'):
            self.plc.write_point('position_trigger', True)
            cycle = self.poll()
            self.assertEqual(cycle.phase, StationPhase.WAIT_POSITION_RESET)
            self.assertFalse(self.plc.read_point('position_done'))
            self.assertTrue(self.plc.read_point('position_success'))
            self.assertEqual(self.plc.read_point('layer_delta_x2'), 0)
            self.assertEqual(self.poll().phase, StationPhase.WAIT_POSITION_RESET)
            self.plc.write_point('position_success', False)
            self.poll()
            self.product(code)
            self.plc.write_point('foam_trigger', True)
            self.assertEqual(self.poll().phase, StationPhase.WAIT_FOAM_RESET)
            self.assertFalse(self.plc.read_point('foam_trigger'))
            self.assertTrue(self.plc.read_point('foam_done'))
            self.assertEqual(self.poll().phase, StationPhase.WAIT_FOAM_RESET)
            self.plc.write_point('foam_done', False)
            self.poll()
        self.plc.write_point('boxing_trigger', True)
        cycle = self.poll()
        self.assertFalse(self.plc.read_point('boxing_trigger'))
        self.assertEqual(cycle.bin_code, 'SIM-INN010144')
        self.assertEqual(cycle.bound_product_codes, ['PROD001', 'PROD002'])
        self.assertEqual(cycle.loaded_quantity, 2)
        self.assertTrue(self.plc.read_point('mes_upload_success'))
        self.assertEqual(self.poll().phase, StationPhase.WAIT_BOXING_RESET)
        self.plc.write_point('mes_upload_done', False)
        self.assertEqual(self.poll().phase, StationPhase.COMPLETED)

    def test_remote_pending_uses_saved_barcode_after_restart(self):
        self.rack()
        remote = Mock(spec=RemoteMesClient)
        remote.upload_product_barcode.side_effect = [RemotePending('task'), {'success': True}]
        self.service.mes = MesService(client=remote)
        self.plc.write_point('product_barcode', 'PROD001')
        self.plc.write_point('mark_trigger', True)
        cycle = self.poll()
        self.assertFalse(self.plc.read_point('mark_trigger'))
        self.assertFalse(self.plc.read_point('product_mes_upload_done'))
        self.plc.write_point('product_barcode', 'OVERWRITTEN')
        self.service = StationWorkflowService(plc=self.plc, mes_service=MesService(client=remote),
            vision_gateway=self.vision, device_service=Mock(), alarm_service=Mock())
        cycle = self.poll()
        self.assertEqual(cycle.bound_product_codes, ['PROD001'])
        self.assertEqual(remote.upload_product_barcode.call_args.args, ('PROD001', 'INN010144'))
        self.assertFalse(Product.objects.filter(product_code='OVERWRITTEN').exists())

    def test_seal_failure_does_not_complete_cycle(self):
        self.rack()
        self.product('PROD001')
        self.client.fail_actions.add('UPLOAD_BOXING_RESULT')
        self.plc.write_point('boxing_trigger', True)
        cycle = self.poll()
        self.assertEqual(cycle.phase, StationPhase.LOCKED)
        self.assertTrue(self.plc.read_point('mes_upload_done'))
        self.assertFalse(self.plc.read_point('mes_upload_success'))
        self.assertIsNone(cycle.finished_at)

    def test_local_seal_save_failure_recovers_without_another_mes_call(self):
        self.rack()
        self.product('PROD001')
        original_save = StationCycle.save

        def fail_bin(instance, *args, **kwargs):
            if 'bin_code' in kwargs.get('update_fields', ()):
                raise RuntimeError('disk error')
            return original_save(instance, *args, **kwargs)

        self.plc.write_point('boxing_trigger', True)
        with patch.object(self.client, 'upload_boxing_result', wraps=self.client.upload_boxing_result) as upload:
            with patch.object(StationCycle, 'save', fail_bin):
                cycle = self.poll()
            self.assertEqual(cycle.phase, StationPhase.LOCKED)
            self.assertEqual(cycle.bin_code, '')
            self.assertTrue(cycle.io_state['pending']['response']['success'])
            self.plc.write_point('mes_upload_done', False)
            self.service.unlock(cycle)
            cycle = self.poll()
            self.assertEqual(cycle.bin_code, 'SIM-INN010144')
            self.assertEqual(cycle.phase, StationPhase.WAIT_BOXING_RESET)
            upload.assert_called_once()

    def test_bound_rack_clears_current_links_and_keeps_history(self):
        rack = Rack.objects.create(rack_code='INN010144')
        old = Product.objects.create(product_code='OLD001', rack=rack)
        history = StationCycle.objects.create(rack=rack, phase=StationPhase.COMPLETED,
            bin_code='OLD-BIN', bound_product_codes=['OLD001'])
        original = self.client.get_rack_recipe
        self.client.get_rack_recipe = lambda code: {**original(code), 'hu_qty': 1}
        cycle = self.rack()
        old.refresh_from_db()
        history.refresh_from_db()
        self.assertIsNone(old.rack_id)
        self.assertEqual(history.bin_code, 'OLD-BIN')
        self.assertEqual(history.bound_product_codes, ['OLD001'])
        self.assertEqual(cycle.bin_code, '')

    def test_product_validation_failure_returns_final_failure(self):
        self.rack()
        self.plc.write_point('product_barcode', '')
        self.plc.write_point('mark_trigger', True)
        cycle = self.poll()
        self.assertEqual(cycle.phase, StationPhase.LOCKED)
        self.assertFalse(self.plc.read_point('mark_trigger'))
        self.assertTrue(self.plc.read_point('product_mes_upload_done'))
        self.assertFalse(self.plc.read_point('product_mes_upload_success'))

    def test_failed_product_does_not_allow_sealing(self):
        self.rack()
        self.client.fail_actions.add('UPLOAD_PRODUCT_BARCODE')
        self.plc.write_point('product_barcode', 'PROD001')
        self.plc.write_point('mark_trigger', True)
        cycle = self.poll()
        self.assertEqual(cycle.phase, StationPhase.LOCKED)
        self.assertEqual(cycle.bound_product_codes, [])
        self.assertTrue(self.plc.read_point('product_mes_upload_done'))
        self.plc.write_point('boxing_trigger', True)
        with patch.object(self.client, 'upload_boxing_result') as upload:
            self.poll()
            upload.assert_not_called()

    def test_unknown_seal_outcome_is_not_automatically_resent(self):
        self.rack()
        self.product('PROD001')
        self.plc.write_point('boxing_trigger', True)
        with patch.object(self.client, 'upload_boxing_result', side_effect=TimeoutError('connection lost')) as upload:
            cycle = self.poll()
            self.assertEqual(cycle.phase, StationPhase.LOCKED)
            self.plc.write_point('mes_upload_done', False)
            self.service.unlock(cycle)
            cycle = self.poll()
            self.assertEqual(cycle.phase, StationPhase.LOCKED)
            self.assertIn('禁止自动重复提交', cycle.last_error)
            upload.assert_called_once()

    def test_next_scan_waits_for_plc_ack_and_preserves_new_trigger(self):
        self.rack()
        self.plc.write_point('product_barcode', 'PROD001')
        self.plc.write_point('mark_trigger', True)
        self.poll()
        self.plc.write_point('product_barcode', 'PROD002')
        self.plc.write_point('mark_trigger', True)
        self.assertEqual(self.poll().phase, StationPhase.WAIT_MARK_RESET)
        self.assertFalse(Product.objects.filter(product_code='PROD002').exists())
        self.assertTrue(self.plc.read_point('mark_trigger'))
        self.plc.write_point('product_mes_upload_done', False)
        self.poll()
        cycle = self.poll()
        self.assertEqual(cycle.bound_product_codes, ['PROD001', 'PROD002'])
