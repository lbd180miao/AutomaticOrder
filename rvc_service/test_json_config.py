import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import PyRVC as RVC
from rvc_service.camera_controller import RvcCameraController, RvcConfigError, RvcControllerError


class JsonConfigTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'rvc.json'
        self.data = {'capture_mode': 2, 'exposure_time_3d': 37, 'gain_3d': 12.5,
                     'roi_width': 640, 'roi_height': 480, 'noise_removal_distance': 17.0,
                     'enable_2d_in_capture': False, 'hdr_exposuretime_content_1': 19}
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def test_normal_mode_is_not_relabelled_as_legacy_robust(self):
        controller = RvcCameraController(self.path)
        self.assertEqual(controller.state.mode, 'Normal')

    def test_sdk_options_include_filter_roi_hdr_and_correct_mode(self):
        self.data['capture_mode'] = 4
        self.write()
        controller = RvcCameraController(self.path)
        options, mode = controller._build_options('X2', {})
        self.assertEqual(mode, 'Ultra')
        self.assertEqual(options.capture_mode, RVC.CaptureMode_Ultra)
        self.assertEqual(options.roi.width, 640)
        self.assertAlmostEqual(options.noise_removal_distance, 17)
        self.assertEqual(options.GetHDRExposureTimeContent(0), 19)
        self.assertFalse(options.enable_2d_in_capture)

    def test_capture_reloads_file_and_explicit_override_is_temporary(self):
        controller = RvcCameraController(self.path)
        camera = Mock()
        camera.GetPointMap.return_value.IsValid.return_value = False
        controller._dev = SimpleNamespace(family='X2', opened=True, camera=camera,
                                         info=SimpleNamespace(), ip='test')
        self.data['exposure_time_3d'] = 43
        self.write()
        for override, expected in [(None, 43), (51, 51), (None, 43)]:
            with self.assertRaisesRegex(RvcControllerError, '点云无效'):
                controller.capture(Path(self.folder.name), exposure_3d=override)
            self.assertEqual(camera.Capture.call_args.args[0].exposure_time_3d, expected)
        camera.LoadCaptureOptionParameters.assert_not_called()

    def test_ui_setting_persists_without_losing_other_fields(self):
        controller = RvcCameraController(self.path)
        controller.set_exposure(exposure_3d=42)
        controller.set_mode('Ultra')
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['exposure_time_3d'], 42)
        self.assertEqual(saved['capture_mode'], 4)
        self.assertEqual(saved['roi_width'], 640)

    def test_missing_or_invalid_config_fails_without_default_fallback(self):
        self.path.write_text('invalid')
        with self.assertRaises(RvcConfigError):
            RvcCameraController(self.path)
        with self.assertRaises(RvcConfigError):
            RvcCameraController(self.path.with_name('missing.json'))
