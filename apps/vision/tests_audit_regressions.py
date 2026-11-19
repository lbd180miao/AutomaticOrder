import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from django.test import SimpleTestCase, TestCase, RequestFactory, override_settings


class ContinuousRecoveryTests(SimpleTestCase):
    def test_inference_error_recovers_and_each_ng_is_durable(self):
        from .foam_live import LiveFoamRuntime
        from .foam_ng_log import recent, record
        from apps.devices.adapters.camera import CameraAdapter
        detector = Mock()
        states = iter(['error', 'FALLEN', 'FALLEN', 'NORMAL'])
        def detect(frame, timestamp, frame_id):
            state = next(states, 'NORMAL')
            if state == 'error':
                raise ValueError('bad frame')
            return dict(state=state, sides={}, frame_id=frame_id, timestamp=timestamp, elapsed_ms=1)
        detector.process.side_effect = detect
        def capture(*args, **kwargs):
            time.sleep(.02)
            return np.zeros((48, 64), np.uint8)
        live = LiveFoamRuntime()
        attempts = []
        def flaky_record(key, result):
            attempts.append(key)
            if len(attempts) == 1:
                raise sqlite3.OperationalError('database temporarily locked')
            record(key, result)
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)), patch(
            'apps.vision.foam_live.FoamStreamInspector', return_value=detector
        ), patch.object(CameraAdapter, 'acquire_frame', side_effect=capture), patch.object(
            CameraAdapter, 'decode_frame', side_effect=lambda f:f
        ), patch.object(CameraAdapter, 'close_worker'), patch.object(
            CameraAdapter, '_stream_active', False
        ), patch('apps.devices.adapters.plc.PLCAdapter.write_point', side_effect=AssertionError('PLC write')), patch(
            'apps.vision.foam_ng_log.record', side_effect=flaky_record
        ):
            try:
                live.start()
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    if (live.status()['result'] or {}).get('state') == 'NORMAL':
                        break
                    time.sleep(.02)
                self.assertTrue(live.status()['running'])
                self.assertEqual(live.status()['result']['state'], 'NORMAL')
                self.assertEqual(len(recent()), 2)
                self.assertEqual(attempts[0], attempts[1])
                self.assertTrue(all(json.loads(raw)['state'] == 'FALLEN' for _, raw in recent()))
            finally:
                live.stop()
            self.assertEqual(len(recent()), 2)

    def test_packaging_copies_only_required_templates(self):
        from tools.packaging_resources import copy_resources, ROOT, UI_ASSET_PATHS
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            with sqlite3.connect(target / 'db.sqlite3') as db:
                db.execute('CREATE TABLE vision_visionrecipe (standard_template_config TEXT, threshold_config TEXT)')
            db.close()
            for relative in UI_ASSET_PATHS:
                dest = target / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / 'static/devices/icons' / dest.name, dest)
            copy_resources(target)
            files = {p.relative_to(target / 'media').as_posix() for p in (target / 'media').rglob('*') if p.is_file()}
            self.assertEqual(files, {'vision/foam_stream_templates/pic2/' + name for name in ('profile.json','far.png','near.png')})
            from .algorithms.foam_stream import FoamStreamInspector
            FoamStreamInspector(target / 'media/vision/foam_stream_templates/pic2/profile.json')


class LatestRackTests(TestCase):
    def test_failed_latest_task_does_not_show_previous_ok(self):
        from .models import VisionTask, RackLocationResult
        from apps.devices.views import status
        old = VisionTask.objects.create(task_type='RACK_LOCATING', is_production=True, status='SUCCESS')
        RackLocationResult.objects.create(vision_task=old, side='LEFT', is_success=True)
        latest = VisionTask.objects.create(task_type='RACK_LOCATING', is_production=True, status='FAILED', error_message='capture disconnected')
        response = status(RequestFactory().get('/devices/status/', {'section':'rack'}))
        self.assertContains(response, 'capture disconnected')
        self.assertNotContains(response, '>OK<')

    def test_capture_failure_has_production_task(self):
        from apps.workflow.station_service import ExistingVisionGateway
        from .models import VisionTask
        with patch('apps.vision.plc_defaults.get_default_recipe', return_value=Mock(pk=1,layer_no=1)), patch(
            'apps.vision.rack_location.Rack3DLocator.acquire_workbench', side_effect=RuntimeError('camera disconnected')
        ), patch('apps.workflow.station_service.record'):
            with self.assertRaisesRegex(RuntimeError, 'camera disconnected'):
                ExistingVisionGateway(service=Mock())._capture_position_job()
        task = VisionTask.objects.get()
        self.assertTrue(task.is_production)
        self.assertEqual(task.status, 'FAILED')
        self.assertIsNotNone(task.finished_at)
