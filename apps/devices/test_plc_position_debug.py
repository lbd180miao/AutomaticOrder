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
        for axis in 'xyz':
            self.plc.write_point(f'layer_delta_{axis}', 12.5)
        self.capture.return_value = {'is_success': False, 'error_message': '相机采集超时'}
        self.plc.write_point('position_trigger', True)
        self.scan()
        self.assertTrue(self.plc.read_point('position_done'))
        self.assertFalse(self.plc.read_point('position_success'))
        self.assertEqual(self.state['values'], dict.fromkeys('xyz', 999.0))
        for axis in 'xyz':
            self.assertEqual(self.plc.read_point(f'layer_delta_{axis}'), 999.0)
        self.scan()
        self.assertEqual(self.capture.call_count, 1)

    def test_invalid_axis_returns_failure_sentinel_on_all_axes(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        self.capture.return_value['compensation_z'] = float('nan')
        self.scan()
        for axis in 'xyz':
            self.assertEqual(self.plc.read_point(f'layer_delta_{axis}'), 999.0)
        self.assertFalse(self.state['ok'])

    def test_failure_values_are_written_before_done_and_success_recovers(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        self.capture.side_effect = ValueError('ROI有效点不足')
        writes = []
        original = self.plc.write_point
        def record(name, value):
            writes.append((name, value))
            original(name, value)
        with patch.object(self.plc, 'write_point', side_effect=record):
            self.scan()
        self.assertEqual(writes[-4:], [
            ('layer_delta_x', 999.0), ('layer_delta_y', 999.0),
            ('layer_delta_z', 999.0), ('position_done', True),
        ])
        self.assertFalse(self.plc.read_point('position_success'))
        self.plc.write_point('position_trigger', False)
        self.scan()
        self.capture.side_effect = None
        self.plc.write_point('position_trigger', True)
        self.scan()
        self.assertEqual(self.state['values'], {'x': 1.25, 'y': -2.5, 'z': 3.75})
        self.assertTrue(self.plc.read_point('position_success'))

    def test_failure_sentinel_write_error_does_not_publish_done(self):
        self.scan()
        self.plc.write_point('position_trigger', True)
        self.capture.side_effect = ValueError('无点云')
        original = self.plc.write_point
        def fail_y(name, value):
            if name == 'layer_delta_y':
                raise OSError('PLC断开')
            original(name, value)
        with patch.object(self.plc, 'write_point', side_effect=fail_y):
            self.scan()
        self.assertFalse(self.state['done'])
        self.assertFalse(self.plc.read_point('position_done'))
        self.assertFalse(self.plc.read_point('position_success'))
        self.assertIsNone(self.state['values'])

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
        with patch('apps.vision.rack_3d.services.RackPositioningService') as service, patch(
            'apps.vision.models.RackLocationRecipe.objects.get', return_value=Mock(roi_config={}, layer_count=3),
        ):
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

    def test_start_checks_plc_before_claiming_session_and_does_not_write(self):
        with patch.object(self.plc, 'read_point', side_effect=TimeoutError('Receive timeout')), patch.object(self.plc, 'write_point') as write:
            response = self.start()
        self.assertFalse(response['success'])
        self.assertIn('监听未启动', response['error'])
        self.assertIn('Receive timeout', response['error'])
        write.assert_not_called()
        self.assertTrue(self.start()['success'])

    def test_start_high_requires_reset_before_camera_trigger(self):
        self.plc.write_point('position_trigger', True)
        started = self.start()
        self.assertEqual(started['phase'], 'ARMING')
        token = started['token']
        with patch('apps.devices.plc_position_debug.capture_position') as capture:
            self.call('poll', token=token)
            capture.assert_not_called()
            self.plc.write_point('position_trigger', False)
            self.assertEqual(self.call('poll', token=token)['phase'], 'WAIT_TRIGGER')

    def test_running_session_rejects_manual_write(self):
        from apps.devices.views import api_plc_write
        self.start()
        request = RequestFactory().post('/', data=json.dumps({'point_name': 'heartbeat', 'value': True}),
                                        content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter') as adapter:
            result = json.loads(api_plc_write(request).content)
        self.assertFalse(result['success'])
        adapter.assert_not_called()

    def test_full_api_handshake_failure_999_reset_and_success(self):
        token = self.start()['token']
        self.assertEqual(self.call('poll', token=token)['phase'], 'WAIT_TRIGGER')
        self.plc.write_point('position_trigger', True)
        with patch('apps.devices.plc_position_debug.capture_position', side_effect=ValueError('Π1有效点不足')) as capture:
            failed = self.call('poll', token=token)
            self.assertEqual(failed['values'], dict.fromkeys('xyz', 999.0))
            self.assertTrue(failed['done'])
            self.assertFalse(failed['ok'])
            for axis in 'xyz':
                self.assertEqual(self.plc.read_point(f'layer_delta_{axis}'), 999.0)
            self.call('poll', token=token)
            capture.assert_called_once()
        self.plc.write_point('position_trigger', False)
        reset = self.call('poll', token=token)
        self.assertFalse(reset['done'])
        self.assertFalse(self.plc.read_point('position_done'))
        self.plc.write_point('position_trigger', True)
        with patch('apps.devices.plc_position_debug.capture_position', return_value={
            'is_success': True, 'compensation_x': 1.25, 'compensation_y': -2.5, 'compensation_z': 3.75,
        }):
            passed = self.call('poll', token=token)
        self.assertTrue(passed['ok'])
        self.assertEqual(passed['count'], 2)
        self.assertEqual(passed['values'], {'x': 1.25, 'y': -2.5, 'z': 3.75})
        self.assertTrue(self.call('stop', token=token)['stopped'])

    def test_adapter_configuration_failure_returns_json_and_releases_session(self):
        token = self.start()['token']
        from apps.devices.views import api_plc_position_debug
        request = RequestFactory().post('/', data=json.dumps({'action': 'poll', 'token': token}), content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter', side_effect=RuntimeError('PLC未配置')):
            data = json.loads(api_plc_position_debug(request).content)
        self.assertFalse(data['success'])
        self.assertTrue(data['stopped'])
        self.assertIn('PLC未配置', data['error'])
        self.assertTrue(self.start()['success'])


@override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': False})
class WorkbenchPositionGatewayTests(SimpleTestCase):
    def setUp(self):
        self.recipe = Mock(roi_config={'local_template_rois': {'plane1': {'x': 1}}}, layer_count=3)
        self.recipe_patch = patch('apps.vision.models.RackLocationRecipe.objects.get', return_value=self.recipe)
        self.recipe_patch.start()
        self.addCleanup(self.recipe_patch.stop)

    @patch('apps.vision.rack_location.RackLocationService')
    @patch('apps.vision.rack_location.Rack3DLocator')
    def test_uses_workbench_and_plc_payload_for_three_plane_recipe(self, locator, service):
        locator.return_value.capture.return_value = {'source': 'rvc_camera', 'pointcloud_token': 'fresh'}
        service.return_value.calculate_workbench.return_value = {
            'locate_ok': True, 'result_id': 42,
            'plc_payload': {'compensation_valid': True, 'offset_x': 1, 'offset_y': 2, 'offset_z': 3},
        }
        result = capture_position(7, 2)
        self.assertTrue(result['is_success'])
        self.assertEqual(result['compensation_z'], 3)
        locator.return_value.capture.assert_called_once_with(recipe_id=7, layer_no=2)
        service.return_value.calculate_workbench.assert_called_once_with(
            token='fresh', roi_config=self.recipe.roi_config, recipe_id=7, layer_no=2, save_record=True,
        )
        service.return_value.calculate_workbench.return_value['plc_payload']['compensation_valid'] = False
        self.assertFalse(capture_position(7, 2)['is_success'])

    @patch('apps.vision.rack_location.RackLocationService')
    @patch('apps.vision.rack_location.Rack3DLocator')
    def test_real_plc_rejects_simulated_fallback(self, locator, service):
        locator.return_value.capture.return_value = {'source': 'sample_fallback', 'pointcloud_token': 'sample'}
        with self.assertRaisesRegex(ValueError, '真实3D采集失败'):
            capture_position(7, 2)
        service.return_value.calculate_workbench.assert_not_called()
