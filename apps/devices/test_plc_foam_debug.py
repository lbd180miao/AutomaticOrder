import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, RequestFactory, override_settings
from apps.devices.adapters.plc import PLCAdapter, MemoryPLCTransport
from apps.devices.plc_foam_debug import step, capture_foam, get_recipe


class FoamHandshakeTests(SimpleTestCase):
    def setUp(self):
        self.plc = PLCAdapter(transport=MemoryPLCTransport())
        self.plc.connect()
        self.state = {'phase': 'ARMING', 'recipe_id': 7}
        self.capture = Mock(return_value={'is_passed': True, 'result_id': 12, 'score': .95})

    def scan(self):
        step(self.state, self.plc, self.capture)

    def test_edges_order_and_adjacent_bits(self):
        self.plc.write_point('foam_trigger', True)
        self.scan()
        self.capture.assert_not_called()
        self.plc.write_point('foam_trigger', False)
        self.scan()
        self.plc.write_point('position_trigger', True)
        self.plc.write_point('foam_trigger', True)
        writes = []
        original = self.plc.write_point
        def record(name, value):
            writes.append((name, value))
            original(name, value)
        with patch.object(self.plc, 'write_point', side_effect=record):
            self.scan()
        self.assertEqual(writes[-2:], [('foam_passed', True), ('foam_done', True)])
        self.assertTrue(self.plc.read_point('position_trigger'))
        self.scan()
        self.capture.assert_called_once_with(7)
        self.plc.write_point('foam_trigger', False)
        self.scan()
        self.assertFalse(self.plc.read_point('foam_done'))
        self.assertFalse(self.plc.read_point('foam_passed'))
        self.plc.write_point('foam_trigger', True)
        self.scan()
        self.assertEqual(self.capture.call_count, 2)

    def test_ng_and_camera_failure_are_acknowledged(self):
        for failure in (False, True):
            with self.subTest(camera_failure=failure):
                self.state['phase'] = 'WAIT_TRIGGER'
                self.plc.write_point('foam_trigger', True)
                self.capture.return_value = {'is_passed': False}
                self.capture.side_effect = RuntimeError('相机超时') if failure else None
                self.scan()
                self.assertTrue(self.plc.read_point('foam_done'))
                self.assertFalse(self.plc.read_point('foam_passed'))
                self.assertEqual(bool(self.state['error']), failure)
                # Keep completion asserted until PLC withdraws its trigger, even for NG.
                self.scan()
                self.assertTrue(self.plc.read_point('foam_done'))
                self.assertFalse(self.plc.read_point('foam_passed'))
                self.plc.write_point('foam_trigger', False)
                self.scan()
                self.assertFalse(self.plc.read_point('foam_done'))

    def test_result_readback_failure_does_not_publish_done_or_recapture(self):
        self.state['phase'] = 'WAIT_TRIGGER'
        self.plc.write_point('foam_trigger', True)
        original = self.plc.read_point
        with patch.object(self.plc, 'read_point', side_effect=lambda name: False if name == 'foam_passed' else original(name)):
            with self.assertRaisesRegex(ValueError, '回读不一致'):
                self.scan()
        self.assertFalse(self.plc.read_point('foam_done'))
        self.scan()
        self.capture.assert_called_once()

    def test_trigger_saved_before_capture(self):
        self.state['phase'] = 'WAIT_TRIGGER'
        self.plc.write_point('foam_trigger', True)
        phases = []
        self.capture.side_effect = lambda recipe: (self.assertEqual(phases, ['CAPTURING']) or {'is_passed': True})
        step(self.state, self.plc, self.capture, lambda: phases.append(self.state['phase']))

    @override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': False})
    def test_real_camera_cannot_fall_back_to_simulation(self):
        with patch('apps.devices.plc_foam_debug.get_recipe', return_value=Mock(pk=7, pos=3)), patch('apps.vision.services.VisionService') as service, patch('apps.vision.algorithms.foam_inspector.FoamInspector') as inspector:
            service.return_value.inspect_foam.return_value = Mock(pk=12, is_passed=True, score=.95, defect_type='NONE')
            capture_foam(7)
        inspector.assert_called_once_with(simulate=False)
        self.assertTrue(service.return_value.inspect_foam.call_args.kwargs['use_camera'])

    def test_missing_roi_rejected(self):
        with patch('apps.vision.models.VisionRecipe.objects.get', return_value=Mock(roi_config={})):
            with self.assertRaisesRegex(ValueError, 'ROI'):
                get_recipe(7)


class FoamDebugAPITests(SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(BASE_DIR=Path(directory.name), AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': True})
        settings.enable()
        self.addCleanup(settings.disable)
        self.plc = PLCAdapter(transport=MemoryPLCTransport())
        self.plc.connect()

    def call(self, action, mode='foam', **kwargs):
        from apps.devices.views import api_plc_position_debug
        request = RequestFactory().post('/', data=json.dumps({'action': action, **kwargs}), content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter', return_value=self.plc), patch('apps.devices.plc_foam_debug.get_recipe', return_value=Mock(pk=7)):
            return json.loads(api_plc_position_debug(request, mode=mode).content)

    def test_session_exclusion_mode_and_full_handshake(self):
        token = self.call('start', recipe_id=7)['token']
        self.assertFalse(self.call('start', mode='position')['success'])
        self.assertFalse(self.call('poll', mode='position', token=token)['success'])
        self.assertFalse(self.call('poll', token='wrong')['success'])
        self.plc.write_point('foam_trigger', True)
        with patch('apps.devices.plc_foam_debug.capture_foam', return_value={'is_passed': True}) as capture:
            self.assertTrue(self.call('poll', token=token)['ok'])
            self.call('poll', token=token)
            capture.assert_called_once()
        self.plc.write_point('foam_trigger', False)
        self.assertFalse(self.call('poll', token=token)['done'])
        self.assertTrue(self.call('stop', token=token)['stopped'])
        self.assertFalse(self.call('poll', token=token)['success'])

    def test_communication_failure_does_not_claim_lease(self):
        with patch.object(self.plc, 'read_point', side_effect=TimeoutError('timeout')):
            self.assertFalse(self.call('start', recipe_id=7)['success'])
        self.assertTrue(self.call('start', recipe_id=7)['success'])

    def test_both_channels_capture_and_stop_independently(self):
        from apps.devices.plc_position_debug import ownership, active
        for first, second in [('position', 'foam'), ('foam', 'position')]:
            with self.subTest(first=first), patch(
                'apps.vision.models.RackLocationRecipe.objects.get',
                return_value=Mock(pk=8, layer_count=3),
            ):
                tokens = {}
                for mode in (first, second):
                    response = self.call('start', mode=mode, recipe_id=7, layer_no=1)
                    self.assertTrue(response['success'], response)
                    tokens[mode] = response['token']
                    self.assertFalse(self.call('start', mode=mode, recipe_id=7, layer_no=1)['success'])
                self.assertNotEqual(tokens[first], tokens[second])
                self.assertFalse(self.call('poll', mode=first, token=tokens[second])['success'])
                self.plc.write_point('position_trigger', True)
                self.plc.write_point('foam_trigger', True)
                with patch('apps.devices.plc_position_debug.capture_position', return_value={
                    'is_success': True, 'compensation_x': 1, 'compensation_y': 2, 'compensation_z': 3,
                }) as position, patch('apps.devices.plc_foam_debug.capture_foam',
                                     return_value={'is_passed': True}) as foam:
                    for mode in (first, second):
                        self.assertTrue(self.call('poll', mode=mode, token=tokens[mode])['ok'])
                        self.call('poll', mode=mode, token=tokens[mode])
                    position.assert_called_once()
                    foam.assert_called_once()
                self.assertTrue(self.plc.read_point('position_done'))
                self.assertTrue(self.plc.read_point('foam_done'))
                self.call('stop', mode=first, token=tokens[first])
                with ownership() as (state, save):
                    self.assertTrue(active(state))
                from apps.devices.views import api_plc_write
                request = RequestFactory().post('/', data=json.dumps({
                    'point_name': 'heartbeat', 'value': True,
                }), content_type='application/json')
                self.assertFalse(json.loads(api_plc_write(request).content)['success'])
                self.assertTrue(self.call('poll', mode=second, token=tokens[second])['success'])
                self.call('stop', mode=second, token=tokens[second])
                with ownership() as (state, save):
                    self.assertFalse(active(state))
                self.plc.write_point('position_trigger', False)
                self.plc.write_point('foam_trigger', False)

    def test_long_capture_preserves_waiting_lease_but_not_expired_lease(self):
        from apps.devices.plc_position_debug import ownership, active
        for expires in (110, 90):
            with patch('apps.devices.plc_position_debug.time.time', return_value=100):
                with ownership() as (state, save):
                    state.clear()
                    state['sessions'] = {'foam': {'expires': expires}}
                    save()
                with patch('apps.devices.plc_position_debug.time.monotonic', side_effect=[0, 30]):
                    with ownership(mode='position'):
                        pass
            with patch('apps.devices.plc_position_debug.time.time', return_value=130):
                with ownership() as (state, save):
                    self.assertEqual(active(state), expires == 110)
                    self.assertEqual(state['sessions']['foam']['expires'], 140 if expires == 110 else 90)
