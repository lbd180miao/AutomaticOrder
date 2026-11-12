from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .adapters.plc import MemoryPLCTransport, PLCAdapter
from .plc_db100 import position_values
from .plc_position_debug import capture_position, dual_group_position, step


class CaptureCompletionTests(SimpleTestCase):
    def test_plc_can_ack_capture_before_calculation_finishes(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_trigger', True)
        state = {'phase': 'WAIT_TRIGGER', 'recipe_id': 1, 'layer_no': 1}

        def capture(*_, on_captured):
            self.assertFalse(plc.read_point('position_trigger'))
            on_captured()
            self.assertTrue(plc.read_point('position_done'))
            plc.write_point('position_done', False)  # PLC proceeds while calculating.
            return {'is_success': True, 'compensation_x': 1,
                    'compensation_y': 2, 'compensation_z': 3}

        step(state, plc, capture)
        self.assertFalse(plc.read_point('position_done'))
        self.assertTrue(plc.read_point('position_success'))
        self.assertEqual(plc.read_point('layer_delta_z2'), 0)
        step(state, plc, Mock(side_effect=AssertionError('duplicate capture')))
        self.assertEqual(state['phase'], 'WAIT_ACK')
        plc.write_point('position_success', False)
        step(state, plc, Mock(side_effect=AssertionError('duplicate capture')))
        plc.write_point('position_trigger', True)
        step(state, plc, capture)
        self.assertEqual(state['count'], 2)

    def test_capture_failure_does_not_signal_photo_complete(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('position_trigger', True)
        step({'phase': 'WAIT_TRIGGER', 'recipe_id': 1, 'layer_no': 1}, plc,
             Mock(side_effect=RuntimeError('camera disconnected')))
        self.assertFalse(plc.read_point('position_trigger'))
        self.assertFalse(plc.read_point('position_done'))
        self.assertFalse(plc.read_point('position_success'))

    def test_real_capture_boundary_precedes_calculation(self):
        recipe = SimpleNamespace(roi_config={'cloud_center_reference': True}, layer_count=1,
                                 max_offset_x=100, max_offset_y=100,
                                 max_offset_z=100, max_offset_rz=10)
        order = []
        result = {'locate_ok': True, 'robot_groups': {'A': {
            'coordinate_system': 'robot_base', 'translation_mm': {'x': 1, 'y': 2, 'z': 3},
            'rotation_deg': {'rz': 0}}}}

        def acquired(**kwargs):
            order.append('capture')
            return {'pointcloud_token': 'frame.npy'}

        def calculate(**kwargs):
            order.append('calculate')
            return result

        with patch('apps.vision.models.RackLocationRecipe.objects.get', return_value=recipe), \
             patch('apps.vision.rack_location.Rack3DLocator.capture', side_effect=acquired), \
             patch('apps.vision.rack_location.RackLocationService.calculate_workbench', side_effect=calculate):
            output = capture_position(1, 1, on_captured=lambda: order.append('notify'))
        self.assertEqual(order, ['capture', 'notify', 'calculate'])
        self.assertTrue(output['is_success'])
        self.assertEqual(output['compensation_x2'], 0)
        result['robot_groups']['B'] = {'coordinate_system': 'camera'}
        self.assertFalse(dual_group_position(result, recipe)['is_success'])

    def test_partial_second_group_is_not_silently_zeroed(self):
        with self.assertRaises(ValueError):
            position_values({'offset_x': 1, 'offset_y': 2, 'offset_z': 3, 'offset_x2': 4})
