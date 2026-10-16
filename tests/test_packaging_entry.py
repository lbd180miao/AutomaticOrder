"""Entry-point regression tests; no camera or running Django server required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run
from apps.devices.adapters import hik_capture_worker


class PackagingEntryTests(unittest.TestCase):
    def test_official_capture_does_not_import_legacy_binding(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            payload = {'output_dir': directory, 'feature_file': 'camera.mfs'}
            with patch.object(hik_capture_worker, '_prepare_runtime'), \
                 patch.object(hik_capture_worker, '_capture_with_official_mvs', return_value='frame.bmp'), \
                 patch.object(hik_capture_worker.importlib, 'import_module') as legacy:
                self.assertEqual(hik_capture_worker.capture(payload), 'frame.bmp')
                legacy.assert_not_called()

    def test_enumeration_does_not_require_frame_grabber_plugins(self):
        sdk = Mock()
        sdk.MV_GIGE_DEVICE, sdk.MV_USB_DEVICE = 1, 4
        sdk.MvCamera.MV_CC_Initialize.return_value = 0
        sdk.MvCamera.MV_CC_EnumDevices.return_value = 0x8000000c
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, \
             patch.object(hik_capture_worker.Path, 'exists', return_value=True), \
             patch.object(hik_capture_worker.importlib, 'import_module', return_value=sdk):
            with self.assertRaisesRegex(RuntimeError, '动态加载 DLL 失败'):
                hik_capture_worker._capture_with_official_mvs({'output_dir': directory})
        self.assertEqual(sdk.MvCamera.MV_CC_EnumDevices.call_args.args[0], 5)
        sdk.MvCamera.MV_CC_Finalize.assert_called_once()

    def test_hik_dispatch_preserves_payload_without_server_start(self):
        payload = '{"camera_serial": "test"}'
        worker = SimpleNamespace(main=lambda argv: (23, argv))
        with patch.dict(sys.modules, {'apps.devices.adapters.hik_capture_worker': worker}):
            self.assertEqual(run.main(['--hik-capture', payload]), (23, [payload]))

    def test_worker_reports_capture_error_to_parent(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = Path(directory) / 'result.json'
            payload = json.dumps({'result_path': str(result)})
            with patch.object(hik_capture_worker, 'capture', side_effect=RuntimeError('SDK unavailable')):
                self.assertEqual(hik_capture_worker.main([payload]), 1)
            self.assertEqual(json.loads(result.read_text()),
                             {'success': False, 'error': 'SDK unavailable'})

    def test_executable_style_dispatch_rejects_invalid_payload(self):
        result = subprocess.run([sys.executable, str(ROOT / 'run.py'),
                                 '--hik-capture', 'invalid-json'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stderr)['success'])
        self.assertNotIn('AutomaticOrder: threads=', result.stdout)


if __name__ == '__main__':
    unittest.main()
