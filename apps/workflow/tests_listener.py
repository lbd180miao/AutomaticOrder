from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from . import listener


class ListenerTests(SimpleTestCase):
    def test_stop_reports_stopping_until_worker_finishes(self):
        import threading
        stop = threading.Event()
        with patch.object(listener, '_thread') as thread, patch.object(listener, '_stop', stop):
            thread.is_alive.return_value = True
            self.assertTrue(listener.listener_running())
            listener.stop_listener(wait=False)
            self.assertFalse(listener.listener_running())
            self.assertTrue(listener.listener_stopping())
            thread.join.assert_not_called()
            with patch.object(listener.threading, 'Thread') as new_thread:
                listener.start_listener(manual=True)
                new_thread.assert_not_called()
            self.assertTrue(stop.is_set())
            thread.is_alive.return_value = False
            self.assertFalse(listener.listener_stopping())

    def test_global_stop_works_even_without_configured_device(self):
        from django.test import RequestFactory
        from apps.devices.views import api_plc_global
        with patch('apps.devices.views._get_plc_device') as device, \
             patch.object(listener, 'stop_listener') as stop, \
             patch.object(listener, 'start_listener') as start:
            response = api_plc_global(RequestFactory().post('/devices/api/plc-global/', {'action': 'stop'}))
        self.assertEqual(response.status_code, 200)
        stop.assert_called_once_with(wait=False)
        start.assert_not_called()
        device.assert_not_called()

    @override_settings(PLC_LISTENER_AUTO_START=False)
    def test_manual_start_is_allowed_and_repeated_click_does_not_duplicate(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory), \
             patch.object(listener, '_thread', None), \
             patch.object(listener, '_stop'), \
             patch.object(listener, 'logger'), \
             patch.object(listener.atexit, 'register'), \
             patch.object(listener.threading, 'Thread') as thread:
            thread.return_value.is_alive.return_value = True
            listener.start_listener(manual=True)
            listener.start_listener(manual=True)
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()

    def test_global_endpoint_requires_post_and_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/devices/api/plc-global/').status_code, 405)
        self.assertEqual(client.post('/devices/api/plc-global/').status_code, 403)

    def test_global_endpoint_manually_starts_listener(self):
        from django.test import RequestFactory
        from apps.devices.views import api_plc_global
        with patch('apps.devices.views._get_plc_device', return_value=Mock()), \
             patch.object(listener, 'start_listener') as start, \
             patch.object(listener, 'listener_running', return_value=True):
            response = api_plc_global(RequestFactory().post('/devices/api/plc-global/', {'action': 'start'}))
        self.assertEqual(response.status_code, 200)
        start.assert_called_once_with(manual=True)

    def test_global_endpoint_rejects_missing_plc(self):
        from django.test import RequestFactory
        from apps.devices.views import api_plc_global
        with patch('apps.devices.views._get_plc_device', return_value=None), \
             patch.object(listener, 'start_listener') as start:
            response = api_plc_global(RequestFactory().post('/devices/api/plc-global/', {'action': 'start'}))
        self.assertEqual(response.status_code, 400)
        start.assert_not_called()

    def test_poll_continues_without_browser_and_reconnects_after_failure(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, False, True]
        first, second = Mock(), Mock()
        first.poll_once.side_effect = ConnectionError('offline')
        second.poll_once.return_value = (SimpleNamespace(pk=1, phase='WAIT_POSITION'), False)
        factory = Mock(side_effect=[first, second])
        with patch.object(listener, 'close_old_connections'), self.assertLogs('plc_listener'):
            listener.poll_loop(stop, .25, 5, factory)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(second.poll_once.call_count, 2)
        first.plc.disconnect.assert_called_once()
        second.plc.disconnect.assert_called_once()
        self.assertEqual([c.args[0] for c in stop.wait.call_args_list], [5, .25, .25])

    def test_initial_missing_configuration_is_retried(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        service = Mock()
        service.poll_once.return_value = (None, False)
        factory = Mock(side_effect=[RuntimeError('PLC not configured'), service])
        with patch.object(listener, 'close_old_connections'), self.assertLogs('plc_listener'):
            listener.poll_loop(stop, .25, 5, factory)
        service.poll_once.assert_called_once()

    @override_settings(PLC_LISTENER_AUTO_START=False)
    def test_disabled_listener_never_starts_thread(self):
        with patch.object(listener.threading, 'Thread') as thread:
            listener.start_listener()
        thread.assert_not_called()

    def test_management_commands_do_not_start_listener(self):
        from .apps import WorkflowConfig
        for command in ('test', 'migrate', 'collectstatic', 'run_workflow_worker'):
            with patch('sys.argv', ['manage.py', command]), patch.object(listener, 'start_listener') as start:
                WorkflowConfig.ready(None)
            start.assert_not_called()
