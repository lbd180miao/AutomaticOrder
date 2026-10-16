from types import SimpleNamespace
from django.test import SimpleTestCase
from .plc_position_debug import first_group_position, step
from .plc_db100 import POINTS_BY_NAME

class FirstGroupTests(SimpleTestCase):
    def setUp(self):
        self.recipe = SimpleNamespace(max_offset_x=100, max_offset_y=100, max_offset_z=100, max_offset_rz=10)
        self.result = {'locate_ok': True, 'robot_groups': {
            'A': {'coordinate_system': 'robot_base', 'translation_mm': {'x':1.25,'y':-2.5,'z':3.75}, 'rotation_deg':{'rz':0}},
            'B': {'coordinate_system':'robot_base', 'translation_mm': {'x':91,'y':92,'z':93}, 'rotation_deg':{'rz':0}}},
            'plc_payload': {'compensation_valid':False, 'offset_x':55}}

    def test_first_group_written_with_handshake(self):
        values = {'position_trigger': True}
        writes = []
        class PLC:
            def tick_heartbeat(self): pass
            def read_point(self, name): return values.get(name)
            def write_point(self, name, value):
                values[name] = value
                writes.append((name, value))
        state = {'phase':'WAIT_TRIGGER','recipe_id':8,'layer_no':1}
        step(state, PLC(), lambda *_: first_group_position(self.result, self.recipe))
        self.assertTrue(state['ok'])
        self.assertEqual([values['layer_delta_'+a] for a in 'xyz'], [1.25,-2.5,3.75])
        self.assertEqual([POINTS_BY_NAME['layer_delta_'+a].offset for a in 'xyz'], [50,54,58])
        self.assertEqual([values['layer_delta_'+a+'2'] for a in 'xyz'], [91,92,93])
        self.assertEqual([POINTS_BY_NAME['layer_delta_'+a+'2'].offset for a in 'xyz'], [62,66,70])
        self.assertEqual(writes[-1], ('position_done',True))
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

class PlcStaticTests(SimpleTestCase):
    def test_javascript_response_is_executable(self):
        from django.test import Client, override_settings
        with override_settings(ALLOWED_HOSTS=['testserver'], DEBUG=False):
            response = Client().get('/static/devices/js/plc_position_debug.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])
        response.close()

class CaptureRouteTests(SimpleTestCase):
    def test_spatial_only_recipe_uses_workbench_group_a(self):
        from unittest.mock import patch
        from .plc_position_debug import capture_position
        from django.test import override_settings
        recipe = SimpleNamespace(roi_config={'spatial_rois':{'configured':True}}, layer_count=3,
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


class NewDBContractTests(SimpleTestCase):
    def test_six_reals_do_not_overlap_control_bits(self):
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        from .plc_db100 import DB_SIZE
        plc = PLCAdapter(MemoryPLCTransport())
        self.assertEqual(DB_SIZE, 75)
        plc.write_point('foam_passed', True)
        plc.write_point('workstation_locked', True)
        values = dict(zip(('x','y','z','x2','y2','z2'), (1.25,-2.5,3.75,4.5,5.25,-6.5)))
        plc.send_rack_offsets({f'offset_{a}': v for a,v in values.items()})
        for a,v in values.items():
            self.assertEqual(plc.read_point(f'layer_delta_{a}'), v)
        self.assertTrue(plc.read_point('foam_passed'))
        self.assertTrue(plc.read_point('workstation_locked'))
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
            self.assertEqual(plc.read_point('foam_passed'), passed)
            self.assertTrue(plc.read_point('foam_done'))
            self.assertEqual(state['ok'], passed)
            step(state, plc, lambda _: self.fail('duplicate capture'))
            plc.write_point('foam_trigger', False)
            step(state, plc)
            self.assertFalse(plc.read_point('foam_passed'))
            self.assertFalse(plc.read_point('foam_done'))

    def test_missing_second_group_writes_six_failure_values(self):
        from .adapters.plc import PLCAdapter, MemoryPLCTransport
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_trigger', True)
        state = {'phase':'WAIT_TRIGGER','recipe_id':1,'layer_no':1}
        step(state, plc, lambda *_: {'is_success':True,'compensation_x':1,'compensation_y':2,'compensation_z':3})
        self.assertFalse(plc.read_point('position_success'))
        self.assertTrue(plc.read_point('position_done'))
        for a in ('x','y','z','x2','y2','z2'):
            self.assertEqual(plc.read_point(f'layer_delta_{a}'),999)


class StationContractTests(SimpleTestCase):
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
        return service

    def test_station_sends_both_groups(self):
        from unittest.mock import Mock
        service = self.service()
        service.vision.calculate_position_offsets.return_value = dict(zip(('x','y','z','x2','y2','z2'), range(1,7)))
        cycle = Mock()
        service._position_trigger(cycle, {'position_trigger':True})
        for a,v in zip(('x','y','z','x2','y2','z2'),range(1,7)):
            self.assertEqual(service.plc.read_point(f'layer_delta_{a}'),v)
        self.assertTrue(service.plc.read_point('position_done'))
        self.assertEqual(cycle.positioning_matrix,[[1,2,3],[4,5,6]])

    def test_station_ng_reports_false_result_and_true_completion(self):
        from unittest.mock import Mock
        service = self.service()
        service.vision.inspect_foam.return_value = (False, None)
        cycle = Mock(loaded_quantity=0)
        self.assertTrue(service._foam_trigger(cycle, {'foam_trigger':True}))
        self.assertFalse(service.plc.read_point('foam_passed'))
        self.assertTrue(service.plc.read_point('foam_done'))
        self.assertFalse(cycle.foam_passed)
        self.assertEqual(cycle.loaded_quantity,0)
        service._lock.assert_called_once()
