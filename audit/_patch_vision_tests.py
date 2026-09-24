# -*- coding: utf-8 -*-
"""一次性补丁：vision/tests.py 的料架帧提供者测试切换为 RVC。"""
from pathlib import Path

path = Path(r"D:\workspace2\AutomaticOrder\apps\vision\tests.py")
text = path.read_text(encoding="utf-8")

start = text.index("class DMCameraRackFrameProviderTests(TestCase):")
end = text.index("class RackLocationRecipe3DModelTests(TestCase):")

new_block = '''class RVCCameraRackFrameProviderTests(TestCase):
    def _recipe(self, name='Provider-POS-01-L1'):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        return Recipe.objects.create(
            recipe_name=name,
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            layer_count=3,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_provider_captures_pointcloud_from_rvc_service(self):
        from apps.vision.rack_location import RVCCameraRackFrameProvider

        recipe = self._recipe()

        class FakeRvcCameraService:
            calls = []

            def __init__(self):
                self._connected = False

            @property
            def is_connected(self):
                return self._connected

            def ensure_connected(self):
                self.calls.append('ensure_connected')
                self._connected = True

            def capture_frame_data(self, frame_type='POINTCLOUD', save_record=True, **kwargs):
                self.calls.append((frame_type, save_record))
                return {
                    'frame_type': frame_type,
                    'data': np.zeros((2, 2, 3), dtype=float),
                    'width': 2,
                    'height': 2,
                }

        with patch('apps.rvc_camera.services.RvcCameraService', FakeRvcCameraService):
            payload = RVCCameraRackFrameProvider().capture(recipe, position_no=1, layer_no=1)

        self.assertEqual(FakeRvcCameraService.calls, [
            'ensure_connected',
            ('POINTCLOUD', False),
        ])
        self.assertEqual(payload['source'], 'rvc_camera')
        self.assertEqual(payload['organized_pointcloud'].shape, (2, 2, 3))

    @override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=True)
    def test_provider_can_force_sample_without_touching_rvc_service(self):
        from apps.vision.rack_location import RVCCameraRackFrameProvider

        class UnexpectedRvcCameraService:
            def __init__(self):
                raise AssertionError('RVC service should not be instantiated')

        with patch('apps.rvc_camera.services.RvcCameraService', UnexpectedRvcCameraService):
            payload = RVCCameraRackFrameProvider().capture(self._recipe('Forced-Sample'), 1, 1)

        self.assertEqual(payload['source'], 'sample_forced')
        self.assertIn('raw_data_path', payload)

    def test_provider_propagates_rvc_configuration_error(self):
        from apps.rvc_camera.client import RvcCameraConfigurationError
        from apps.vision.rack_location import RVCCameraRackFrameProvider

        class MisconfiguredRvcCameraService:
            @property
            def is_connected(self):
                return False

            def ensure_connected(self):
                raise RvcCameraConfigurationError('unsupported capture mode')

        with patch('apps.rvc_camera.services.RvcCameraService', MisconfiguredRvcCameraService):
            with self.assertRaisesRegex(RvcCameraConfigurationError, 'unsupported capture mode'):
                RVCCameraRackFrameProvider().capture(self._recipe('Bad-Mode'), 1, 1)

    def test_provider_still_falls_back_for_non_configuration_error(self):
        from apps.vision.rack_location import RVCCameraRackFrameProvider

        class OfflineRvcCameraService:
            @property
            def is_connected(self):
                return False

            def ensure_connected(self):
                raise RuntimeError('camera offline')

        with patch('apps.rvc_camera.services.RvcCameraService', OfflineRvcCameraService):
            payload = RVCCameraRackFrameProvider().capture(self._recipe('Offline'), 1, 1)

        self.assertEqual(payload['source'], 'sample_fallback')
        self.assertEqual(payload['fallback_reason'], 'camera offline')

    def test_dm_provider_name_is_backward_compatible_alias(self):
        from apps.vision.rack_location import (
            DMCameraRackFrameProvider,
            RVCCameraRackFrameProvider,
        )
        self.assertIs(DMCameraRackFrameProvider, RVCCameraRackFrameProvider)


'''

text = text[:start] + new_block + text[end:]
path.write_text(text, encoding="utf-8")
print("vision/tests.py patched OK")
