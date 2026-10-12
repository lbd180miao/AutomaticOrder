"""Regression tests for scene substitution and truncated ROIs masquerading as noise."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from django.test import SimpleTestCase, override_settings
from .rack_input import capture_input, plane_roi, cloud_identity
from .rack_location import Rack3DLocator, RackLocationService
from .models import RackLocationRecipe


class RackInputTests(SimpleTestCase):
    def setUp(self):
        yy, xx = np.mgrid[:12, :12]
        self.cloud = np.stack([xx, yy, np.full_like(xx, 1500)], axis=2).astype(float)
        self.recipe = RackLocationRecipe(pk=8, layer_count=3)

    def test_capture_failure_never_substitutes_offline_or_sample_cloud(self):
        provider = Mock()
        provider.capture.side_effect = RuntimeError('camera disconnected')
        with patch('apps.vision.rack_location.build_sample_pointcloud') as sample, \
                patch('apps.vision.rack_location._load_offline_pic_pointcloud') as offline:
            locator = Rack3DLocator(frame_provider=provider)
            with patch.object(locator, '_select_recipe', return_value=self.recipe), \
                    patch.object(locator, '_persist_frame') as persist:
                with self.assertRaisesRegex(ValueError, 'camera disconnected'):
                    locator.capture(recipe_id=8)
                persist.assert_not_called()
            service = RackLocationService(frame_provider=provider)
            with patch('apps.vision.rack_location.RackLocationRecipe.objects.filter') as lookup, \
                    patch.object(service, '_persist_workbench_frame') as persist:
                lookup.return_value.first.return_value = self.recipe
                with self.assertRaisesRegex(ValueError, 'camera disconnected'):
                    service.capture_workbench(recipe_id=8)
                persist.assert_not_called()
            sample.assert_not_called()
            offline.assert_not_called()

    def test_provider_fallback_and_invalid_real_frames_are_rejected(self):
        for frame in [
            {'source':'sample_fallback', 'organized_pointcloud':self.cloud},
            {'source':'docs_pic_offline', 'organized_pointcloud':self.cloud},
            {'source':'rvc_camera'},
            {'source':'rvc_camera', 'organized_pointcloud':np.zeros((12,12,3))},
            {'source':'rvc_camera', 'organized_pointcloud':np.ones((144,3))},
        ]:
            with self.subTest(source=frame['source']):
                with self.assertRaises(ValueError):
                    capture_input(Mock(capture=Mock(return_value=frame)), self.recipe, 1, 1)

    @override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=False)
    def test_demo_requires_explicit_server_setting(self):
        with self.assertRaises(ValueError):
            capture_input(Mock(capture=Mock(return_value={'source':'sample_forced'})), self.recipe, 1, 1)

    @override_settings(VISION_RACK_LOCATION_FORCE_SAMPLE=True)
    def test_explicit_demo_uses_process_independent_seed(self):
        provider = Mock(capture=Mock(return_value={'source':'sample_forced'}))
        with patch('apps.vision.rack_location.build_sample_pointcloud', return_value=self.cloud) as sample:
            capture_input(provider, self.recipe, 1, 1)
            first = sample.call_args.kwargs['seed']
            capture_input(provider, self.recipe, 1, 1)
            self.assertEqual(first, sample.call_args.kwargs['seed'])

    def test_numpy_rgb_image_does_not_trigger_fallback(self):
        frame={'source':'rvc_camera','organized_pointcloud':self.cloud,'image_2d':np.zeros((12,12,3),dtype=np.uint8)}
        service = RackLocationService(frame_provider=Mock(capture=Mock(return_value=frame)))
        with patch.object(service, '_persist_workbench_frame', return_value=('test.npy','/test.jpg',12,12)) as persist:
            result = service.capture_workbench()
        self.assertEqual(result['source'], 'rvc_camera')
        self.assertIs(persist.call_args.args[1], frame['image_2d'])
        np.testing.assert_array_equal(persist.call_args.args[0], self.cloud)

    def test_resolution_mismatch_fails_instead_of_clamping(self):
        raw = {'x':963,'y':3,'w':72,'h':615}
        with self.assertRaisesRegex(ValueError, '640×480'):
            plane_roi(raw,640,480,'plane3')
        self.assertEqual(plane_roi(raw,1440,1080,'plane3'),raw)

    def test_already_clamped_history_roi_is_rejected(self):
        rois={name:{'x':0,'y':0,'w':12,'h':12} for name in ('plane1','plane2','plane3')}
        rois['plane2']['h']=1
        with self.assertRaisesRegex(ValueError, '至少 2'):
            RackLocationService._crop_local_template_clouds(self.cloud,rois)

    def test_fractional_roi_preserves_full_requested_area(self):
        self.assertEqual(plane_roi({'x':1.3,'y':2.4,'w':3.5,'h':4.7},12,12,'plane1'),
                         {'x':1,'y':2,'w':4,'h':6})

    def test_capture_provenance_survives_persist_and_reload(self):
        service=RackLocationService()
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=root) as directory, override_settings(MEDIA_ROOT=directory):
            token,_,_,_=service._persist_workbench_frame(self.cloud,capture_metadata={'source':'rvc_camera'})
            loaded=service._load_workbench_pointcloud(token)
            data=service._frame_metadata(token,loaded)
            self.assertEqual(data['source'],'rvc_camera')
            self.assertEqual(data['pointcloud_sha256'],cloud_identity(self.cloud)['pointcloud_sha256'])
            loaded[0,0,2]+=10
            with self.assertRaisesRegex(ValueError,'不一致'):
                service._frame_metadata(token,loaded)

    def test_identity_distinguishes_shapes_and_geometry_but_not_dtype(self):
        first=cloud_identity(self.cloud)
        self.assertEqual(first,cloud_identity(self.cloud.astype('float32')))
        other=self.cloud.copy(); other[0,0,2]+=1
        self.assertNotEqual(first['pointcloud_sha256'],cloud_identity(other)['pointcloud_sha256'])
        self.assertNotEqual(first['pointcloud_sha256'],cloud_identity(self.cloud.reshape(6,24,3))['pointcloud_sha256'])
