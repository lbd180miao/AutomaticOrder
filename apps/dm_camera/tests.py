from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError, DMCameraException
from apps.dm_camera.services import DMCameraService
from apps.dm_camera.models import DMCameraConfig
from apps.dm_camera.sdk.LW_DM_Type import LWTriggerMode
from apps.dm_camera.tofconfig import TofCameraConfig, TofConfigError


class DMCameraServiceConnectionRecoveryTests(TestCase):
    def setUp(self):
        self.service = DMCameraService()
        self.service._camera = None
        self.service._current_session = None

    def tearDown(self):
        self.service._camera = None
        self.service._current_session = None

    def test_connect_clears_failed_sdk_instance_so_next_retry_is_not_uninitialized(self):
        class FailingCamera:
            device_handle = None
            is_streaming = False

            def find_devices(self):
                raise DMCameraException("查找设备失败，错误码: 34")

            def disconnect(self):
                pass

        with patch('apps.dm_camera.services.DMCamera', FailingCamera):
            with self.assertRaises(DMCameraException):
                self.service.connect()

        self.assertIsNone(self.service._camera)

    def test_connect_releases_stale_unconnected_sdk_instance_before_new_connect(self):
        calls = []

        class StaleCamera:
            device_handle = None
            is_streaming = False

            def disconnect(self):
                calls.append('stale_disconnect')

        class FailingCamera:
            device_handle = None
            is_streaming = False

            def find_devices(self):
                raise DMCameraException("查找设备失败，错误码: 34")

            def disconnect(self):
                calls.append('new_disconnect')

        self.service._camera = StaleCamera()

        with patch('apps.dm_camera.services.DMCamera', FailingCamera):
            with self.assertRaises(DMCameraException):
                self.service.connect()

        self.assertEqual(calls, ['stale_disconnect', 'new_disconnect'])
        self.assertIsNone(self.service._camera)

    def test_disconnect_clears_stale_sdk_instance_even_when_sdk_disconnect_fails(self):
        class StaleCamera:
            device_handle = object()
            is_streaming = True

            def disconnect(self):
                raise DMCameraException("停止数据流失败，错误码: 34")

        self.service._camera = StaleCamera()

        with self.assertRaises(DMCameraException):
            self.service.disconnect()

        self.assertIsNone(self.service._camera)
        self.assertIsNone(self.service._current_session)

    def test_connect_cleans_up_camera_when_database_config_lookup_fails(self):
        cameras = []

        class ConnectedCamera:
            device_handle = object()
            is_streaming = False

            def __init__(self):
                self.disconnected = False
                cameras.append(self)

            def find_devices(self):
                return [SimpleNamespace(handle=7, sn='DB-FAIL-SN', type='TOF', ip='192.168.1.9')]

            def connect(self, device):
                return device

            def disconnect(self):
                self.disconnected = True
                self.device_handle = None

        with patch('apps.dm_camera.services.DMCamera', ConnectedCamera), patch(
            'apps.dm_camera.services.DMCameraConfig.objects.filter',
            side_effect=RuntimeError('database unavailable'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
                self.service.connect()

        self.assertTrue(cameras[0].disconnected)
        self.assertIsNone(self.service._camera)


class DMCameraTofConfigApplicationTests(TestCase):
    class FakeCamera:
        def __init__(self):
            self.device_handle = object()
            self.is_streaming = False
            self.configure_calls = []
            self.filter_calls = []
            self.events = []
            self.disconnected = False

        def configure_camera(self, **kwargs):
            self.configure_calls.append(kwargs)
            self.events.append(('configure_camera', kwargs))

        def set_filters(self, **kwargs):
            self.filter_calls.append(kwargs)
            self.events.append(('set_filters', kwargs))

        def disconnect(self):
            self.disconnected = True
            self.device_handle = None

    def setUp(self):
        self.service = DMCameraService()
        self.service._camera = None
        self.service._current_session = None
        self.config = DMCameraConfig.objects.create(
            name='database-values-must-not-be-used',
            frame_rate=99,
            exposure_time=9999,
            trigger_mode='HARD',
            confidence_filter_enable=True,
            confidence_threshold=91,
            flying_pixels_filter_enable=True,
            flying_pixels_threshold=92,
            spatial_filter_enable=True,
            spatial_threshold=93,
            is_active=True,
        )

    def tearDown(self):
        self.service._camera = None
        self.service._current_session = None

    def test_apply_config_maps_all_tofconfig_trigger_modes_and_configures_before_filters(self):
        trigger_modes = {
            'ACTIVE': LWTriggerMode.LW_TRIGGER_ACTIVE,
            'SOFT': LWTriggerMode.LW_TRIGGER_SOFT,
            'HARD': LWTriggerMode.LW_TRIGGER_HARD,
        }

        for trigger_mode, expected_trigger_mode in trigger_modes.items():
            with self.subTest(trigger_mode=trigger_mode):
                camera = self.FakeCamera()
                self.service._camera = camera
                tof_config = TofCameraConfig(
                    frame_rate=10,
                    exposure_time=1004,
                    trigger_mode=trigger_mode,
                    confidence=(False, 15),
                    flying_pixels=(False, 5),
                    spatial=(False, 2),
                )
                configure_values = {
                    'frame_rate': 10,
                    'exposure_time': 1004,
                    'trigger_mode': expected_trigger_mode,
                }
                filter_values = {
                    'confidence': (False, 15),
                    'flying_pixels': (False, 5),
                    'spatial': (False, 2),
                }

                with patch('apps.dm_camera.services.load_tof_config', return_value=tof_config):
                    self.service._apply_config(self.config)

                self.assertEqual(camera.events, [
                    ('configure_camera', configure_values),
                    ('set_filters', filter_values),
                ])

    def test_apply_config_rejects_unknown_tofconfig_trigger_mode(self):
        self.service._camera = self.FakeCamera()
        tof_config = TofCameraConfig(
            frame_rate=10,
            exposure_time=1004,
            trigger_mode='UNKNOWN',
            confidence=(False, 15),
            flying_pixels=(False, 5),
            spatial=(False, 2),
        )

        with patch('apps.dm_camera.services.load_tof_config', return_value=tof_config):
            with self.assertRaisesRegex(DMCameraException, 'trigger_mode.*UNKNOWN') as raised:
                self.service._apply_config(self.config)

        self.assertIsInstance(raised.exception, DMCameraConfigurationError)

    def test_connect_converts_tofconfig_error_and_cleans_up_camera(self):
        cameras = []

        class ConnectableFakeCamera(self.FakeCamera):
            def __init__(self):
                super().__init__()
                cameras.append(self)

            def find_devices(self):
                return [SimpleNamespace(handle=7, sn='TOF-SN', type='TOF', ip='192.168.1.8')]

            def connect(self, device):
                return device

        with patch('apps.dm_camera.services.DMCamera', ConnectableFakeCamera), patch(
            'apps.dm_camera.services.load_tof_config',
            side_effect=TofConfigError('tofconfig invalid JSON at byte 12'),
        ):
            with self.assertRaisesRegex(DMCameraException, 'tofconfig invalid JSON at byte 12') as raised:
                self.service.connect()

        self.assertIsInstance(raised.exception, DMCameraConfigurationError)
        self.assertTrue(cameras[0].disconnected)
        self.assertIsNone(self.service._camera)


class DMCameraDemoTemplateTests(TestCase):
    def test_demo_page_guards_camera_actions_and_connects_selected_device(self):
        source = (Path(settings.BASE_DIR) / 'templates' / 'dm_camera_demo.html').read_text(encoding='utf-8')

        self.assertIn('let isBusy = false;', source)
        self.assertIn('function setBusy', source)
        self.assertIn('let selectedDeviceSn = null;', source)
        self.assertIn("device_sn: selectedDeviceSn", source)
        self.assertIn('async function syncStatus', source)
        self.assertIn('diagnosticPanel', source)
        self.assertIn('btnDiagnostics', source)
        self.assertIn('btnRecoverConnect', source)
        self.assertIn('function renderDiagnostics', source)


class DMCameraApiDiagnosticsTests(TestCase):
    def test_connect_error_returns_structured_sdk_error_detail(self):
        class FakeService:
            def connect(self, **kwargs):
                raise DMCameraException("打开设备失败，错误码: 52")

        with patch('apps.dm_camera.views.dm_service', FakeService()):
            response = self.client.post(
                reverse('dm_camera:connect'),
                data='{}',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error_detail']['code'], 52)
        self.assertEqual(payload['error_detail']['name'], 'LW_RETURN_DEVICE_OCCUPIED')
        self.assertIn('占用', payload['error_detail']['suggestion'])

    def test_diagnostics_api_returns_sdk_status_and_devices(self):
        class FakeService:
            def get_status(self):
                return {'connected': False, 'streaming': False, 'session': None, 'device_info': None}

            def find_devices(self):
                return [{'sn': 'SN-01', 'ip': '192.168.1.200', 'type': 'LWP-D322-WI'}]

        with patch('apps.dm_camera.views.dm_service', FakeService()):
            response = self.client.get(reverse('dm_camera:diagnostics'))

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertTrue(data['sdk']['dll_exists'])
        self.assertEqual(data['status']['connected'], False)
        self.assertEqual(data['devices'][0]['sn'], 'SN-01')

    def test_recover_api_disconnects_finds_connects_and_optionally_starts_stream(self):
        calls = []

        class FakeService:
            def disconnect(self):
                calls.append('disconnect')

            def find_devices(self):
                calls.append('find')
                return [{'sn': 'SN-01', 'ip': '192.168.1.200'}]

            def connect(self, device_sn=None, config_id=None):
                calls.append(('connect', device_sn, config_id))
                return {'device_sn': device_sn, 'device_ip': '192.168.1.200'}

            def start_stream(self):
                calls.append('start')
                return {'status': 'streaming'}

            def get_status(self):
                return {'connected': True, 'streaming': True, 'session': {'device_sn': 'SN-01'}}

        with patch('apps.dm_camera.views.dm_service', FakeService()):
            response = self.client.post(
                reverse('dm_camera:recover'),
                data='{"device_sn": "SN-01", "start_stream": true}',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ['disconnect', 'find', ('connect', 'SN-01', None), 'start'])
        self.assertTrue(response.json()['data']['status']['streaming'])

    def test_recover_api_forces_stale_sdk_reset_when_disconnect_reports_uninitialized(self):
        calls = []

        class FakeService:
            def __init__(self):
                self._camera = object()

            def disconnect(self):
                calls.append('disconnect')
                raise DMCameraException("停止数据流失败，错误码: 34")

            def find_devices(self):
                calls.append(('find', self._camera is None))
                return [{'sn': 'SN-01', 'ip': '192.168.1.200'}]

            def connect(self, device_sn=None, config_id=None):
                calls.append(('connect', self._camera is None, device_sn, config_id))
                return {'device_sn': device_sn, 'device_ip': '192.168.1.200'}

            def get_status(self):
                return {'connected': True, 'streaming': False, 'session': {'device_sn': 'SN-01'}}

        fake_service = FakeService()

        with patch('apps.dm_camera.views.dm_service', fake_service):
            response = self.client.post(
                reverse('dm_camera:recover'),
                data='{"device_sn": "SN-01", "start_stream": false}',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [
            'disconnect',
            ('find', True),
            ('connect', True, 'SN-01', None),
        ])


class TofConfigTests(TestCase):
    @staticmethod
    def _valid_payload():
        return {
            'fps_value': 10,
            'exposure_time': [1004],
            'trigger_mode': 0,
            'is_confidence_filtering': True,
            'confidence_filter_value': 15,
            'is_fly_filtering': False,
            'fly_filter_value': 5,
            'is_spatial_filtering': False,
            'spatial_filter_value': 2,
        }

    def _load_payload(self, payload):
        import json
        from tempfile import TemporaryDirectory

        from apps.dm_camera.tofconfig import load_tof_config

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'tofconfig'
            plain = json.dumps(payload).encode('utf-8')
            path.write_bytes(bytes(byte ^ 0xFF for byte in plain))
            return load_tof_config(path)

    def _load_plain_bytes(self, plain):
        from tempfile import TemporaryDirectory

        from apps.dm_camera.tofconfig import load_tof_config

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'tofconfig'
            path.write_bytes(bytes(byte ^ 0xFF for byte in plain))
            return load_tof_config(path)

    def test_maps_valid_tof_camera_configuration(self):
        from apps.dm_camera.tofconfig import TofCameraConfig

        config = self._load_payload(self._valid_payload())

        self.assertIsInstance(config, TofCameraConfig)
        self.assertEqual(config.frame_rate, 10)
        self.assertEqual(config.exposure_time, 1004)
        self.assertEqual(config.trigger_mode, 'ACTIVE')
        self.assertEqual(config.confidence, (True, 15))
        self.assertEqual(config.flying_pixels, (False, 5))
        self.assertEqual(config.spatial, (False, 2))

    def test_maps_all_supported_trigger_modes(self):
        expected = {0: 'ACTIVE', 1: 'SOFT', 2: 'HARD'}

        for raw_mode, name in expected.items():
            with self.subTest(raw_mode=raw_mode):
                payload = self._valid_payload()
                payload['trigger_mode'] = raw_mode
                self.assertEqual(self._load_payload(payload).trigger_mode, name)

    def test_loads_repository_tofconfig(self):
        from apps.dm_camera.tofconfig import load_tof_config

        config = load_tof_config()

        self.assertEqual(config.frame_rate, 10)
        self.assertEqual(config.exposure_time, 1004)
        self.assertEqual(config.spatial, (False, 2))

    def test_missing_file_raises_tof_config_error(self):
        from tempfile import TemporaryDirectory

        from apps.dm_camera.tofconfig import TofConfigError, load_tof_config

        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / 'missing-tofconfig'
            with self.assertRaisesRegex(TofConfigError, 'missing|not found'):
                load_tof_config(missing)

    def test_invalid_utf8_raises_tof_config_error(self):
        from apps.dm_camera.tofconfig import TofConfigError

        with self.assertRaisesRegex(TofConfigError, 'UTF-8'):
            self._load_plain_bytes(b'\xff')

    def test_damaged_json_raises_tof_config_error(self):
        from apps.dm_camera.tofconfig import TofConfigError

        with self.assertRaisesRegex(TofConfigError, 'JSON'):
            self._load_plain_bytes(b'{not valid json')

    def test_non_object_root_raises_tof_config_error(self):
        from apps.dm_camera.tofconfig import TofConfigError

        with self.assertRaisesRegex(TofConfigError, 'root|object'):
            self._load_payload([])

    def test_missing_required_field_raises_tof_config_error(self):
        from apps.dm_camera.tofconfig import TofConfigError

        payload = self._valid_payload()
        del payload['fps_value']

        with self.assertRaisesRegex(TofConfigError, 'fps_value'):
            self._load_payload(payload)

    def test_boolean_filter_fields_require_actual_booleans(self):
        from apps.dm_camera.tofconfig import TofConfigError

        fields = (
            'is_confidence_filtering',
            'is_fly_filtering',
            'is_spatial_filtering',
        )
        for field in fields:
            with self.subTest(field=field):
                payload = self._valid_payload()
                payload[field] = 1
                with self.assertRaisesRegex(TofConfigError, field):
                    self._load_payload(payload)

    def test_integer_fields_reject_booleans_strings_and_invalid_ranges(self):
        from apps.dm_camera.tofconfig import TofConfigError

        invalid_values = {
            'fps_value': (True, '10', 0, -1),
            'confidence_filter_value': (True, '15', -1),
            'fly_filter_value': (False, '5', -1),
            'spatial_filter_value': (True, '2', -1),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = self._valid_payload()
                    payload[field] = value
                    with self.assertRaisesRegex(TofConfigError, field):
                        self._load_payload(payload)

    def test_exposure_time_requires_non_empty_list(self):
        from apps.dm_camera.tofconfig import TofConfigError

        for value in (None, 1004, '1004', []):
            with self.subTest(value=value):
                payload = self._valid_payload()
                payload['exposure_time'] = value
                with self.assertRaisesRegex(TofConfigError, 'exposure_time'):
                    self._load_payload(payload)

    def test_exposure_time_first_item_requires_positive_integer(self):
        from apps.dm_camera.tofconfig import TofConfigError

        for value in (True, '1004', 0, -1):
            with self.subTest(value=value):
                payload = self._valid_payload()
                payload['exposure_time'] = [value]
                with self.assertRaisesRegex(TofConfigError, 'exposure_time'):
                    self._load_payload(payload)

    def test_unknown_trigger_mode_raises_tof_config_error(self):
        from apps.dm_camera.tofconfig import TofConfigError

        payload = self._valid_payload()
        payload['trigger_mode'] = 99

        with self.assertRaisesRegex(TofConfigError, 'trigger_mode'):
            self._load_payload(payload)
