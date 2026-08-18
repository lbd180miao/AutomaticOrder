import struct

from django.test import SimpleTestCase

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.devices.plc_db100 import (
    DB_SIZE, POINTS_BY_NAME, decode_value, encode_value, validate_barcode,
)


class DB100CodecTests(SimpleTestCase):
    def test_s7_string_uses_two_byte_header(self):
        point = POINTS_BY_NAME['product_barcode']
        payload = encode_value(point, 'P-100')
        self.assertEqual(len(payload), 22)
        self.assertEqual(payload[:2], bytes([20, 5]))
        self.assertEqual(decode_value(point, payload), 'P-100')

    def test_int_and_real_are_big_endian(self):
        self.assertEqual(encode_value(POINTS_BY_NAME['heartbeat'], 24), b'\x00\x18')
        encoded = encode_value(POINTS_BY_NAME['layer_delta_z'], 1.25)
        self.assertEqual(encoded, struct.pack('>f', 1.25))

    def test_contract_uses_new_71_byte_layout(self):
        self.assertEqual(DB_SIZE, 71)
        expected = {
            'product_barcode_valid': 26,
            'rack_barcode': 28,
            'rack_result': 52,
            'recipe_verify_trigger': 53,
            'position_trigger': 56,
            'layer_delta_z': 60,
            'foam_trigger': 64,
            'foam_passed': 65,
            'boxing_trigger': 67,
            'workstation_locked': 70,
        }
        self.assertEqual(
            {name: POINTS_BY_NAME[name].offset for name in expected}, expected,
        )
        self.assertEqual(POINTS_BY_NAME['foam_passed'].direction, 'IN')

    def test_barcode_rejects_empty_control_and_overlength(self):
        for value in ('', 'HAS SPACE', 'X' * 21):
            with self.assertRaises(ValueError):
                validate_barcode(value)


class PLCAdapterTests(SimpleTestCase):
    def setUp(self):
        self.transport = MemoryPLCTransport()
        self.plc = PLCAdapter(transport=self.transport)
        self.plc.connect()

    def test_read_write_points_and_delta_z(self):
        self.plc.write_point('product_barcode', 'P-001')
        self.plc.write_point('mark_trigger', True)
        self.assertEqual(self.plc.read_point('product_barcode'), 'P-001')
        self.assertTrue(self.plc.read_point('mark_trigger'))
        self.plc.write_point('layer_delta_z', 1.875)
        self.assertAlmostEqual(self.plc.read_point('layer_delta_z'), 1.875)

    def test_send_rack_offsets_writes_only_delta_z(self):
        result = self.plc.send_rack_offsets({'offset_z': -2.5})
        self.assertTrue(result['success'])
        self.assertAlmostEqual(self.plc.read_point('layer_delta_z'), -2.5)

    def test_heartbeat_wraps_signed_int(self):
        self.plc.write_point('heartbeat', 32767)
        self.assertEqual(self.plc.tick_heartbeat(), -32768)
