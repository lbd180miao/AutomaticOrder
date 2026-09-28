import struct
import unittest
from unittest.mock import Mock

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.devices.plc_db100 import DB_SIZE, POINTS_BY_NAME


class DB100LayoutTests(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryPLCTransport()
        self.plc = PLCAdapter(transport=self.transport)
        self.plc.connect()

    def test_shared_bits_preserve_neighbors(self):
        for offset in (46, 48, 49, 62):
            points = [p for p in POINTS_BY_NAME.values()
                      if p.offset == offset and p.data_type == 'BOOL']
            self.transport.buffer[offset] = 255
            for point in points:
                self.plc.write_point(point.name, False)
                self.assertEqual(self.transport.buffer[offset], 255 ^ (1 << point.bit))
                self.plc.write_point(point.name, True)
                self.assertEqual(self.transport.buffer[offset], 255)

    def test_heartbeat_toggles_only_bit_zero(self):
        self.transport.buffer[48] = 254
        self.assertIs(self.plc.tick_heartbeat(), True)
        self.assertEqual(self.transport.buffer[48], 255)
        self.assertIs(self.plc.tick_heartbeat(), False)
        self.assertEqual(self.transport.buffer[48], 254)

    def test_all_transport_operations_target_db2(self):
        transport = Mock(wraps=self.transport)
        plc = PLCAdapter(transport=transport)
        plc.write_point('mark_read_done', True)
        plc.read_point('product_barcode')
        plc.read_snapshot()
        self.assertTrue(transport.read.called)
        self.assertTrue(transport.write.called)
        for call in transport.read.call_args_list + transport.write.call_args_list:
            self.assertEqual(call.args[0], 2)

    def test_strings_and_input_snapshot(self):
        self.plc.write_point('product_barcode', 'ABC')
        self.plc.write_point('rack_barcode', 'RACK')
        self.transport.buffer[22] = 1
        self.transport.buffer[46] = 31
        snapshot = self.plc.read_snapshot()
        self.assertEqual(self.transport.buffer[:5], b'\x14\x03ABC')
        self.assertEqual(self.transport.buffer[24:30], b'\x14\x04RACK')
        self.assertEqual(snapshot['product_barcode'], 'ABC')
        self.assertEqual(snapshot['rack_barcode'], 'RACK')
        for name in ('mark_trigger', 'rack_trigger', 'recipe_verify_trigger',
                     'position_trigger', 'foam_trigger', 'boxing_trigger'):
            self.assertIs(snapshot[name], True)
        self.assertNotIn('foam_passed', snapshot)

    def test_three_axis_big_endian_reals(self):
        self.transport.buffer[49] = 7
        self.transport.buffer[62] = 31
        self.plc.send_rack_offsets({'offset_x': 1.25, 'offset_y': -2.5, 'offset_z': 3.75})
        self.assertEqual(self.transport.buffer[50:62], struct.pack('>fff', 1.25, -2.5, 3.75))
        self.assertEqual(self.transport.buffer[49], 7)
        self.assertEqual(self.transport.buffer[62], 31)
        self.assertEqual(len(self.transport.buffer), DB_SIZE)


if __name__ == '__main__':
    unittest.main()
