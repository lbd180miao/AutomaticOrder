from unittest.mock import Mock, patch
from django.test import SimpleTestCase, TestCase
from apps.devices.adapters.plc import PLCAdapter, MemoryPLCTransport
from apps.devices.plc_db100 import POINTS_BY_NAME
from apps.mes.client import SimulatedMesClient
from apps.mes.services import MesService
from apps.production.models import Product
from .plc_inputs import collect_events, TRIGGERS
from .station_service import StationWorkflowService


def sample(**changes):
    return dict({'product_barcode': 'PROD001', 'rack_barcode': 'RACK001',
                 'rack_barcode_2': 'RACK002', **dict.fromkeys(TRIGGERS, False)}, **changes)


class RoutingTests(SimpleTestCase):
    def setUp(self):
        self.observed = {}
        collect_events(self.observed, [sample()], initialize=True)

    def events(self, **changes):
        return collect_events(self.observed, [sample(**changes)])[0]

    def test_barcode_change_alone_never_binds(self):
        self.assertEqual(self.events(product_barcode='PROD002'), [])

    def test_second_working_rising_edge_locks_second_rack(self):
        job, = self.events(rack_working_2=True)
        self.assertEqual(job['trigger'], 'mark_trigger')
        self.assertEqual(job['data']['rack_barcode'], 'RACK002')
        self.assertEqual(job['data']['product_barcode'], 'PROD001')
        self.assertTrue(job['consumed'])
        self.events(rack_barcode_2='RACK003', product_barcode='PROD002', rack_working_2=True)
        self.assertEqual(job['data']['rack_barcode'], 'RACK002')
        self.assertEqual(job['data']['product_barcode'], 'PROD001')

    def test_high_for_five_seconds_does_not_repeat(self):
        self.assertEqual(len(self.events(rack_working=True)), 1)
        for _ in range(10):
            self.assertEqual(self.events(rack_working=True), [])
        self.events()
        self.assertEqual(self.events(rack_working=True), [])

    def test_second_edge_while_first_still_high_is_unambiguous(self):
        self.events(rack_working=True)
        job, = self.events(product_barcode='PROD002', rack_working=True, rack_working_2=True)
        self.assertEqual(job['data']['rack_slot'], 2)

    def test_simultaneous_working_edges_reject_ambiguous_product(self):
        events, messages = collect_events(self.observed, [sample(rack_working=True, rack_working_2=True)])
        self.assertEqual(events, [])
        self.assertTrue(any('同时上升' in message for _, message in messages))

    def test_both_boxing_edges_route_independently(self):
        jobs = self.events(boxing_trigger=True, boxing_trigger_2=True)
        self.assertEqual([job['data']['rack_barcode'] for job in jobs], ['RACK001', 'RACK002'])
        self.assertNotEqual(jobs[0]['data']['rack_round'], jobs[1]['data']['rack_round'])

    def test_initial_high_and_reconnect_high_are_only_baselines(self):
        for initialize in (True, True):
            jobs, _ = collect_events(self.observed, [sample(**dict.fromkeys(TRIGGERS, True))], initialize=initialize)
            self.assertEqual(jobs, [])

    def test_buffered_pulses_are_not_lost(self):
        jobs, _ = collect_events(self.observed, [sample(foam_trigger=True), sample(), sample(foam_trigger=True)])
        self.assertEqual([job['trigger'] for job in jobs], ['foam_trigger', 'foam_trigger'])

    def test_invalid_current_rack_does_not_use_cached_rack(self):
        self.assertEqual(self.events(rack_barcode_2='NoRead', rack_working_2=True), [])
        self.assertEqual(self.observed['rack_barcode_2'], 'RACK002')
        self.assertTrue(self.observed['product_pending'])

    def test_invalid_reads_preserve_all_three_effective_codes_and_rounds(self):
        original = dict(self.observed)
        for invalid in ('', '   ', 'NoRead', 'nOrEaD'):
            self.assertEqual(self.events(product_barcode=invalid, rack_barcode=invalid,
                                         rack_barcode_2=invalid), [])
            self.assertEqual(self.observed, original)
        self.assertEqual(self.events(), [])

    def test_each_rack_deduplicates_independently(self):
        jobs = self.events(rack_barcode='RACK003')
        self.assertEqual([(job['trigger'], job['data']['rack_slot']) for job in jobs], [('rack_trigger', 1)])
        jobs = self.events(rack_barcode='RACK003', rack_barcode_2='RACK003')
        self.assertEqual([(job['trigger'], job['data']['rack_slot']) for job in jobs], [('rack_trigger', 2)])
        self.assertEqual(self.events(rack_barcode='RACK003', rack_barcode_2='RACK003'), [])

    def test_same_product_does_not_bind_again_even_on_other_slot(self):
        self.events(rack_working=True)
        self.events(product_barcode='NoRead')
        self.assertEqual(self.events(rack_working_2=True), [])
        self.events()
        job, = self.events(product_barcode='PROD002', rack_working_2=True)
        self.assertEqual(job['data']['product_barcode'], 'PROD002')
        self.assertEqual(job['data']['rack_slot'], 2)

    def test_pending_new_product_survives_invalid_read(self):
        self.events(product_barcode='PROD002')
        self.assertEqual(self.events(product_barcode='', rack_working=True), [])
        self.events(product_barcode='NoRead')
        job, = self.events(product_barcode='PROD002', rack_working=True)
        self.assertEqual(job['data']['product_barcode'], 'PROD002')

    def test_restart_preserves_consumed_product(self):
        import json
        self.events(rack_working=True)
        restored = json.loads(json.dumps(self.observed))
        collect_events(restored, [sample()], initialize=True)
        jobs, _ = collect_events(restored, [sample(rack_working_2=True)])
        self.assertEqual(jobs, [])

    def test_nine_inputs_read_in_one_block(self):
        plc = PLCAdapter(MemoryPLCTransport())
        for name, value in sample(**dict.fromkeys(TRIGGERS, True)).items():
            plc.write_point(name, value)
        with patch.object(plc.transport, 'read', wraps=plc.transport.read) as read:
            values = plc.read_listener_snapshot()
        read.assert_called_once_with(2, 0, 70)
        self.assertEqual(values, sample(**dict.fromkeys(TRIGGERS, True)))

    def test_short_read_rejected(self):
        plc = PLCAdapter(MemoryPLCTransport())
        with patch.object(plc.transport, 'read', return_value=b'\0' * 69):
            with self.assertRaises(ConnectionError):
                plc.read_listener_snapshot()

    def test_inactive_feedback_points_cannot_be_written(self):
        plc = PLCAdapter(MemoryPLCTransport())
        plc.write_point('rack_barcode_2', 'RACK002')
        before = bytes(plc.transport.buffer)
        for name in ('foam_passed', 'mes_upload_done', 'workstation_locked'):
            with self.assertRaises(KeyError):
                plc.write_point(name, True)
        self.assertEqual(bytes(plc.transport.buffer), before)

    def test_heartbeat_toggles_every_half_second_and_preserves_adjacent_bits(self):
        plc = PLCAdapter(MemoryPLCTransport(), heartbeat_interval=10)
        self.assertEqual(plc.heartbeat_interval, 0.5)
        plc.transport.buffer[70] = 0b10101010
        for now, expected in ((100, True), (100.49, True), (100.5, False),
                              (100.99, False), (101, True), (101.5, False)):
            with patch('apps.devices.adapters.plc.time.time', return_value=now):
                self.assertEqual(plc.tick_heartbeat(), expected)
            self.assertEqual(plc.transport.buffer[70], 0b10101010 | expected)

    def test_sampler_toggles_heartbeat_independently_of_input_scan(self):
        import threading
        from .listener import PLCInputSampler
        plc = PLCAdapter(MemoryPLCTransport())
        refreshed = threading.Event()
        sampler = PLCInputSampler(plc, interval=10)
        try:
            self.assertTrue(plc.read_point('heartbeat'))
            original = plc.tick_heartbeat
            def tick():
                result = original()
                refreshed.set()
                return result
            with patch.object(plc, 'tick_heartbeat', side_effect=tick):
                self.assertTrue(refreshed.wait(2))
                self.assertFalse(plc.read_point('heartbeat'))
                refreshed.clear()
                self.assertTrue(refreshed.wait(2))
                self.assertTrue(plc.read_point('heartbeat'))
        finally:
            sampler.close()

    def test_real_heartbeat_byte_read_does_not_wait_for_input_scan(self):
        from apps.devices.adapters.plc import Snap7Transport
        transport = Snap7Transport('127.0.0.1')
        transport.client = Mock()
        transport.client.db_read.return_value = b'\xaa'
        with patch('apps.devices.plc_io.plc_read_interval') as throttle:
            self.assertEqual(transport.read(2, 70, 1), b'\xaa')
            throttle.assert_not_called()
            transport.read(2, 0, 70)
            throttle.assert_called_once_with(transport)

    def test_channels_share_half_second_schedule(self):
        import tempfile
        from django.test import override_settings
        class Transport(MemoryPLCTransport):
            address, tcp_port, rack, slot = 'heartbeat-test', 102, 0, 1
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory):
            transport = Transport()
            a, b = PLCAdapter(transport), PLCAdapter(transport)
            for now, expected in ((100, True), (100.5, False), (101, True)):
                with patch('apps.devices.adapters.plc.time.time', return_value=now):
                    self.assertEqual(a.tick_heartbeat(), expected)
                    self.assertEqual(b.tick_heartbeat(), expected)

    def test_updated_xyz_addresses_and_db_capacity(self):
        from apps.devices.plc_db100 import DB_SIZE
        self.assertEqual(DB_SIZE, 104)
        self.assertEqual([POINTS_BY_NAME['layer_delta_' + axis].offset
                          for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2')],
                         [76, 80, 84, 88, 92, 96])
        plc = PLCAdapter(MemoryPLCTransport())
        for name, value in sample().items():
            plc.write_point(name, value)
        for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2'):
            plc.write_point('layer_delta_' + axis, 1.25)
            self.assertEqual(plc.read_point('layer_delta_' + axis), 1.25)
        plc.tick_heartbeat()
        plc.write_point('rack_type_code', 2)
        plc.write_point('rack_type_code_2', 3)
        self.assertEqual(plc.read_point('rack_type_code'), 2)
        self.assertEqual(plc.read_point('rack_type_code_2'), 3)
        self.assertEqual(plc.read_listener_snapshot(), sample())


class WorkflowTests(TestCase):
    def setUp(self):
        self.plc = PLCAdapter(MemoryPLCTransport())
        self.mes = MesService(client=SimulatedMesClient())
        self.service = StationWorkflowService(plc=self.plc, mes_service=self.mes,
            vision_gateway=Mock(), device_service=Mock(), alarm_service=Mock())
        self.poll()

    def poll(self, **changes):
        for name, value in changes.items():
            self.plc.write_point(name, value)
        return self.service._poll_once_owned()[0]

    def test_alternating_products_bind_to_the_correct_rack(self):
        self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002', product_barcode='PROD001')
        self.assertFalse(Product.objects.exists())
        self.poll(rack_working=True)
        self.assertEqual(Product.objects.get(product_code='PROD001').rack.rack_code, 'RACK001')
        self.poll(rack_working=False, product_barcode='PROD002')
        self.poll(rack_working_2=True)
        self.assertEqual(Product.objects.get(product_code='PROD002').rack.rack_code, 'RACK002')
        self.poll(rack_working_2=True)
        self.assertEqual(Product.objects.count(), 2)

    def test_boxing_uses_each_slot_not_last_active_rack(self):
        self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002')
        with patch.object(self.mes, 'upload_boxing_result', return_value={'success': True, 'bin_code': 'BIN001'}) as upload:
            self.poll(boxing_trigger=True, boxing_trigger_2=True)
            self.assertEqual([call.args[0]['rack_code'] for call in upload.call_args_list], ['RACK001', 'RACK002'])
            self.poll(boxing_trigger=True, boxing_trigger_2=True)
            self.assertEqual(upload.call_count, 2)

    def test_noread_never_creates_product_or_sends_binding(self):
        self.poll(rack_barcode='RACK001', rack_barcode_2='NoRead', product_barcode='PROD001')
        with patch.object(self.mes, 'upload_product_barcode') as upload:
            self.poll(rack_working_2=True)
            upload.assert_not_called()
        self.assertFalse(Product.objects.exists())

    def test_rack_recipe_writes_separate_type_outputs(self):
        with patch.object(self.plc, 'write_point', wraps=self.plc.write_point) as write:
            self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002')
        outputs = [call.args[0] for call in write.call_args_list]
        self.assertIn('rack_type_code', outputs)
        self.assertIn('rack_type_code_2', outputs)

    def test_visual_events_only_write_xyz_and_preserve_all_inputs(self):
        axes = ('x', 'y', 'z', 'x2', 'y2', 'z2')
        self.service.vision.calculate_position_offsets.return_value = dict(zip(axes, (1, 2, 3, 4, 5, 6)))
        self.service.vision.inspect_foam.return_value = (True, None)
        self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002', product_barcode='PROD001')
        with patch.object(self.plc, 'write_point', wraps=self.plc.write_point) as write:
            self.poll(position_trigger=True, foam_trigger=True, rack_working=True, boxing_trigger=True)
        writes = [call.args[0] for call in write.call_args_list if POINTS_BY_NAME[call.args[0]].direction == 'OUT']
        self.assertEqual(set(writes), {'layer_delta_' + axis for axis in axes})
        for axis, value in zip(axes, (1, 2, 3, 4, 5, 6)):
            self.assertEqual(self.plc.read_point('layer_delta_' + axis), value)
        self.assertEqual(self.plc.read_listener_snapshot(), sample(position_trigger=True, foam_trigger=True,
                                                                rack_working=True, boxing_trigger=True))

    def test_invalid_rack_read_then_original_does_not_repeat_mes_query(self):
        with patch.object(self.mes, 'get_rack_recipe', wraps=self.mes.get_rack_recipe) as query:
            self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002')
            self.poll(rack_barcode='', rack_barcode_2='NoRead')
            self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002')
            self.assertEqual(query.call_count, 2)
            self.poll(rack_barcode_2='RACK003')
            self.assertEqual(query.call_count, 3)

    def test_repeated_edges_never_repeat_product_upload(self):
        self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002', product_barcode='PROD001')
        with patch.object(self.mes, 'upload_product_barcode', wraps=self.mes.upload_product_barcode) as upload:
            self.poll(rack_working=True)
            self.poll(rack_working=False, product_barcode='NoRead')
            self.poll(rack_working_2=True, product_barcode='PROD001')
            self.poll(rack_working_2=False)
            self.poll(rack_working=True)
            self.assertEqual(upload.call_count, 1)
            self.poll(rack_working=False, product_barcode='PROD002')
            self.poll(rack_working_2=True)
            self.assertEqual(upload.call_count, 2)
        self.assertEqual(Product.objects.get(product_code='PROD001').rack.rack_code, 'RACK001')
        self.assertEqual(Product.objects.get(product_code='PROD002').rack.rack_code, 'RACK002')

    def test_waiting_upload_does_not_enqueue_duplicate_product(self):
        from apps.mes.remote_client import RemotePending
        self.poll(rack_barcode='RACK001', rack_barcode_2='RACK002', product_barcode='PROD001')
        with patch.object(self.service, '_product_trigger', side_effect=RemotePending):
            self.poll(rack_working=True)
            self.poll(rack_working=False)
            cycle = self.poll(rack_working_2=True)
        queued = [job for job in cycle.io_state['listener_queue'] if job['trigger'] == 'mark_trigger']
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['data']['rack_slot'], 1)

    def test_failed_upload_not_automatically_resubmitted_for_unchanged_code(self):
        self.poll(rack_barcode='RACK001', product_barcode='PROD001')
        with patch.object(self.mes, 'upload_product_barcode', return_value={'success': False, 'error': 'test failure'}) as upload:
            self.poll(rack_working=True)
            self.poll(rack_working=False)
            self.poll(rack_working=True)
            self.assertEqual(upload.call_count, 1)
