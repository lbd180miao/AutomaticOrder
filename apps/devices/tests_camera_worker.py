"""Persistent camera request lifecycle regression checks."""
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from .adapters.camera import CameraAdapter
from .adapters import hik_capture_worker as worker


class PersistentCameraTests(SimpleTestCase):
    def test_reuse_and_reconfigure(self):
        with tempfile.TemporaryDirectory() as directory:
            feature = Path(directory) / 'camera.mfs'
            feature.write_text('settings')
            result = Path(directory) / 'result.json'
            payload = {'feature_file': str(feature), 'result_path': str(result)}
            process = Mock()
            process.poll.return_value = None
            def respond(line):
                Path(json.loads(line)['result_path']).write_text(json.dumps(
                    {'success': True, 'image_path': 'fresh.bmp'}))
            process.stdin.write.side_effect = respond
            try:
                with patch('apps.devices.adapters.camera.subprocess.Popen', return_value=process) as spawn:
                    for _ in range(2):
                        self.assertEqual(CameraAdapter()._persistent_capture(['python'], payload, result), 'fresh.bmp')
                        result.unlink()
                    self.assertEqual(spawn.call_count, 1)
                    stamp = feature.stat().st_mtime_ns + 1000000000
                    os.utime(feature, ns=(stamp, stamp))
                    CameraAdapter()._persistent_capture(['python'], payload, result)
                    self.assertEqual(spawn.call_count, 2)
            finally:
                CameraAdapter.close_worker()
            self.assertIsNone(CameraAdapter._worker)
            self.assertTrue(process.stdin.close.called)

    def test_request_frames_and_release_on_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{n}.json' for n in range(2)]
            stream = io.StringIO(''.join(json.dumps({'result_path': str(p)}) + '\n' for p in paths))
            closed = []
            def frames(payload):
                try:
                    yield 'first.bmp'
                    yield 'second.bmp'
                finally:
                    closed.append(True)
            with patch.object(worker.sys, 'stdin', stream), patch.object(worker, '_prepare_runtime'), \
                 patch.object(worker, '_official_mvs_session', side_effect=frames) as factory:
                worker.serve({})
            factory.assert_called_once()
            self.assertEqual([json.loads(p.read_text())['image_path'] for p in paths],
                             ['first.bmp', 'second.bmp'])
            self.assertEqual(closed, [True])

    def test_reconnect_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{n}.json' for n in range(2)]
            stream = io.StringIO(''.join(json.dumps({'result_path': str(p)}) + '\n' for p in paths))
            def failure():
                raise RuntimeError('disconnected')
                yield
            def success():
                yield 'reconnected.bmp'
            with patch.object(worker.sys, 'stdin', stream), patch.object(worker, '_prepare_runtime'), \
                 patch.object(worker, '_official_mvs_session', side_effect=[failure(), success()]):
                worker.serve({})
            self.assertFalse(json.loads(paths[0].read_text())['success'])
            self.assertEqual(json.loads(paths[1].read_text())['image_path'], 'reconnected.bmp')
