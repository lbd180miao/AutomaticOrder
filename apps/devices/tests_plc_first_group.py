from types import SimpleNamespace
from django.test import SimpleTestCase
from .plc_position_debug import first_group_position, step
from .plc_db100 import POINTS_BY_NAME

class FirstGroupTests(SimpleTestCase):
    def setUp(self):
        self.recipe = SimpleNamespace(max_offset_x=100, max_offset_y=100, max_offset_z=100, max_offset_rz=10)
        self.result = {'locate_ok': True, 'robot_groups': {
            'A': {'coordinate_system': 'robot_base', 'translation_mm': {'x':1.25,'y':-2.5,'z':3.75}, 'rotation_deg':{'rz':0}},
            'B': {'translation_mm': {'x':91,'y':92,'z':93}}},
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
        with override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES':False}), \
             patch('apps.vision.models.RackLocationRecipe.objects.get',return_value=recipe), \
             patch('apps.vision.rack_location.Rack3DLocator.capture',return_value={'source':'rvc_camera','pointcloud_token':'test.npy'}), \
             patch('apps.vision.rack_location.RackLocationService.calculate_workbench',return_value=result) as calculate:
            output = capture_position(8,1)
        self.assertTrue(output['is_success'])
        self.assertEqual(output['compensation_x'],1)
        calculate.assert_called_once()
