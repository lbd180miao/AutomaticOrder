"""All rack entry points use cloud registration, with no legacy geometry fallback."""
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import numpy as np
from django.test import TestCase, override_settings
from django.urls import resolve, Resolver404, reverse

from .models import RackLocationRecipe, RackLocationResult, VisionTask
from .rack_cloud_match import build_template, VERSION
from .rack_cloud_service import evaluate_cloud
from .rack_location import RackLocationService, Rack3DLocator, PlcVisionResultWriter, result_payload
from .tests_cloud_match import fixture


class CloudServiceTests(TestCase):
    def test_production_readiness_uses_cloud_regions_and_template(self):
        from apps.production.rack_recipe_service import _vision_readiness
        self.recipe.hand_eye_config = {'matrix': np.eye(4).tolist()}
        self.assertTrue(_vision_readiness(self.recipe)['ready'])
        self.recipe.roi_config.pop('cloud_match_reference')
        self.recipe.local_template_std = {'groups': {'A': {'old': True}}}
        status = _vision_readiness(self.recipe)
        self.assertFalse(status['template_ready'])
        self.assertIn('点云标准模板未保存', status['issues'])

    def test_duplicate_cloud_regions_do_not_pass_readiness(self):
        from apps.production.rack_recipe_service import _vision_readiness
        config = dict(self.config)
        config['rois'] = [self.config['rois'][0]] * 4
        self.recipe.roi_config['cloud_match_config'] = config
        self.assertFalse(_vision_readiness(self.recipe)['roi_complete'])

    def test_package_snapshot_excludes_old_plane_settings(self):
        from .offline_data_views import _merge_package_roi_config
        result = _merge_package_roi_config(self.recipe.roi_config, {
            'target_roi': {'x': 1}, 'local_template_rois': {'plane1': {}},
            'camera_roi': {'x': 10},
        })
        self.assertEqual(set(result), {
            'cloud_match_config', 'cloud_match_reference', 'camera_roi',
        })
        self.assertEqual(result['cloud_match_reference'], self.reference)

    @override_settings(MIDDLEWARE=[])
    def test_recipe_detail_counts_cloud_regions(self):
        response = self.client.get(reverse('vision:api_rack_location_recipe_detail',
                                           args=[self.recipe.pk]))
        self.assertEqual(response.status_code, 200)
        recipe = response.json()['recipe']
        self.assertEqual(recipe['roi_info']['configured_count'], 4)
        self.assertTrue(recipe['roi_info']['is_complete'])
        self.assertNotIn('local_template_std', recipe)

    def setUp(self):
        self.cloud, self.config, self.metadata = fixture()
        self.reference = build_template(self.cloud, self.config, self.metadata)
        self.recipe = RackLocationRecipe.objects.create(recipe_name='only-cloud', roi_config={
            'cloud_match_config': self.config, 'cloud_match_reference': self.reference,
            'spatial_rois': {'old': True}, 'local_template_rois': {'old': True},
        })
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        override = override_settings(MEDIA_ROOT=self.temp.name)
        override.enable(); self.addCleanup(override.disable)

    def test_facades_ignore_legacy_fields_and_persist_cloud_results(self):
        service = RackLocationService()
        token, *_ = service._persist_workbench_frame(self.cloud + [3, -2, 1], capture_metadata=self.metadata)
        for facade in (service, Rack3DLocator()):
            result = facade.calculate_workbench(token=token, recipe_id=self.recipe.pk, save_record=True)
            self.assertEqual(result['algorithm_version'], VERSION)
            self.assertTrue(result['locate_ok'])
            self.assertFalse(result['plc_publish_allowed'])
            record = RackLocationResult.objects.get(pk=result['result_id'])
            self.assertEqual(record.result_data['source'], 'cloud_match')
            self.assertEqual(result_payload(record)['algorithm_version'], VERSION)
        self.assertEqual(VisionTask.objects.count(), 2)

    def test_missing_cloud_template_never_uses_plane_template(self):
        self.recipe.roi_config.pop('cloud_match_reference')
        self.recipe.local_template_std = {'groups': {'A': {'old': True}}}
        self.recipe.save()
        with self.assertRaisesRegex(ValueError, '保存点云模板'):
            evaluate_cloud(self.recipe, self.cloud, self.metadata, save_record=True)
        self.assertFalse(RackLocationResult.objects.exists())

    def test_production_trigger_uses_matching_and_cannot_publish(self):
        provider = Mock(capture=Mock(return_value={
            'source': 'rvc_camera', 'organized_pointcloud': self.cloud,
            'metadata': self.metadata, 'image_2d': np.zeros((80, 80, 3), np.uint8),
        }))
        adapter = Mock()
        service = RackLocationService(frame_provider=provider, plc_writer=PlcVisionResultWriter(adapter=adapter))
        record = service.trigger(recipe_id=self.recipe.pk, layer_no=1, write_plc=True)
        self.assertTrue(record.is_success)
        self.assertEqual(record.result_data['algorithm_version'], VERSION)
        self.assertEqual(record.plc_write_status, 'REJECTED')
        adapter.send_rack_offsets.assert_not_called()
        provider.capture.assert_called_once()

    def test_bad_match_does_not_produce_robot_compensation(self):
        reference = dict(self.reference)
        reference['limits'] = {**reference['limits'], 'min_fitness': 1.1}
        self.recipe.roi_config['cloud_match_reference'] = reference
        result = evaluate_cloud(self.recipe, self.cloud, self.metadata, save_record=True)
        self.assertFalse(result['locate_ok'])
        self.assertIsNone(result['robot_result'])
        self.assertEqual(result['robot_groups'], {})
        self.assertFalse(RackLocationResult.objects.get(pk=result['result_id']).is_success)

    def test_second_api_service_uses_same_cloud_algorithm(self):
        from .rack_3d.services import RackPositioningService
        from .rack_3d.providers import OfflineDepthCameraProvider
        provider = OfflineDepthCameraProvider({'pointcloud': self.cloud, 'metadata': self.metadata})
        service = RackPositioningService(mode='OFFLINE', depth_camera_provider=provider,
                                         loaded_data={'pointcloud': self.cloud, 'metadata': self.metadata},
                                         hand_eye_matrix=np.eye(4), robot_pose_matrix=np.eye(4))
        result = service.execute_positioning(self.recipe.pk, 1, save=False)
        self.assertTrue(result['locate_ok'])
        self.assertEqual(result['algorithm_version'], VERSION)
        self.assertFalse(VisionTask.objects.exists())

    def test_historical_results_read_without_old_algorithm_modules(self):
        task = VisionTask.objects.create(task_type='RACK_LOCATING', status='SUCCESS')
        record = RackLocationResult.objects.create(vision_task=task, recipe=self.recipe, side='BOTH',
            result_data={'algorithm_version': 'LOCAL_TEMPLATE_3D_V2', 'local_template_cur': {'historical': True}})
        payload = result_payload(record)
        self.assertEqual(payload['algorithm_version'], 'LOCAL_TEMPLATE_3D_V2')
        with override_settings(MIDDLEWARE=[]):
            response = self.client.get(reverse('vision:rack_positioning_history'), {'recipe_id': self.recipe.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['history'][0]['id'], record.pk)

    def test_old_plane_and_template_routes_are_removed(self):
        for suffix in ('process/', 'detect/plane/', 'detect/edge/', 'detect/pillar/',
                       'default-params/', 'v2/template/build/', 'v2/compensation/compute/',
                       'v2/template/save/'):
            with self.subTest(suffix=suffix), self.assertRaises(Resolver404):
                resolve('/vision/rack-positioning/'+suffix)

    def test_package_reprocessing_uses_cloud_template(self):
        from .offline_data_service import OfflineDataPackageService
        service = OfflineDataPackageService(base_dir=Path(self.temp.name)/'packages')
        created = service.create_package(pointcloud=self.cloud, hand_eye_matrix=np.eye(4),
            robot_pose_matrix=np.eye(4), roi_config=self.recipe.roi_config, recipe=self.recipe,
            layer_no=1, camera_info={**self.metadata['camera'], 'source':'rvc_camera'})
        result = service.reprocess_package(created['package_name'], self.recipe.pk, 1)
        self.assertTrue(result['locate_ok'])
        self.assertEqual(result['algorithm_version'], VERSION)
