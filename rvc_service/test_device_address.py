"""Device address regression tests; no hardware is opened."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from rvc_service.camera_controller import RvcCameraController, RvcControllerError
import PyRVC as RVC


class DeviceAddressTests(unittest.TestCase):
    def test_default_capture_uses_device_parameters(self):
        controller = RvcCameraController()
        camera = Mock()
        camera.GetPointMap.return_value.IsValid.return_value = False
        controller._dev = SimpleNamespace(family='X2', opened=True, camera=camera,
                                         info=SimpleNamespace(), ip='169.254.10.202')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            with self.assertRaisesRegex(RvcControllerError, '点云无效'):
                controller.capture(folder)
        camera.Capture.assert_called_once_with()
        camera.LoadCaptureOptionParameters.assert_not_called()

    def test_transform_type_matches_sdk_and_preview_channel(self):
        controller = RvcCameraController()
        for family, extra, options, expected in (
            ('X1', False, RVC.X1_CaptureOptions(), True),
            ('X2', False, RVC.X2_CaptureOptions(), RVC.CameraID_Left),
            ('X2', True, RVC.X2_CaptureOptions(), RVC.CameraID_Extra),
        ):
            with self.subTest(family=family, extra=extra):
                controller._dev = SimpleNamespace(family=family, info=SimpleNamespace(support_extra=extra))
                controller._set_transform_camera(options)
                self.assertEqual(options.transform_to_camera, expected)

    def test_discovery_address_wins_over_saved_network_config(self):
        device = Mock()
        device.GetDeviceInfo.return_value = (True, SimpleNamespace(port='169.254.10.202'))
        device.GetNetworkConfig.return_value = (0, b'169.254.35.81', b'255.255.0.0', b'0.0.0.0', 0)
        self.assertEqual(RvcCameraController._device_ip(device), '169.254.10.202')
        device.GetNetworkConfig.assert_not_called()

    def test_network_config_fallback(self):
        device = Mock()
        device.GetDeviceInfo.return_value = (True, SimpleNamespace(port='USB'))
        device.GetNetworkConfig.return_value = (0, b'169.254.10.202', b'255.255.0.0', b'0.0.0.0', 0)
        self.assertEqual(RvcCameraController._device_ip(device), '169.254.10.202')

    def test_subnet_mask_is_never_used_as_device_address(self):
        device = Mock()
        device.GetDeviceInfo.return_value = (True, SimpleNamespace(port=''))
        device.GetNetworkConfig.return_value = (0, b'', b'255.255.0.0', b'0.0.0.0', 0)
        self.assertEqual(RvcCameraController._device_ip(device), '')
