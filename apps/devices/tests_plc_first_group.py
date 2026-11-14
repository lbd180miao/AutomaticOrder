from types import SimpleNamespace
from django.test import SimpleTestCase, TestCase
from .plc_position_debug import first_group_position, step
from .plc_db100 import POINTS_BY_NAME

class FirstGroupTests(SimpleTestCase):
    def setUp(self):
        self.recipe = SimpleNamespace(max_offset_x=100, max_offset_y=100, max_offset_z=100, max_offset_rz=10)
        self.result = {'locate_ok': True, 'plc_publish_allowed': False,
                       'robot_result': {'success': True}, 'robot_groups': {
            'A': {'coordinate_system': 'robot_base', 'translation_mm': {'x':1.25,'y':-2.5,'z':3.75}, 'rotation_deg':{'rz':0}},
            'B': {'coordinate_system':'robot_base', 'translation_mm': {'x':91,'y':92,'z':93}, 'rotation_deg':{'rz':0}}},
            'plc_payload': {'compensation_valid':False, 'offset_x':55}}

    def test_first_group_overwrites_only_six_results(self):
        values = {'position_trigger': True}
        writes = []
        class PLC:
            def tick_heartbeat(self): pass
            def read_point(self, name): return values.get(name)
            def write_point(self, name, value):
                values[name] = value
                writes.append((name, value))
        state = {'phase':'WAIT_TRIGGER','recipe_id':8,'layer_no':1}
        def capture(*_, on_captured):
            self.assertTrue(values['position_trigger'])
            on_captured()
            self.assertFalse(values.get('position_done', False))
            return first_group_position(self.result, self.recipe)
        step(state, PLC(), capture)
        self.assertTrue(state['ok'])
        self.assertEqual([values['layer_delta_'+a] for a in 'xyz'], [1.25,-2.5,3.75])
        self.assertEqual([POINTS_BY_NAME['layer_delta_'+a].offset for a in 'xyz'], [76,80,84])
        self.assertEqual([values['layer_delta_'+a+'2'] for a in 'xyz'], [91,92,93])
        self.assertEqual([POINTS_BY_NAME['layer_delta_'+a+'2'].offset for a in 'xyz'], [88,92,96])
        self.assertEqual({name for name, _ in writes}, {'layer_delta_' + axis for axis in ('x','y','z','x2','y2','z2')})
        count = len(writes)
        step(state, PLC(), lambda *_: self.fail('same trigger captured twice'))
        self.assertEqual(len(writes), count)

    def test_missing_group_never_uses_legacy_or_b(self):
        del self.result['robot_groups']['A']
        self.assertFalse(first_group_position(self.result,self.recipe)['is_success'])

    def test_invalid_or_excessive_values_fail(self):
        for value in [float('nan'), float('inf'), 101]:
            self.result['robot_groups']['A']['translation_mm']['x'] = value
            self.assertFalse(first_group_position(self.result,self.recipe)['is_success'])

    def test_camera_coordinates_fail(self):
        self.result['robot_groups']['A']['coordinate_system']='camera'
        self.assertFalse(first_group_position(self.result,self.recipe)['is_success'])

    def test_matching_failure_keeps_original_reason_despite_legacy_flag(self):
        self.result.update(locate_ok=False, error_message='模板覆盖率不足：区域 2 遮挡')
        result = first_group_position(self.result, self.recipe)
        self.assertFalse(result['is_success'])
        self.assertEqual(result['error_message'], '模板覆盖率不足：区域 2 遮挡')

    def test_failed_calibration_rejects_even_stale_valid_groups(self):
        self.result['robot_result'] = {'success': False, 'errorMessage': '请保存拍照机器人姿态'}
        result = first_group_position(self.result, self.recipe)
        self.assertFalse(result['is_success'])
        self.assertEqual(result['error_message'], '请保存拍照机器人姿态')

class PlcStaticTests(SimpleTestCase):
    def test_javascript_response_is_executable(self):
        from django.test import Client, override_settings
        with override_settings(ALLOWED_HOSTS=['testserver'], DEBUG=False):
            response = Client().get('/static/devices/js/plc_position_debug.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])
        response.close()

class CaptureRouteTests(TestCase):
    def test_cloud_recipe_uses_shared_matcher(self):
        from unittest.mock import patch
        from .plc_position_debug import capture_position
        from django.test import override_settings
        recipe = SimpleNamespace(roi_config={'cloud_center_reference':{'version':'cloud_match_v1'}}, layer_count=3,
                                 max_offset_x=100,max_offset_y=100,max_offset_z=100,max_offset_rz=10)
        result = {'locate_ok':True, 'robot_groups':{'A':{'coordinate_system':'robot_base',
                   'translation_mm':{'x':1,'y':2,'z':3}, 'rotation_deg':{'rz':0}}}}
        result['robot_groups']['B'] = result['robot_groups']['A'].copy()
        with override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES':False}), \
             patch('apps.vision.models.RackLocationRecipe.objects.get',return_value=recipe), \
             patch('apps.vision.rack_location.Rack3DLocator.capture',return_value={'source':'rvc_camera','pointcloud_token':'test.npy'}), \
             patch('apps.vision.rack_location.RackLocationService.calculate_workbench',return_value=result) as calculate:
            output = capture_position(8,1)
        self.assertTrue(output['is_success'])
        self.assertEqual(output['compensation_x'],1)
        calculate.assert_called_once()

    def test_plane_only_recipe_captures_but_does_not_compute(self):
        from unittest.mock import patch
        from .plc_position_debug import capture_position
        recipe = SimpleNamespace(roi_config={'spatial_rois': {'configured': True}}, layer_count=3)
        with patch('apps.vision.models.RackLocationRecipe.objects.get', return_value=recipe),              patch('apps.vision.rack_location.Rack3DLocator.capture', return_value={'pointcloud_token': 'test.npy'}) as capture:
            result = capture_position(8, 1)
        self.assertFalse(result['is_success'])
        self.assertIn('点云标准模板', result['error_message'])
        capture.assert_called_once()

    def test_missing_groups_fail_with_concrete_reason(self):
        recipe = SimpleNamespace(max_offset_x=100, max_offset_y=100, max_offset_z=100, max_offset_rz=10)
        result = {'locate_ok': True, 'plc_publish_allowed': False, 'robot_groups': {}}
        converted = first_group_position(result, recipe)
        self.assertFalse(converted['is_success'])
        self.assertIn('缺少A组', converted['error_message'])


class NewDBContractTests(SimpleTestCase):
    def test_six_reals_do_not_overlap_control_bits(self):
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        from .plc_db100 import DB_SIZE
        plc = PLCAdapter(MemoryPLCTransport())
        self.assertEqual(DB_SIZE, 104)
        plc.write_point('rack_type_code', 2)
        plc.write_point('rack_type_code', 1)
        self.assertEqual(plc.read_point('rack_type_code'), 1)
        plc.write_point('rack_type_code_2', 3)
        plc.write_point('rack_working_2', True)
        values = dict(zip(('x','y','z','x2','y2','z2'), (1.25,-2.5,3.75,4.5,5.25,-6.5)))
        plc.send_rack_offsets({f'offset_{a}': v for a,v in values.items()})
        for a,v in values.items():
            self.assertEqual(plc.read_point(f'layer_delta_{a}'), v)
        self.assertEqual(plc.read_point('rack_type_code'), 1)
        self.assertEqual(plc.read_point('rack_type_code_2'), 3)
        self.assertTrue(plc.read_point('rack_working_2'))
        before = bytes(plc.transport.buffer)
        with self.assertRaises(ValueError):
            plc.send_rack_offsets({'offset_x': 99})
        self.assertEqual(bytes(plc.transport.buffer), before)

    def test_foam_result_matches_verdict_then_reset(self):
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        from .plc_foam_debug import step
        for passed in (True, False):
            plc = PLCAdapter(MemoryPLCTransport())
            plc.write_point('foam_trigger', True)
            state = {'phase':'WAIT_TRIGGER', 'recipe_id':1}
            step(state, plc, lambda _: {'is_passed':passed})
            self.assertEqual(state['ok'], passed)
            self.assertEqual(state['ok'], passed)
            step(state, plc, lambda _: self.fail('duplicate capture'))
            self.assertTrue(plc.read_point('foam_trigger'))
            plc.write_point('foam_trigger', False)
            step(state, plc)
            self.assertEqual(state['ok'], passed)

    def test_missing_second_group_writes_zeros(self):
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_trigger', True)
        state = {'phase':'WAIT_TRIGGER','recipe_id':1,'layer_no':1}
        def capture(*_, on_captured):
            on_captured()
            return {'is_success':True,'compensation_x':1,'compensation_y':2,'compensation_z':3}
        step(state, plc, capture)
        self.assertTrue(state['ok'])
        for a, expected in zip(('x','y','z','x2','y2','z2'), (1,2,3,0,0,0)):
            self.assertEqual(plc.read_point(f'layer_delta_{a}'), expected)


class StationContractTests(SimpleTestCase):
    def setUp(self):
        from unittest.mock import patch
        log_patch = patch('apps.workflow.station_service.record')
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def service(self):
        from unittest.mock import Mock
        from apps.workflow.station_service import StationWorkflowService
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        service = object.__new__(StationWorkflowService)
        service.plc = PLCAdapter(MemoryPLCTransport())
        service.devices = Mock()
        service.plc_device_code = 'PLC-01'
        service.vision = Mock()
        service._set_phase = Mock()
        service._lock = Mock()
        service._channel_failure = Mock()
        return service

    def test_station_sends_both_groups(self):
        from unittest.mock import Mock
        service = self.service()
        def calculate(cycle, *, on_captured):
            self.assertFalse(service.plc.read_point('position_trigger'))
            on_captured()
            return dict(zip(('x','y','z','x2','y2','z2'), range(1,7)))
        service.vision.calculate_position_offsets.side_effect = calculate
        cycle = Mock(io_state={})
        service._position_trigger(cycle, {'position_trigger':True})
        for a,v in zip(('x','y','z','x2','y2','z2'),range(1,7)):
            self.assertEqual(service.plc.read_point(f'layer_delta_{a}'),v)
        self.assertFalse(service.plc.read_point('position_done'))
        self.assertEqual(cycle.positioning_matrix,[[1,2,3],[4,5,6]])

    def test_station_ng_overwrites_only_false_result(self):
        from unittest.mock import Mock
        service = self.service()
        service.vision.inspect_foam.return_value = (False, None)
        cycle = Mock(loaded_quantity=0, io_state={})
        self.assertTrue(service._foam_trigger(cycle, {'foam_trigger':True}))
        self.assertFalse(service.plc.read_point('foam_passed'))
        self.assertFalse(service.plc.read_point('foam_done'))
        self.assertFalse(cycle.foam_passed)
        self.assertEqual(cycle.loaded_quantity,0)
        service._channel_failure.assert_called_once()
        service._lock.assert_not_called()


class LayerResultContractTests(SimpleTestCase):
    def result(self):
        return {'locate_ok': True, 'plc_publish_allowed': True, 'robot_groups': {
            name: {'coordinate_system':'robot_base', 'translation_mm':dict(zip('xyz', values)),
                   'rotation_deg':{'rz':0}}
            for name,values in [('A',(1,2,3)),('B',(4,5,6))]}}

    def recipe(self, layers):
        return SimpleNamespace(layer_count=layers, roi_config={'cloud_center_config':{'rack_layers':layers}},
            max_offset_x=100,max_offset_y=100,max_offset_z=100,max_offset_rz=10)

    def test_two_layers_clear_second_group_even_if_stale_group_exists(self):
        from .plc_position_debug import dual_group_position
        result = dual_group_position(self.result(), self.recipe(2))
        self.assertTrue(result['is_success'])
        self.assertEqual([result['compensation_'+a] for a in ('x','y','z','x2','y2','z2')], [1,2,3,0,0,0])

    def test_three_layers_require_both_valid_groups(self):
        from .plc_position_debug import dual_group_position
        data = self.result()
        result = dual_group_position(data, self.recipe(3))
        self.assertTrue(result['is_success'])
        self.assertEqual([result['compensation_'+a] for a in ('x','y','z','x2','y2','z2')], [1,2,3,4,5,6])
        del data['robot_groups']['B']
        self.assertFalse(dual_group_position(data, self.recipe(3))['is_success'])
