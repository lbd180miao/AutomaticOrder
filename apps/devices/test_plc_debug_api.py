import json
from unittest.mock import patch

from django.test import SimpleTestCase, RequestFactory, override_settings
from django.template.loader import render_to_string

from apps.devices import views
from apps.devices.adapters.plc import PLCAdapter, MemoryPLCTransport
from apps.devices.plc_db100 import DB100_POINTS


class PLCWriteTests(SimpleTestCase):
    def setUp(self):
        self.plc = PLCAdapter(transport=MemoryPLCTransport())
        self.plc.connect()

    def write(self, name, value):
        request = RequestFactory().post('/devices/api/plc-write/',
            data=json.dumps({'point_name': name, 'value': value}), content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter', return_value=self.plc):
            return json.loads(views.api_plc_write(request).content)

    def test_bool_set_reset_preserves_other_bits(self):
        self.plc.transport.buffer[48] = 253
        self.assertTrue(self.write('mark_read_done', True)['verified'])
        self.assertEqual(self.plc.transport.buffer[48], 255)
        self.assertTrue(self.write('mark_read_done', False)['verified'])
        self.assertEqual(self.plc.transport.buffer[48], 253)

    def test_real_round_trip_all_axes(self):
        for axis in 'xyz':
            self.assertTrue(self.write('layer_delta_' + axis, -1.234)['verified'])

    def test_invalid_values_and_inputs_do_not_write(self):
        for name, value in [('heartbeat', 'wrong'), ('heartbeat', 2),
                            ('layer_delta_x', 'NaN'), ('layer_delta_y', 'Infinity'),
                            ('layer_delta_z', 1e100), ('mark_trigger', True)]:
            with self.subTest(name=name, value=value):
                with patch.object(self.plc, 'write_point') as write:
                    self.assertFalse(self.write(name, value)['success'])
                    write.assert_not_called()

    def test_mismatch_is_not_success(self):
        with patch.object(self.plc, 'read_point', return_value=False):
            result = self.write('heartbeat', True)
        self.assertFalse(result['success'])
        self.assertFalse(result['verified'])

    def test_template_contains_output_addresses(self):
        html = render_to_string('devices/plc_debug.html', {'plc_points': DB100_POINTS, 'db_number': 2})
        write_form = html.split('id="write-form"')[1].split('</form>')[0]
        for point in DB100_POINTS:
            self.assertEqual(f'value="{point.name}"' in write_form, point.direction == 'OUT')
        self.assertIn('DBX48.7', write_form)
        self.assertIn('DBD54', write_form)

    @override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': False})
    def test_manual_read_closes_connection_even_on_timeout(self):
        request = RequestFactory().post('/', data=json.dumps({'point_name': 'position_trigger'}), content_type='application/json')
        with patch('apps.devices.services.get_plc_adapter', return_value=self.plc), patch.object(
            self.plc, 'read_point', side_effect=TimeoutError('Receive timeout'),
        ), patch.object(self.plc, 'disconnect') as close:
            response = json.loads(views.api_plc_read(request).content)
        self.assertFalse(response['success'])
        close.assert_called_once()

    @override_settings(AUTOMATIC_ORDER={'USE_SIMULATED_DEVICES': False})
    def test_manual_write_closes_connection(self):
        with patch.object(self.plc, 'disconnect') as close:
            self.assertTrue(self.write('layer_delta_x', 999)['verified'])
        close.assert_called_once()
