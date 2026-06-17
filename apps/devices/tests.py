import sys
import types
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import os

from django.test import SimpleTestCase, override_settings

from apps.core.constants import DeviceType
from apps.devices.adapters.camera import CameraAdapter
from apps.devices.adapters import hik_capture_worker
from apps.devices.adapters.simulated import SimulatedDeviceAdapter
from apps.devices.services import get_device_adapter


class FakeHikCamera:
    instances = []

    def __init__(self, output_dir, format='PNG', quality=5):
        self.output_dir = output_dir
        self.format = format
        self.quality = quality
        self.open_calls = []
        FakeHikCamera.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def open(self, camera_ip=None, pc_ip=None):
        self.open_calls.append((camera_ip, pc_ip))

    def capture(self):
        return str(Path(self.output_dir) / 'image.png')


def fake_chg_hik_module():
    module = types.ModuleType('chg_hik')
    module.Camera = FakeHikCamera
    return module


class CameraAdapterTests(SimpleTestCase):
    def setUp(self):
        FakeHikCamera.instances = []

    def test_capture_uses_ip_direct_mode_when_camera_and_pc_ip_are_configured(self):
        with TemporaryDirectory() as tmpdir:
            settings_value = {
                'HIK_CAMERA': {
                    'OUTPUT_DIR': tmpdir,
                    'SDK_LIB_DIR': 'C:/MVS/Runtime',
                    'CAMERA_IP': '192.168.1.64',
                    'PC_IP': '192.168.1.100',
                    'FORMAT': 'JPEG',
                    'QUALITY': 95,
                    'RUN_IN_SUBPROCESS': False,
                }
            }
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch('os.add_dll_directory') as add_dll_directory:
                    with mock.patch.dict('os.environ', {}, clear=True):
                        with mock.patch.dict(sys.modules, {'chg_hik': fake_chg_hik_module()}):
                            result = CameraAdapter().capture('CAM01', 'RACK_LOCATING')
                        self.assertIn('C:/MVS/Runtime', os.environ['PATH'])
                        self.assertEqual(os.environ['HCMVS_LIB'], 'C:/MVS/Runtime')

        add_dll_directory.assert_called_once_with('C:/MVS/Runtime')

        camera = FakeHikCamera.instances[0]
        self.assertEqual(camera.output_dir, Path(tmpdir).resolve().as_posix())
        self.assertEqual(camera.format, 'JPEG')
        self.assertEqual(camera.quality, 95)
        self.assertEqual(camera.open_calls, [('192.168.1.64', '192.168.1.100')])
        self.assertEqual(
            result,
            {
                'success': True,
                'image_path': str(Path(tmpdir).resolve() / 'image.png'),
                'camera_code': 'CAM01',
                'task_type': 'RACK_LOCATING',
            },
        )

    def test_capture_skips_dll_directory_setup_when_runtime_dir_is_not_configured(self):
        with TemporaryDirectory() as tmpdir:
            settings_value = {
                'HIK_CAMERA': {
                    'OUTPUT_DIR': tmpdir,
                    'CAMERA_IP': '192.168.1.64',
                    'PC_IP': '192.168.1.100',
                    'FORMAT': 'JPEG',
                    'QUALITY': 95,
                    'RUN_IN_SUBPROCESS': False,
                }
            }
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch.dict(sys.modules, {'chg_hik': fake_chg_hik_module()}):
                    result = CameraAdapter().capture('CAM01', 'RACK_LOCATING')

        camera = FakeHikCamera.instances[0]
        self.assertEqual(camera.output_dir, Path(tmpdir).resolve().as_posix())
        self.assertEqual(camera.format, 'JPEG')
        self.assertEqual(camera.quality, 95)
        self.assertEqual(camera.open_calls, [('192.168.1.64', '192.168.1.100')])
        self.assertEqual(
            result,
            {
                'success': True,
                'image_path': str(Path(tmpdir).resolve() / 'image.png'),
                'camera_code': 'CAM01',
                'task_type': 'RACK_LOCATING',
            },
        )

    def test_capture_uses_enumeration_mode_when_ip_settings_are_empty(self):
        with TemporaryDirectory() as tmpdir:
            settings_value = {
                'HIK_CAMERA': {
                    'OUTPUT_DIR': tmpdir,
                    'CAMERA_IP': '',
                    'PC_IP': '',
                    'FORMAT': 'PNG',
                    'QUALITY': 5,
                    'RUN_IN_SUBPROCESS': False,
                }
            }
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch.dict(sys.modules, {'chg_hik': fake_chg_hik_module()}):
                    CameraAdapter().capture('CAM02', 'FOAM_INSPECTION')

        camera = FakeHikCamera.instances[0]
        self.assertEqual(camera.open_calls, [(None, None)])

    def test_capture_raises_clear_error_when_chg_hik_is_not_installed(self):
        with TemporaryDirectory() as tmpdir:
            settings_value = {'HIK_CAMERA': {'OUTPUT_DIR': tmpdir, 'RUN_IN_SUBPROCESS': False}}
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch.dict(sys.modules, {'chg_hik': None}):
                    with self.assertRaisesRegex(RuntimeError, 'chg_hik'):
                        CameraAdapter().capture('CAM03', 'RACK_LOCATING')

    def test_import_chg_hik_retries_project_venv_site_packages(self):
        module = fake_chg_hik_module()
        import_calls = []

        def fake_import(name):
            import_calls.append(name)
            if len(import_calls) == 1:
                raise ImportError('missing chg_hik from active python')
            return module

        with mock.patch.object(Path, 'exists', return_value=True):
            with mock.patch('importlib.import_module', side_effect=fake_import):
                with mock.patch.object(sys, 'path', []):
                    imported = CameraAdapter()._import_chg_hik()

        self.assertIs(imported, module)
        self.assertEqual(import_calls, ['chg_hik', 'chg_hik'])
        self.assertTrue(any('.venv' in path and 'site-packages' in path for path in sys.path))

    def test_capture_raises_worker_error_without_directly_importing_chg_hik(self):
        completed = mock.Mock()
        completed.returncode = 1
        completed.stdout = ''
        completed.stderr = '{"error": "native sdk exited"}'

        with TemporaryDirectory() as tmpdir:
            settings_value = {'HIK_CAMERA': {'OUTPUT_DIR': tmpdir}}
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch('subprocess.run', return_value=completed):
                    with mock.patch.object(CameraAdapter, '_import_chg_hik') as import_chg_hik:
                        with self.assertRaisesRegex(RuntimeError, 'native sdk exited'):
                            CameraAdapter().capture('CAM04', 'FOAM_INSPECTION')

        import_chg_hik.assert_not_called()

    def test_capture_reads_worker_result_file_when_sdk_prints_logs(self):
        def fake_run(command, **kwargs):
            payload = json.loads(command[-1])
            Path(payload['result_path']).write_text(
                json.dumps({'success': True, 'image_path': 'D:/capture/foam.png'}),
                encoding='utf-8',
            )
            completed = mock.Mock()
            completed.returncode = 0
            completed.stdout = '=== 初始化相机 ===\n关闭相机...\n'
            completed.stderr = ''
            return completed

        with TemporaryDirectory() as tmpdir:
            settings_value = {'HIK_CAMERA': {'OUTPUT_DIR': tmpdir}}
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch('subprocess.run', side_effect=fake_run):
                    result = CameraAdapter().capture('CAM04', 'FOAM_INSPECTION')

        self.assertEqual(result['image_path'], 'D:/capture/foam.png')

    def test_capture_raises_clear_error_when_worker_result_file_is_empty(self):
        def fake_run(command, **kwargs):
            payload = json.loads(command[-1])
            Path(payload['result_path']).write_text('', encoding='utf-8')
            completed = mock.Mock()
            completed.returncode = 0
            completed.stdout = '=== 初始化相机 ===\n关闭相机...\n'
            completed.stderr = ''
            return completed

        with TemporaryDirectory() as tmpdir:
            settings_value = {'HIK_CAMERA': {'OUTPUT_DIR': tmpdir}}
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch('subprocess.run', side_effect=fake_run):
                    with self.assertRaisesRegex(RuntimeError, 'invalid worker result'):
                        CameraAdapter().capture('CAM04', 'FOAM_INSPECTION')

    def test_capture_accepts_success_result_when_worker_exits_nonzero_after_capture(self):
        def fake_run(command, **kwargs):
            payload = json.loads(command[-1])
            Path(payload['result_path']).write_text(
                json.dumps({'success': True, 'image_path': 'D:/capture/foam.png'}),
                encoding='utf-8',
            )
            completed = mock.Mock()
            completed.returncode = 1
            completed.stdout = '=== 初始化相机 ===\n关闭相机...\n'
            completed.stderr = ''
            return completed

        with TemporaryDirectory() as tmpdir:
            settings_value = {'HIK_CAMERA': {'OUTPUT_DIR': tmpdir}}
            with override_settings(AUTOMATIC_ORDER=settings_value):
                with mock.patch('subprocess.run', side_effect=fake_run):
                    result = CameraAdapter().capture('CAM04', 'FOAM_INSPECTION')

        self.assertEqual(result['image_path'], 'D:/capture/foam.png')

    def test_get_device_adapter_returns_camera_adapter_for_camera_devices_when_not_simulated(self):
        settings_value = {'USE_SIMULATED_DEVICES': False}
        with override_settings(AUTOMATIC_ORDER=settings_value):
            adapter = get_device_adapter(device_type=DeviceType.INSPECT_CAMERA)

        self.assertIsInstance(adapter, CameraAdapter)

    def test_get_device_adapter_keeps_simulated_adapter_when_simulation_is_enabled(self):
        settings_value = {'USE_SIMULATED_DEVICES': True}
        with override_settings(AUTOMATIC_ORDER=settings_value):
            adapter = get_device_adapter(device_type=DeviceType.INSPECT_CAMERA)

        self.assertIsInstance(adapter, SimulatedDeviceAdapter)


class HikCaptureWorkerTests(SimpleTestCase):
    def test_capture_prefers_legacy_capture_images_and_returns_newest_image(self):
        def capture_images(output_dir, format='PNG', quality=5, camera_ip=None, pc_ip=None):
            image_path = Path(output_dir) / 'legacy_capture.png'
            image_path.write_bytes(b'fake image')
            return {'success': True, 'images_captured': 1, 'message': 'ok'}

        module = types.ModuleType('chg_hik')
        module.capture_images = capture_images

        with TemporaryDirectory() as tmpdir:
            payload = {
                'base_dir': tmpdir,
                'output_dir': tmpdir,
                'camera_ip': '169.254.160.253',
                'pc_ip': '169.254.160.95',
                'format': 'PNG',
                'quality': 5,
            }
            with mock.patch.dict(sys.modules, {'chg_hik': module}):
                image_path = hik_capture_worker.capture(payload)

        self.assertTrue(image_path.endswith('legacy_capture.png'))

    def test_capture_returns_image_path_when_close_fails_after_successful_capture(self):
        class CloseFailingCamera:
            def __init__(self, output_dir, format='PNG', quality=5):
                self.output_dir = output_dir

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                raise RuntimeError('close failed')

            def open(self, camera_ip=None, pc_ip=None):
                return None

            def capture(self):
                return str(Path(self.output_dir) / 'image.png')

            def close_camera(self):
                raise RuntimeError('close failed')

        module = types.ModuleType('chg_hik')
        module.Camera = CloseFailingCamera

        with TemporaryDirectory() as tmpdir:
            payload = {'base_dir': tmpdir, 'output_dir': tmpdir}
            with mock.patch.dict(sys.modules, {'chg_hik': module}):
                image_path = hik_capture_worker.capture(payload)

        self.assertTrue(image_path.endswith('image.png'))

    def test_capture_does_not_close_camera_after_successful_one_shot_capture(self):
        state = {'closed': False}

        class TrackingCamera:
            def __init__(self, output_dir, format='PNG', quality=5):
                self.output_dir = output_dir

            def open(self, camera_ip=None, pc_ip=None):
                return None

            def capture(self):
                return str(Path(self.output_dir) / 'image.png')

            def close_camera(self):
                state['closed'] = True

        module = types.ModuleType('chg_hik')
        module.Camera = TrackingCamera

        with TemporaryDirectory() as tmpdir:
            payload = {'base_dir': tmpdir, 'output_dir': tmpdir}
            with mock.patch.dict(sys.modules, {'chg_hik': module}):
                image_path = hik_capture_worker.capture(payload)

        self.assertTrue(image_path.endswith('image.png'))
        self.assertFalse(state['closed'])
