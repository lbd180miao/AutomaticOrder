import json
import tempfile
import threading
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, RequestFactory, override_settings
from django.conf import settings

from .adapters.plc import PLCAdapter, MemoryPLCTransport
from .plc_position_debug import step as position_step
from .plc_foam_debug import step as foam_step


class HeartbeatTests(SimpleTestCase):
    def test_parallel_bool_writes_preserve_same_byte_bits(self):
        class Transport(MemoryPLCTransport):
            def read(self, *args):
                value = super().read(*args)
                time.sleep(0.01)
                return value

        plc = PLCAdapter(Transport())
        gate = threading.Barrier(2)
        errors = []

        def write(name):
            try:
                gate.wait(timeout=2)
                plc.write_point(name, True)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(name,))
                   for name in ('mark_read_done', 'product_barcode_valid')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(plc.read_point('mark_read_done'))
        self.assertTrue(plc.read_point('product_barcode_valid'))

    def test_two_channels_share_one_heartbeat_schedule(self):
        plc = PLCAdapter(MemoryPLCTransport())
        with patch('time.time', return_value=100):
            position_step({'phase': 'WAIT_TRIGGER'}, plc, Mock())
            self.assertTrue(plc.read_point('heartbeat'))
            foam_step({'phase': 'WAIT_TRIGGER'}, plc, Mock())
            self.assertTrue(plc.read_point('heartbeat'))
        with patch('time.time', return_value=101):
            self.assertFalse(plc.tick_heartbeat())

    def test_new_connections_share_endpoint_timestamp_and_preserve_other_bits(self):
        class Transport(MemoryPLCTransport):
            address, tcp_port, rack, slot = 'test-endpoint', 102, 0, 1

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR, prefix='plc-test-') as directory, \
             override_settings(DATA_DIR=directory):
            first, second = Transport(), Transport()
            second.buffer = first.buffer
            a, b = PLCAdapter(first, heartbeat_interval=2), PLCAdapter(second, heartbeat_interval=2)
            a.write_point('mark_read_done', True)
            with patch('time.time', return_value=100):
                self.assertTrue(a.tick_heartbeat())
                self.assertTrue(b.tick_heartbeat())
            with patch('time.time', return_value=101):
                self.assertTrue(b.tick_heartbeat())
            with patch('time.time', return_value=102):
                self.assertFalse(b.tick_heartbeat())
            self.assertTrue(a.read_point('mark_read_done'))

    def test_heartbeat_continues_while_capture_blocks(self):
        second_heartbeat = threading.Event()

        class Transport(MemoryPLCTransport):
            heartbeats = 0

            def write(self, db_number, offset, data):
                super().write(db_number, offset, data)
                if offset == 48:
                    self.heartbeats += 1
                    if self.heartbeats >= 2:
                        second_heartbeat.set()

        transport = Transport()
        plc = PLCAdapter(transport)
        plc.write_point('position_trigger', True)

        def capture(*_):
            self.assertTrue(second_heartbeat.wait(4), 'heartbeat stopped during capture')
            return {'is_success': False, 'error_message': 'test NG'}

        with plc.maintain_heartbeat():
            position_step({'phase': 'WAIT_TRIGGER', 'recipe_id': 1, 'layer_no': 1}, plc, capture)
        self.assertTrue(plc.read_point('position_done'))


class HandshakeRecoveryTests(SimpleTestCase):
    def test_retry_success_and_failure_results_without_recapture(self):
        for success in (True, False):
            with self.subTest(success=success):
                plc = PLCAdapter(MemoryPLCTransport())
                plc.write_point('position_trigger', True)
                state = {'phase': 'WAIT_TRIGGER', 'recipe_id': 1, 'layer_no': 1}
                result = {'is_success': success, 'error_message': 'camera NG',
                          **{f'compensation_{a}': i + 0.25
                             for i, a in enumerate(('x', 'y', 'z', 'x2', 'y2', 'z2'))}}
                capture = Mock(return_value=result)
                original = plc.write_point

                def fail(name, value):
                    if name == 'layer_delta_z2':
                        raise ConnectionError('temporary outage')
                    original(name, value)

                with patch.object(plc, 'write_point', side_effect=fail):
                    position_step(state, plc, capture)
                self.assertEqual(state['phase'], 'WRITE_PENDING')
                self.assertFalse(plc.read_point('position_done'))
                # Resume the persisted JSON state, as a new HTTP request would.
                state = json.loads(json.dumps(state))
                position_step(state, plc, capture)
                capture.assert_called_once()
                self.assertEqual(state['phase'], 'WAIT_RESET')
                self.assertTrue(plc.read_point('position_done'))
                self.assertEqual(plc.read_point('position_success'), success)
                self.assertEqual(plc.read_point('layer_delta_z2'), 5.25 if success else 999)
                self.assertEqual(state['count'], 1)

    def test_interrupted_capture_returns_failure_without_recapturing(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_trigger', True)
        capture = Mock()
        state = {'phase': 'CAPTURING'}
        position_step(state, plc, capture)
        capture.assert_not_called()
        self.assertTrue(plc.read_point('position_done'))
        self.assertFalse(plc.read_point('position_success'))
        self.assertEqual(plc.read_point('layer_delta_z2'), 999)

    def test_pending_session_survives_connection_failure(self):
        from .views import api_plc_position_debug
        state = {'token': 'test', 'mode': 'position', 'expires': 10**12,
                 'phase': 'WRITE_PENDING', 'pending_result': {'values': {}}}
        plc = Mock()
        plc.maintain_heartbeat.side_effect = ConnectionError('offline')
        request = RequestFactory().post('/', data=json.dumps({'action': 'poll', 'token': 'test'}),
                                        content_type='application/json')
        with patch('apps.devices.plc_position_debug.ownership', return_value=nullcontext((state, Mock()))), \
             patch('apps.devices.services.get_plc_adapter', return_value=plc):
            response = json.loads(api_plc_position_debug(request).content)
        self.assertTrue(response['success'])
        self.assertEqual(response['phase'], 'WRITE_PENDING')
        self.assertNotIn('stopped', response)

    def test_locked_station_reasserts_cleared_plc_lock(self):
        from apps.workflow.station_service import StationWorkflowService
        from apps.workflow.models import StationPhase
        service = object.__new__(StationWorkflowService)
        service.plc = PLCAdapter(MemoryPLCTransport())
        service.devices = Mock()
        service.plc_device_code = 'PLC-01'
        service._ensure_cycle = Mock(return_value=SimpleNamespace(phase=StationPhase.LOCKED))
        self.assertFalse(service.plc.read_snapshot()['workstation_locked'])
        service._poll_once_owned()
        self.assertTrue(service.plc.read_snapshot()['workstation_locked'])

    def test_foam_capture_exception_completes_with_false_result(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('foam_trigger', True)
        foam_step({'phase': 'WAIT_TRIGGER', 'recipe_id': 1}, plc,
                  Mock(side_effect=RuntimeError('camera error')))
        self.assertTrue(plc.read_point('foam_done'))
        self.assertFalse(plc.read_point('foam_passed'))


class CompensationWriterTests(SimpleTestCase):
    def setUp(self):
        from apps.vision.plc_writer_service import PLCCompensationWriter
        from apps.vision.compensation_calculator import CompensationData
        self.writer = PLCCompensationWriter()
        self.compensation = CompensationData(1, 2, 3, 0, 1, 1, 1, True)

    def test_missing_second_group_does_not_report_success_or_connect(self):
        with patch('apps.vision.plc_writer_service.get_plc_adapter') as factory, \
             patch.object(self.writer.logger, 'exception'):
            result = self.writer.write_compensation_to_plc(self.compensation, 1)
        self.assertFalse(result['success'])
        factory.assert_not_called()

    def test_writes_all_six_values_and_distinguishes_real_transport(self):
        # A fake transport deliberately not inheriting MemoryPLCTransport exercises
        # the production reporting/cleanup path without touching a physical PLC.
        class Transport:
            def __init__(self):
                self.memory = MemoryPLCTransport()
            def connect(self): return self.memory.connect()
            def disconnect(self): return self.memory.disconnect()
            def is_connected(self): return self.memory.is_connected()
            def read(self, *args): return self.memory.read(*args)
            def write(self, *args): return self.memory.write(*args)

        for transport, simulated in ((MemoryPLCTransport(), True), (Transport(), False)):
            with self.subTest(simulated=simulated):
                plc = PLCAdapter(transport)
                with patch('apps.vision.plc_writer_service.get_plc_adapter', return_value=plc), \
                     patch('apps.vision.plc_writer_service.ownership', return_value=nullcontext(({}, Mock()))):
                    result = self.writer.write_compensation_to_plc(
                        self.compensation, 1, second_group={'x': 4, 'y': 5, 'z': 6})
                self.assertTrue(result['success'])
                self.assertEqual(result['simulated'], simulated)
                if not simulated:
                    self.assertFalse(transport.is_connected())
                self.assertEqual([plc.read_point(f'layer_delta_{a}') for a in ('x','y','z','x2','y2','z2')],
                                 [1, 2, 3, 4, 5, 6])
                self.assertTrue(plc.read_point('position_done'))
                self.assertTrue(plc.read_point('position_success'))

    def test_writer_cannot_interfere_with_debug_session(self):
        with patch('apps.vision.plc_writer_service.get_plc_adapter') as factory, \
             patch('apps.vision.plc_writer_service.ownership',
                   return_value=nullcontext(({'expires': 10**12}, Mock()))), \
             patch.object(self.writer.logger, 'exception'):
            result = self.writer.write_compensation_to_plc(
                self.compensation, 1, second_group={'x': 4, 'y': 5, 'z': 6})
        self.assertFalse(result['success'])
        factory.assert_not_called()

    def test_partial_write_never_reports_completion(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_done', True)
        with patch('apps.vision.plc_writer_service.get_plc_adapter', return_value=plc), \
             patch('apps.vision.plc_writer_service.ownership', return_value=nullcontext(({}, Mock()))), \
             patch.object(plc, 'send_rack_offsets', side_effect=ConnectionError('write failed')), \
             patch.object(self.writer.logger, 'exception'):
            result = self.writer.write_compensation_to_plc(
                self.compensation, 1, second_group={'x': 4, 'y': 5, 'z': 6})
        self.assertFalse(result['success'])
        self.assertFalse(plc.read_point('position_done'))
        self.assertFalse(plc.read_point('position_success'))

    def test_write_status_uses_existing_json_field(self):
        from apps.vision.models import RackLocationResult
        record = RackLocationResult(result_data={'keep': True})
        with patch('apps.vision.plc_writer_service.RackLocationResult.objects.get', return_value=record), \
             patch.object(record, 'save') as save:
            self.writer._update_result_plc_status(1, 'WRITTEN', '', {'offset_z2': 6})
        self.assertEqual(record.plc_write_status, 'WRITTEN')
        self.assertTrue(record.result_data['keep'])
        self.assertIn('plc_written_at', record.result_data)
        for field in save.call_args.kwargs['update_fields']:
            RackLocationResult._meta.get_field(field)

    def test_status_api_and_history_order_accept_json_timestamp(self):
        from apps.vision.models import RackLocationResult
        from apps.vision.views_plc_writer import get_plc_write_status
        record = RackLocationResult(id=1, plc_write_status='WRITTEN',
                                    result_data={'plc_written_at': '2026-10-13T10:00:00+08:00'})
        with patch('apps.vision.models.RackLocationResult.objects.get', return_value=record):
            response = get_plc_write_status(RequestFactory().get('/', {'result_id': 1}))
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['plc_written_at'], record.result_data['plc_written_at'])
        # Compile without accessing the production database; a removed-field sort fails here.
        self.assertIn('plc_written_at', str(RackLocationResult.objects.order_by('-result_data__plc_written_at').query))

    def test_workbench_record_uses_robot_groups_without_legacy_compensation(self):
        recipe = SimpleNamespace(max_offset_x=100, max_offset_y=100, max_offset_z=100, max_offset_rz=10)
        groups = {name: {'coordinate_system': 'robot_base',
                         'translation_mm': dict(zip('xyz', values)), 'rotation_deg': {'rz': 0}}
                  for name, values in (('A', (1, 2, 3)), ('B', (4, 5, 6)))}
        record = SimpleNamespace(is_success=True, recipe=recipe, confidence=0.9,
                                 result_data={'robot_groups': groups}, layer_no=1,
                                 position_no=1, side='BOTH', recipe_id=1)
        with patch('apps.vision.plc_writer_service.RackLocationResult.objects.select_related') as query, \
             patch.object(self.writer, 'write_compensation_to_plc', return_value={'success': True}) as write:
            query.return_value.get.return_value = record
            self.assertTrue(self.writer.write_compensation_from_result(1)['success'])
        self.assertEqual(write.call_args.kwargs['second_group'], {'x': 4, 'y': 5, 'z': 6})
        self.assertEqual(write.call_args.kwargs['compensation'].compensation_x, 1)

    def test_batch_cannot_overwrite_several_layers_without_handshake(self):
        with patch('apps.vision.models.RackLocationRecipe.objects.get',
                   return_value=SimpleNamespace(layer_count=3)), \
             patch.object(self.writer, 'write_compensation_from_result') as write:
            result = self.writer.batch_write_compensations_for_recipe(1)
        self.assertFalse(result['success'])
        write.assert_not_called()
