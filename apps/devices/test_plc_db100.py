import struct

from django.test import SimpleTestCase

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.devices.plc_db100 import POINTS_BY_NAME, decode_value, encode_value, validate_barcode


class DB100CodecTests(SimpleTestCase):
    def test_s7_string_uses_two_byte_header(self):
        point = POINTS_BY_NAME['product_barcode']
        payload = encode_value(point, 'P-100')
        self.assertEqual(len(payload), 22)
        self.assertEqual(payload[:2], bytes([20, 5]))
        self.assertEqual(decode_value(point, payload), 'P-100')

    def test_int_and_real_are_big_endian(self):
        self.assertEqual(encode_value(POINTS_BY_NAME['loaded_quantity'], 24), b'\x00\x18')
        encoded = encode_value(POINTS_BY_NAME['matrix_0_0'], 1.25)
        self.assertEqual(encoded, struct.pack('>f', 1.25))

    def test_barcode_rejects_empty_control_and_overlength(self):
        for value in ('', 'HAS SPACE', 'X' * 21):
            with self.assertRaises(ValueError):
                validate_barcode(value)


class PLCAdapterTests(SimpleTestCase):
    def setUp(self):
        self.transport = MemoryPLCTransport()
        self.plc = PLCAdapter(transport=self.transport)
        self.plc.connect()

    def test_read_write_points_and_matrix(self):
        self.plc.write_point('product_barcode', 'P-001')
        self.plc.write_point('mark_trigger', True)
        self.assertEqual(self.plc.read_point('product_barcode'), 'P-001')
        self.assertTrue(self.plc.read_point('mark_trigger'))

        matrix = [[float(row * 4 + col) for col in range(4)] for row in range(4)]
        self.plc.write_matrix(matrix)
        self.assertEqual(self.plc.read_matrix(), matrix)

    def test_heartbeat_wraps_signed_int(self):
        self.plc.write_point('heartbeat', 32767)
        self.assertEqual(self.plc.tick_heartbeat(), -32768)

