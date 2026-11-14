"""Regression checks for physical read pacing and exclusive debug modes."""
import tempfile
import threading
import time
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .adapters.plc import Snap7Transport
from .plc_position_debug import ownership


class SerialPollingTests(SimpleTestCase):
    def test_windows_lock_retries_contention_without_native_one_second_wait(self):
        import errno
        from .plc_io import _lock_windows
        import sys
        native = Mock()
        native.locking.side_effect = [OSError(errno.EACCES, 'busy'), None]
        with patch.dict(sys.modules, msvcrt=native), \
             patch('apps.devices.plc_io.time.sleep') as sleep:
            _lock_windows(Mock())
        sleep.assert_called_once_with(0.02)
        self.assertEqual(native.locking.call_count, 2)
        self.assertEqual(native.locking.call_args.args[1], native.LK_NBLCK)

    def test_windows_lock_timeout_identifies_local_contention(self):
        import errno
        import sys
        from .plc_io import _lock_windows
        native = Mock()
        native.locking.side_effect = OSError(errno.EDEADLK, 'Resource deadlock avoided')
        with patch.dict(sys.modules, msvcrt=native), \
             patch('apps.devices.plc_io.time.monotonic', side_effect=[0, 16]):
            with self.assertRaisesRegex(TimeoutError, '本机 PLC 通信锁'):
                _lock_windows(Mock())

    def test_concurrent_connections_cannot_overlap_or_skip_gap(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory):
            events, errors = [], []
            gate = threading.Barrier(2)

            def read(*args):
                events.append(('start', time.monotonic()))
                time.sleep(0.02)
                events.append(('end', time.monotonic()))
                return b'\x00'

            def worker():
                try:
                    transport = Snap7Transport('concurrent-test')
                    transport.client = Mock(db_read=read)
                    gate.wait(timeout=2)
                    transport.read(2, 46, 1)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual([kind for kind, _ in events], ['start', 'end', 'start', 'end'])
            self.assertGreaterEqual(events[2][1] - events[1][1], 0.5)

    def test_connections_share_gap_measured_from_read_completion_even_on_error(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory), \
             patch('apps.devices.plc_io.time.monotonic') as clock, \
             patch('apps.devices.plc_io.time.sleep') as sleep:
            first, second = Snap7Transport('test'), Snap7Transport('test')
            first.client = Mock()
            second.client = Mock()

            def slow_read(*args):
                clock.return_value = 105.0
                return b'\x00'

            clock.return_value = 100.0
            first.client.db_read.side_effect = slow_read
            first.read(2, 46, 1)
            sleep.assert_not_called()
            clock.return_value = 105.2
            second.client.db_read.side_effect = ConnectionError('offline')
            with self.assertRaises(ConnectionError):
                second.read(2, 46, 1)
            self.assertAlmostEqual(sleep.call_args.args[0], 0.3)
            sleep.reset_mock()
            clock.return_value = 105.3
            with self.assertRaises(ConnectionError):
                second.read(2, 46, 1)
            self.assertAlmostEqual(sleep.call_args.args[0], 0.4)

    def test_second_mode_rejected_until_first_stopped(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory), \
             patch('apps.devices.plc_position_debug.time.sleep'):
            with ownership('position') as (state, save):
                state.update(token='test', expires=10**12)
                save()
            with self.assertRaisesRegex(ValueError, '其他工序'):
                with ownership('foam'):
                    self.fail('A second mode was allowed to start')
            with ownership('position', stopping=True) as (state, save):
                state['expires'] = 0
                save()
            with ownership('foam') as (state, save):
                state.update(token='foam', expires=10**12)
                save()

    def test_old_parallel_sessions_can_still_be_stopped(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory), \
             patch('apps.devices.plc_position_debug.time.sleep'):
            with ownership() as (state, save):
                state['sessions'] = {mode: {'expires': 10**12}
                                     for mode in ('position', 'foam')}
                save()
            with ownership('position', stopping=True) as (state, save):
                state['expires'] = 0
                save()
