"""Audit-only reproductions; isolated test database and mocked hardware."""
import ast
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
from django.test import TestCase, SimpleTestCase, RequestFactory


class AuditFindings(SimpleTestCase):
    def test_packaging_filter_removes_required_foam_images(self):
        from tools.packaging_resources import is_visual_data, is_ui_asset
        for name in ('far.png', 'near.png'):
            relative = 'media/vision/foam_stream_templates/pic2/' + name
            self.assertTrue((ROOT / relative).is_file())
            self.assertTrue(is_visual_data(relative) and not is_ui_asset(relative))
        print('REPRODUCED: required foam images are excluded by AGVControl.spec filter')

    def test_algorithm_error_stops_capture_without_restart(self):
        import numpy as np
        from apps.vision.foam_live import LiveFoamRuntime
        from apps.devices.adapters.camera import CameraAdapter
        runtime = LiveFoamRuntime()
        detector = Mock()
        detector.process.side_effect = ValueError('single bad inference frame')
        def capture(*args, **kwargs):
            time.sleep(.02)
            return np.zeros((48, 64), dtype=np.uint8)
        with patch('apps.vision.foam_live.FoamStreamInspector', return_value=detector), patch.object(
            CameraAdapter, 'acquire_frame', side_effect=capture
        ), patch.object(CameraAdapter, 'decode_frame', side_effect=lambda frame: frame), patch.object(CameraAdapter, 'close_worker'):
            try:
                runtime.start()
                for thread in runtime.threads:
                    thread.join(2)
                self.assertTrue(runtime.halt.is_set())
                self.assertFalse(any(thread.is_alive() for thread in runtime.threads))
                self.assertFalse(runtime.status()['running'])
                print('REPRODUCED: one inference exception terminates both runtime threads')
            finally:
                runtime.stop()


class StatusFinding(TestCase):
    def test_failed_latest_task_displays_old_success(self):
        from apps.vision.models import VisionTask, RackLocationResult
        from apps.devices.views import status
        old = VisionTask.objects.create(task_type='RACK_LOCATING', is_production=True, status='SUCCESS')
        previous = RackLocationResult.objects.create(vision_task=old, side='LEFT', is_success=True)
        latest = VisionTask.objects.create(task_type='RACK_LOCATING', is_production=True, status='FAILED', error_message='capture disconnected')
        with patch('apps.devices.views.render') as render:
            status(RequestFactory().get('/devices/status/', {'section': 'rack'}))
        shown = render.call_args.args[2]['rack']
        self.assertEqual(shown.pk, previous.pk)
        self.assertNotEqual(shown.vision_task_id, latest.pk)
        self.assertTrue(shown.is_success)
        print('REPRODUCED: latest failed task is hidden and old successful result remains selected')


if __name__ == '__main__':
    count = 0
    for folder in ('apps', 'AutomaticOrder', 'mes_gateway_project', 'rvc_service'):
        for path in (ROOT / folder).rglob('*.py'):
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            count += 1
    print(f'Python syntax parsed: {count} files')
    from django.test.runner import DiscoverRunner
    sys.exit(bool(DiscoverRunner(verbosity=1, interactive=False).run_tests(['__main__'])))
