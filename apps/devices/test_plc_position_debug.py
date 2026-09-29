import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings, RequestFactory

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.devices.plc_position_debug import step, ownership, DebugBusy, capture_position


class PositionHandshakeTests(SimpleTestCase):
    def setUp(self):
        self.plc = PLCAdapter(transport=MemoryPLCTransport())
        self.plc.connect()
        self.state = {'phase': 'ARMING', 'recipe_id': 7, 'layer_no': 2}
        self.capture = Mock(return_value={
            'is_success': True, 'compensation_x': 1.25,
            'compensation_y': -2.5, 'compensation_z': 3.75, 'result_id': 12,
        })

    def scan(self):
        step(self.state, self.plc, self.capture)

    def test_start_high_waits_for_low_then_one_capture_per_trigger(self):
        self.plc.write_point('position_trigger', True)
        self.scan()
        self.capture.assert_not_called()
        self.plc.write_point('position_trigger', False)
        self.scan()
        self.plc.write_point('boxing_allowed', True)
        self.plc.write_point('position_trigger', True)
        writes = []
        original = self.plc.write_point
        def record(name, value):
            writes.append((name, value))
            original(name, value)
        with patch.object(self.plc, 'write_point', side_effect=record):
            self.scan()
        self.assertEqual(writes[-2:], [('position_success', True), ('position_done', True)])
        self.assertEqual(self.state['values'], {'x': 1.25, 'y': -2.5, 'z': 3.75})
        self.assertTrue(self.plc.read_point('boxing_allowed'))
        self.scan()
        self.capture.assert_called_once_with(7, 2)
        self.plc.write_point('position_trigger', False)
        self.scan()
        self.assertFalse(self.plc.read_point('position_done'))
        self.assertFalse(self.plc.read_point('position_success'))
        self.plc.write_point('position_trigger', True)
        self.scan()
        self.assertEqual(self.capture.call_count, 2)

    def test_failure_acknowledges_ng_without_reusing_compensation(self):
        self.scan()
        self.capture.return_value = {'is_success': False, 'error_message': '相机采集超时'}
        self.plc.write_point('position_trigger', True)
        self.scan()
        self.assertTrue(self.plc.read_point('position_done'))
        self.assertFalse(self.plc.read_point('position_success'))
        self.assertIsNone(self.state['values'])
        self.scan()
        self.assertEqual(self.capture.call_count, 1)

    def test_invalid_axis_prevents_all_compensation_writes(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        self.capture.return_value['compensation_z'] = float('nan')
        self.scan()
        self.assertEqual(self.plc.read_point('layer_delta_x'), 0)
        self.assertFalse(self.state['ok'])

    def test_readback_failure_cannot_report_ok(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        original = self.plc.read_point
        with patch.object(self.plc, 'read_point', side_effect=lambda name: 999 if name == 'layer_delta_y' else original(name)):
            self.scan()
        self.assertFalse(self.state['ok'])
        self.assertTrue(self.state['done'])

    def test_consumed_trigger_is_persisted_before_camera(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        phases = []
        step(self.state, self.plc, self.capture, lambda: phases.append(self.state['phase']))
        self.assertEqual(phases, ['CAPTURING'])

    def test_file_ownership_excludes_concurrent_scans(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            with ownership() as (state, save):
                state['phase'] = 'ARMING'
                save()
                with self.assertRaises(DebugBusy):
                    with ownership():
                        pass
            with ownership() as (state, save):
                self.assertEqual(state['phase'], 'ARMING')

    @override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': False})
    def test_real_plc_forces_real_camera(self):
        with patch('apps.vision.rack_3d.services.RackPositioningService') as service:
            capture_position(7, 2)
        service.assert_called_once_with(mode='REAL')
        service.return_value.execute_positioning.assert_called_once_with(7, 2, save=True)


class PositionDebugAPITests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(BASE_DIR=Path(self.directory.name),
            AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': True})
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.plc = PLCAdapter(transport=MemoryPLCTransport())
        self.plc.connect()

    def call(self, action, **kwargs):
        from apps.devices.views import api_plc_position_debug
        request = RequestFactory().post('/', data=json.dumps({'action': action, **kwargs}),
                                        content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter', return_value=self.plc):
            return json.loads(api_plc_position_debug(request).content)

    def start(self, layer=1):
        with patch('apps.vision.models.RackLocationRecipe.objects.get', return_value=Mock(pk=7, layer_count=3)):
            return self.call('start', recipe_id=7, layer_no=layer)

    def test_session_start_ownership_stop(self):
        result = self.start()
        self.assertTrue(result['success'])
        token = result['token']
        self.assertFalse(self.start()['success'])
        self.assertFalse(self.call('poll', token='wrong')['success'])
        self.assertEqual(self.call('poll', token=token)['phase'], 'WAIT_TRIGGER')
        self.assertTrue(self.call('stop', token=token)['stopped'])
        self.assertFalse(self.call('poll', token=token)['success'])

    def test_invalid_layer_does_not_claim_plc(self):
        self.assertFalse(self.start(layer=4)['success'])
        self.assertTrue(self.start(layer=1)['success'])

    def test_running_session_rejects_manual_write(self):
        from apps.devices.views import api_plc_write
        self.start()
        request = RequestFactory().post('/', data=json.dumps({'point_name': 'heartbeat', 'value': True}),
                                        content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter') as adapter:
            result = json.loads(api_plc_write(request).content)
        self.assertFalse(result['success'])
        adapter.assert_not_called()
