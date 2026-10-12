"""Endpoint integration uses the isolated Django test database, never PLC I/O."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import cv2
import numpy as np
from django.test import TestCase, override_settings
from django.conf import settings
from django.urls import reverse

from .models import RackLocationRecipe
from .tests_dual_point import fixture


@override_settings(MIDDLEWARE=[item for item in settings.MIDDLEWARE if not item.startswith('whitenoise.')])
class DualPointEditorTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings_override = override_settings(MEDIA_ROOT=str(self.root))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        image, cloud, self.config, *_ = fixture()
        self.config['imageSize'] = [320, 220]
        np.save(self.root/'frame.npy', cloud)
        cv2.imwrite(str(self.root/'frame_image2d.png'), image)
        self.original = {'target_roi': {'x': 10, 'y': 10, 'w': 20, 'h': 20},
                         'local_template_rois': {'plane1': {'x': 5}}, 'unrelated': 'preserve'}
        self.recipe = RackLocationRecipe.objects.create(recipe_name='dual-point-test-only', roi_config=self.original)

    def post(self, endpoint, data):
        return self.client.post(reverse('vision:rack_dual_point_'+endpoint), json.dumps(data), content_type='application/json')

    def prepare(self):
        response = self.post('prepare', {'pointcloud_token': 'frame.npy', 'recipe_id': self.recipe.pk, 'source': 'rvc_camera'})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_prepare_returns_actual_image_and_2d_draft(self):
        data = self.prepare()
        self.assertEqual([data['width'], data['height']], [320, 220])
        self.assertEqual(data['config']['rois'], [])
        response = self.client.get(data['image_url'])
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_depth_preview_uses_same_pointcloud_and_rejects_changed_file(self):
        data = self.prepare()
        response = self.client.get(data['depth_preview_url'])
        self.assertEqual(response.status_code, 200)
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape, (220, 320, 3))
        self.assertEqual(self.client.get(reverse('vision:rack_dual_point_depth')+'?token=forged').status_code, 400)
        np.save(self.root/'frame.npy', np.zeros((10, 10, 3)))
        self.assertEqual(self.client.get(data['depth_preview_url']).status_code, 400)
        response = self.post('evaluate', {'recipe_id': self.recipe.pk, 'pointcloud_token': 'frame.npy',
            'image_token': data['image_token'], 'cloud_token': data['cloud_token'],
            'config': self.config, 'coordinate_system': 'camera'})
        self.assertEqual(response.status_code, 400)

    def test_prepare_keeps_canvas_available_when_auto_edges_fail(self):
        self.config['validationStatus'] = '2d_draft_not_production_validated'
        self.recipe.roi_config['dual_point'] = self.config
        self.recipe.save(update_fields=['roi_config'])
        cv2.imwrite(str(self.root/'frame_image2d.png'), np.zeros((220, 320), np.uint8))
        data = self.prepare()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['config']['rois']), 4)
        self.assertIn('P1_horizontal', data['three_d_status'])

    def test_save_preserves_other_configuration_and_loads_back(self):
        data = self.prepare()
        response = self.post('save', {'image_token': data['image_token'], 'recipe_id': self.recipe.pk, 'config': self.config})
        self.assertEqual(response.status_code, 200, response.content)
        self.recipe.refresh_from_db()
        self.assertEqual({k:v for k,v in self.recipe.roi_config.items() if k != 'dual_point'}, self.original)
        self.assertEqual(self.prepare()['config'], self.config)

    def test_test_endpoint_returns_lines_and_pixels_without_compensation(self):
        data = self.prepare()
        self.config['compareAlgorithms'] = True
        self.config['maxAlgorithmDifferencePx'] = 1
        response = self.post('test', {'image_token': data['image_token'], 'config': self.config})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(len(result['result']['lines']), 4)
        self.assertEqual(len(result['result']['pixels']), 2)
        self.assertFalse(result['three_d_success'])
        self.assertFalse(result['plc_publish_allowed'])

    def test_resolution_change_and_out_of_bounds_rejected(self):
        data = self.prepare()
        self.config['imageSize'] = [1440, 1080]
        response = self.post('save', {'image_token': data['image_token'], 'recipe_id': self.recipe.pk, 'config': self.config})
        self.assertEqual(response.status_code, 400)
        self.config['imageSize'] = [320, 220]
        self.config['rois'][0]['x'] = -20
        self.assertEqual(self.post('test', {'image_token': data['image_token'], 'config': self.config}).status_code, 400)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config, self.original)

    def test_forged_or_changed_image_is_rejected(self):
        data = self.prepare()
        self.assertEqual(self.post('test', {'image_token': 'forged', 'config': self.config}).status_code, 400)
        (self.root/'frame_image2d.png').write_bytes(b'changed')
        self.assertEqual(self.post('test', {'image_token': data['image_token'], 'config': self.config}).status_code, 400)

    def test_traversal_and_depth_preview_fallback_rejected(self):
        self.assertEqual(self.post('prepare', {'pointcloud_token': '../outside.npy'}).status_code, 400)
        (self.root/'frame_image2d.png').unlink()
        self.assertEqual(self.post('prepare', {'pointcloud_token': 'frame.npy'}).status_code, 400)

    def test_editor_is_in_existing_workbench(self):
        response = self.client.get(reverse('vision:rack_locator_panel'))
        self.assertContains(response, 'dp-canvas')
        self.assertContains(response, 'dp-depth-canvas')
        self.assertContains(response, 'id="dp-save-standard"')
        self.assertContains(response, 'rack_dual_point.js')
        self.assertContains(response, 'rl-canvas')
        self.assertContains(response, 'data-mode="dual"')
        self.assertContains(response, 'id="dp-evaluate"')
        self.assertContains(response, '标准模板 XYZ')
        self.assertContains(response, '差值 ΔXYZ')
        for removed in ('dp-fields', 'dp-transfer-fields', 'dp-json', 'dp-quality', 'dp-gate-status'):
            self.assertNotContains(response, f'id="{removed}"')
        self.assertNotContains(response, '<details id="dp-panel"')

    def test_forensics_needs_no_image_rois_or_calibration(self):
        (self.root/'frame_image2d.png').unlink()
        response = self.post('forensics', {'pointcloud_token':'frame.npy'})
        self.assertEqual(response.status_code, 200, response.content)
        report = response.json()['report']
        self.assertGreater(report['valid_points'], 0)
        self.assertIsNone(report['unit'])
        self.assertFalse(report['production_ready'])
        self.assertEqual(self.post('forensics', {'pointcloud_token':'../outside.npy'}).status_code, 400)

    def test_missing_contract_does_not_publish_or_offer_teach(self):
        data = self.prepare()
        response = self.post('evaluate', {'image_token':data['image_token'], 'pointcloud_token':'frame.npy',
                                         'config':self.config, 'recipe_id':self.recipe.pk})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertFalse(result['result']['success'])
        self.assertIsNone(result['teach_token'])
        self.assertFalse(result['compensation']['success'])
        self.assertFalse(result['plc_publish_allowed'])

    def test_verified_evaluation_signed_teach_and_new_frame_compensation(self):
        from .tests_dual_point import next_frame
        image, cloud, config, metadata, hand_eye, pose = fixture()
        package = {'image':image,'cloud':cloud,'metadata':metadata,'hand_eye':hand_eye,
                   'robot_pose':pose,'pixel_index_map':None}
        data = self.prepare()
        body = {'image_token':data['image_token'], 'pointcloud_token':'frame.npy',
                'config':config, 'recipe_id':self.recipe.pk}
        with patch('apps.vision.rack_dual_point_views._frame_package', return_value=package):
            evaluated = self.post('evaluate', body).json()
            self.assertTrue(evaluated['result']['success'], evaluated)
            teach = {'recipe_id':self.recipe.pk, 'teach_token':evaluated['teach_token']}
            self.assertEqual(self.post('teach', teach).status_code, 400)  # config not saved
            self.assertEqual(self.post('save', body).status_code, 200)
            self.assertEqual(self.post('teach', teach).status_code, 200)
            self.recipe.refresh_from_db()
            self.assertEqual(self.recipe.roi_config['unrelated'], 'preserve')
            self.assertIn('dual_point_reference', self.recipe.roi_config)
            reused = self.post('evaluate', body).json()
            self.assertEqual(reused['compensation']['errorCode'], 'REUSED_TEACH_FRAME')
            package['metadata'] = next_frame(metadata)
            current = self.post('evaluate', body).json()
            self.assertTrue(current['compensation']['success'], current)
            self.assertFalse(current['plc_publish_allowed'])
            self.assertEqual(self.post('teach', {**teach,'recipe_id':self.recipe.pk+1}).status_code, 400)
            config['maxOffsetMm'][0][0] = 19
            self.post('save', body)
            self.assertEqual(self.post('teach', teach).status_code, 400)

    def test_camera_template_without_hand_eye_or_robot_pose(self):
        image, cloud, config, metadata, _, _ = fixture()
        contract = metadata['dual_point_contract']
        for key in ('robot_frame', 'matrix_unit', 'transform_mode', 'hand_eye_direction',
                    'pose_direction', 'pose_frame_id', 'pose_synchronized', 'calibration_verified'):
            contract.pop(key, None)
        package = {'image': image, 'cloud': cloud, 'metadata': metadata,
                   'hand_eye': None, 'robot_pose': None, 'pixel_index_map': None}
        prepared = self.prepare()
        body = {'image_token': prepared['image_token'], 'pointcloud_token': 'frame.npy',
                'config': config, 'recipe_id': self.recipe.pk, 'coordinate_system': 'camera'}
        with patch('apps.vision.rack_dual_point_views._frame_package', return_value=package):
            data = self.post('evaluate', body).json()
            self.assertTrue(data['result']['success'], data)
            self.assertEqual(data['result']['coordinateSystem'], 'camera')
            self.assertEqual(data['result']['unit'], 'mm')
            self.assertEqual(len(data['result']['points']), 2)
            for point in data['result']['points']:
                self.assertNotIn('robot', point)
                self.assertAlmostEqual(point['xyz'][2], 1000, places=3)
            self.assertFalse(data['compensation']['success'])
            taught = self.post('teach', {'recipe_id': self.recipe.pk, 'teach_token': data['teach_token']})
            self.assertEqual(taught.status_code, 200, taught.content)
            self.recipe.refresh_from_db()
            self.assertEqual(self.recipe.roi_config['dual_point'], config)
            self.assertEqual(self.recipe.roi_config['unrelated'], 'preserve')
            self.assertIn('dual_point_camera_reference', self.recipe.roi_config)
            self.assertNotIn('dual_point_reference', self.recipe.roi_config)
            self.assertEqual(self.prepare()['reference']['measurement']['coordinateSystem'], 'camera')
            self.assertIsNotNone(self.post('evaluate', body).json()['reference'])
            contract['cloud_frame'] = 'robot_base'
            rejected = self.post('evaluate', body).json()
            self.assertFalse(rejected['result']['success'])
            self.assertEqual(rejected['result']['errorCode'], 'COORDINATE_MISMATCH')

    def test_forged_teach_and_mismatched_image_are_rejected(self):
        self.assertEqual(self.post('teach', {'recipe_id':self.recipe.pk,'teach_token':'forged'}).status_code, 400)
        data = self.prepare()
        image, cloud, *_ = fixture()
        np.save(self.root/'other.npy', cloud)
        cv2.imwrite(str(self.root/'other_image2d.png'), image)
        response = self.post('evaluate', {'image_token':data['image_token'], 'pointcloud_token':'other.npy',
                                         'config':self.config, 'recipe_id':self.recipe.pk})
        self.assertEqual(response.status_code, 400)
