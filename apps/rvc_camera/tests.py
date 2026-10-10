import tempfile
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from . import apps
from .client import RvcCameraClient


class CaptureRequestTests(SimpleTestCase):
    @override_settings(AUTOMATIC_ORDER={'RVC_CAMERA': {'DEFAULT_MODE': ''}})
    def test_default_capture_does_not_force_mode(self):
        client = RvcCameraClient()
        with patch.object(client, '_post', return_value={}) as post:
            client.capture()
            self.assertNotIn('mode', post.call_args.args[1])
            client.capture(mode='Ultra')
            self.assertEqual(post.call_args.args[1]['mode'], 'Ultra')


class AutoStartTests(SimpleTestCase):
    def setUp(self):
        self.config = apps.RvcCameraConfig('apps.rvc_camera', __import__('apps.rvc_camera', fromlist=['']))
        self.addCleanup(apps._rvc_stop.clear)
        apps._rvc_stop.clear()

    def test_runserver_modes(self):
        for argv, env, expected in [
            (['manage.py', 'runserver'], {}, False),
            (['manage.py', 'runserver', '--noreload'], {}, True),
            (['manage.py', 'runserver'], {'RUN_MAIN': 'true'}, True),
            (['manage.py', 'migrate'], {}, False),
            (['run.py'], {}, True),
        ]:
            with self.subTest(argv=argv, env=env), patch.object(apps.sys, 'argv', argv), patch.dict(apps.os.environ, env, clear=True), patch.object(self.config, '_launch_rvc_service') as launch:
                self.config.ready()
                self.assertEqual(launch.called, expected)

    def test_existing_service_is_reused(self):
        with patch.object(apps, '_rvc_proc', None), patch.object(apps, '_service_alive', return_value=True), patch.object(apps.subprocess, 'Popen') as spawn:
            apps._ensure_rvc_service({})
            spawn.assert_not_called()

    def test_exited_child_restarts_and_logs(self):
        child = Mock()
        child.poll.return_value = 1
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder, override_settings(BASE_DIR=Path(folder), DATA_DIR=Path(folder)), patch.object(apps, '_rvc_proc', child), patch.object(apps, '_service_alive', return_value=False), patch.object(apps.subprocess, 'Popen') as spawn:
            apps._ensure_rvc_service({'CAMERA_IP': '169.254.10.202'})
            self.assertIn('8001', spawn.call_args.args[0])
            self.assertIn('--parent-stdin', spawn.call_args.args[0])
            self.assertEqual(spawn.call_args.kwargs['stdin'], subprocess.PIPE)
            self.assertEqual(spawn.call_args.kwargs['cwd'], folder)
            self.assertTrue((Path(folder) / 'logs/rvc-service.log').exists())

    def test_running_child_not_duplicated(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(apps, '_rvc_proc', child), patch.object(apps.subprocess, 'Popen') as spawn:
            apps._ensure_rvc_service({})
            spawn.assert_not_called()

    def test_monitor_retries_after_failure(self):
        with patch.object(apps, '_ensure_rvc_service', side_effect=[OSError('failed'), None]) as ensure, patch.object(apps._rvc_stop, 'wait', side_effect=[False, True]):
            apps._supervise_rvc_service({})
            self.assertEqual(ensure.call_count, 2)

    def test_shutdown_prevents_launch(self):
        apps._rvc_stop.set()
        with patch.object(apps.subprocess, 'Popen') as spawn:
            apps._ensure_rvc_service({})
            spawn.assert_not_called()

    def test_shutdown_closes_parent_pipe_and_waits(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(apps, '_rvc_proc', child):
            apps._stop_rvc_service()
            child.stdin.close.assert_called_once()
            child.wait.assert_called_once_with(timeout=12)
            child.kill.assert_not_called()
            self.assertIsNone(apps._rvc_proc)


class ParentLifetimeTests(SimpleTestCase):
    def test_parent_watch_does_not_block_native_imports(self):
        code = '''
import sys, threading
from pathlib import Path
from rvc_service.__main__ import _watch_parent
stopping = threading.Event()
threading.Thread(target=_watch_parent, args=(stopping,), daemon=True).start()
import numpy
import PyRVC
Path(sys.argv[1]).write_text('ready')
stopping.wait(30)
'''
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            marker = Path(folder) / 'ready'
            child = subprocess.Popen([sys.executable, '-c', code, str(marker)],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and time.monotonic() < deadline:
                    if child.poll() is not None:
                        break
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), 'Native import blocked while parent pipe is open')
                child.stdin.close()
                self.assertEqual(child.wait(timeout=5), 0)
            finally:
                if not child.stdin.closed:
                    child.stdin.close()
                if child.poll() is None:
                    child.kill()
                    child.wait()

    # Exercise the real entry point without loading or connecting any camera SDK.
    child_code = '''
import sys, time
from pathlib import Path
from types import SimpleNamespace
from rvc_service.__main__ import main
marker = Path(sys.argv[1])
controller = SimpleNamespace(system_shutdown=lambda: marker.write_text('released'))
server = SimpleNamespace(RequestHandlerClass=SimpleNamespace(controller=controller),
    handle_request=lambda: time.sleep(0.05), server_close=lambda: None)
sys.modules['rvc_service.server'] = SimpleNamespace(make_server=lambda *a, **k: server)
main(['--parent-stdin', '--no-auto-connect', '--output-dir', str(marker.parent)])
'''

    def test_pipe_close_releases_camera_and_exits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            marker = Path(folder) / 'released'
            child = subprocess.Popen([sys.executable, '-c', self.child_code, str(marker)],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
            try:
                child.stdin.close()
                self.assertEqual(child.wait(timeout=15), 0)
                self.assertEqual(marker.read_text(), 'released')
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_forced_web_exit_releases_camera(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            marker = Path(folder) / 'released'
            parent_code = '''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]],
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
print(child.pid, flush=True)
time.sleep(60)
'''
            parent = subprocess.Popen([sys.executable, '-c', parent_code,
                                       self.child_code, str(marker)], stdout=subprocess.PIPE,
                                      text=True)
            try:
                self.assertTrue(parent.stdout.readline().strip().isdigit())
                parent.kill()
                parent.wait(timeout=5)
                deadline = time.monotonic() + 15
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), 'Camera cleanup did not follow web process exit')
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait()
                parent.stdout.close()


