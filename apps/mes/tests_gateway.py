import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from . import remote_client


class OutboxTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(DATA_DIR=Path(self.temp.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        Path(self.temp.name, 'agv_gateway.json').write_text(json.dumps({
            'gateway_url': 'http://127.0.0.1:18000', 'token': 'test-token'}))
        self.worker = patch.object(remote_client, 'start_worker')
        self.worker.start()
        self.addCleanup(self.worker.stop)

    def test_submission_is_durable_and_identity_is_stable(self):
        one = remote_client.submit('SELF_TEST', {}, 'key')
        two = remote_client.submit('SELF_TEST', {}, 'key')
        self.assertEqual(one, two)
        self.assertEqual(remote_client.result(one)['gateway_state'], 'pending')
        self.assertEqual(len(remote_client.rows()), 1)

    def test_manual_arrival_creates_read_only_real_mes_task(self):
        response = self.client.post('/mes/gateway/test/', data=json.dumps({
            'mode':'rack_query','rack_code':'RACK001'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        row=remote_client.rows()[0]
        self.assertEqual(row['action'], 'GET_RACK_RECIPE')
        self.assertEqual(json.loads(row['payload'])['rack_code'], 'RACK001')
        from apps.production.models import Rack
        self.assertEqual(Rack.objects.count(), 0)
        response = self.client.post('/mes/gateway/test/', data=json.dumps({
            'mode':'rack_query','rack_code':''}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_disconnect_retains_task_and_reconnect_uses_same_id(self):
        task_id = remote_client.submit('SELF_TEST', {})
        with patch.object(remote_client.requests, 'Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.post.side_effect = ConnectionError('offline')
            remote_client.deliver_once()
            self.assertEqual(remote_client.result(task_id)['gateway_state'], 'pending')
            session.post.side_effect = None
            response = Mock()
            response.json.return_value = {'id': task_id, 'state': 'succeeded', 'result': {'success': True}}
            session.post.return_value = response
            remote_client.deliver_once()
            self.assertTrue(remote_client.result(task_id)['success'])
            self.assertEqual(session.post.call_args.kwargs['json']['id'], task_id)

    def test_bad_gateway_response_does_not_mark_success(self):
        task_id = remote_client.submit('SELF_TEST', {})
        with patch.object(remote_client.requests, 'Session') as factory:
            factory.return_value.__enter__.return_value.post.return_value.json.return_value = {
                'id': 'wrong', 'state': 'succeeded', 'result': {'success': True}}
            remote_client.deliver_once()
        self.assertFalse(remote_client.result(task_id)['success'])

    def test_nonblocking_call_yields_scan_with_saved_task(self):
        client = remote_client.RemoteMesClient()
        client.nonblocking = True
        client.context_cycle = 1
        with self.assertRaises(remote_client.RemotePending):
            client.get_rack_recipe('R1')
        with self.assertRaises(remote_client.RemotePending):
            client.get_rack_recipe('R1')
        self.assertEqual(len(remote_client.rows()), 1)

    def test_plc_scans_resume_same_product_after_remote_completion(self):
        from django.utils import timezone
        from apps.production.models import Rack, RackRecipe, Product
        from apps.workflow.models import StationCycle, StationPhase
        from apps.workflow.station_service import StationWorkflowService
        from apps.mes.services import MesService
        recipe = RackRecipe.objects.create(recipe_code='TEST', name='test', rack_type='test')
        rack = Rack.objects.create(rack_code='RACK001', current_recipe=recipe)
        cycle = StationCycle.objects.create(rack=rack, phase=StationPhase.WAIT_PRODUCT, started_at=timezone.now(),
            io_state={'listener_inputs': {'rack_barcode': 'RACK001', 'rack_barcode_round': 'round-1'}})
        plc = Mock()
        plc.read_point.return_value = False
        plc.tick_heartbeat.return_value = True
        sample = {'rack_working': False, 'product_barcode': 'PROD001', 'rack_barcode': 'RACK001'}
        plc.read_listener_snapshot.side_effect = lambda: dict(sample)
        service = StationWorkflowService(plc=plc, mes_service=MesService(remote_client.RemoteMesClient()),
                                         device_service=Mock())
        service._poll_once_owned()  # establish the low baseline
        sample['rack_working'] = True
        for _ in range(2):
            _, changed = service._poll_once_owned()
            self.assertFalse(changed)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(len(remote_client.rows()), 1)
        task = remote_client.rows()[0]
        with remote_client.database() as db:
            db.execute("UPDATE tasks SET state='succeeded', result=? WHERE id=?", ('{"success": true}', task['id']))
        _, changed = service._poll_once_owned()
        self.assertTrue(changed)
        cycle.refresh_from_db()
        self.assertEqual(cycle.phase, StationPhase.WAIT_RACK)
        self.assertEqual(Product.objects.count(), 1)
        plc.tick_heartbeat.assert_not_called()
        sample['rack_working'] = False
        service._poll_once_owned()
        sample['rack_working'] = True
        service._poll_once_owned()
        self.assertEqual(len(remote_client.rows()), 1)
