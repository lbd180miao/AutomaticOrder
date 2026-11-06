"""Cloud-template endpoint integration; isolated database and no camera or PLC I/O."""
import copy
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse, resolve, Resolver404

from .models import RackLocationRecipe
from .tests_cloud_match import fixture


@override_settings(MIDDLEWARE=[item for item in settings.MIDDLEWARE if not item.startswith('whitenoise.')])
class CloudMatchEditorTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        override = override_settings(MEDIA_ROOT=str(self.root))
        override.enable()
        self.addCleanup(override.disable)
        self.cloud, self.config, self.metadata = fixture()
        np.save(self.root/'frame.npy', self.cloud)
        cv2.imwrite(str(self.root/'frame_image2d.png'), np.zeros((80, 80, 3), np.uint8))
        (self.root/'frame.units.json').write_text('{"unit":"mm"}')
        self.original = {'unrelated': 'preserve', 'dual_point': {'algorithm': 'Projection'},
                         'dual_point_camera_reference': {'measurement': {'points': ['old']}}}
        self.recipe = RackLocationRecipe.objects.create(recipe_name='cloud-match-test', roi_config=self.original)

    def post(self, endpoint, data):
        return self.client.post(reverse('vision:rack_dual_point_'+endpoint), json.dumps(data), content_type='application/json')

    def prepare(self, **extra):
        response = self.post('prepare', {'pointcloud_token': 'frame.npy', 'recipe_id': self.recipe.pk,
                                         'source': 'rvc_camera', **extra})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def payload(self):
        prepared = self.prepare()
        return {'pointcloud_token': 'frame.npy', 'source': 'rvc_camera', 'recipe_id': self.recipe.pk,
                'image_token': prepared['image_token'], 'cloud_token': prepared['cloud_token'],
                'config': self.config}

    def test_cloud_template_roundtrip_without_mode_selection(self):
        payload = self.payload()
        self.assertEqual(self.post('cloud_match', payload).status_code, 400)
        saved = self.post('cloud_match', {**payload, 'action': 'save_template'})
        self.assertEqual(saved.status_code, 200, saved.content)
        self.recipe.refresh_from_db()
        self.assertIn('cloud_match_reference', self.recipe.roi_config)
        for key, value in self.original.items():
            self.assertEqual(self.recipe.roi_config[key], value)
        result = self.post('cloud_match', payload)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()['result']['success'])
        self.assertFalse(result.json()['plc_publish_allowed'])
        loaded = self.prepare()
        self.assertEqual(loaded['config'], self.config)
        self.assertIn('measurement', loaded['reference'])
        self.assertNotIn('points', loaded['reference'])

    def test_old_mode_cannot_restore_edge_algorithm_or_reference(self):
        for mode in (None, 'edges', 'cloud_match'):
            loaded = self.prepare(localization_mode=mode)
            self.assertEqual(loaded['config'], {'imageSize': [80, 80], 'rois': []})
            self.assertIsNone(loaded['reference'])
            response = self.post('save', {'image_token': loaded['image_token'], 'recipe_id': self.recipe.pk,
                                         'config': self.config, 'localization_mode': mode})
            self.assertEqual(response.status_code, 200, response.content)
            self.recipe.refresh_from_db()
            self.assertEqual(self.recipe.roi_config['cloud_match_config'], self.config)
            self.assertEqual(self.recipe.roi_config['dual_point'], self.original['dual_point'])
            self.recipe.roi_config = copy.deepcopy(self.original)
            self.recipe.save(update_fields=['roi_config'])

    def test_saved_regions_load_without_gray_edge_detection(self):
        payload = self.payload()
        self.assertEqual(self.post('save', payload).status_code, 200)
        self.assertEqual(self.prepare()['config'], self.config)
        self.recipe.refresh_from_db()
        self.assertEqual({k: v for k, v in self.recipe.roi_config.items() if k != 'cloud_match_config'}, self.original)

    def test_original_image_and_depth_preview(self):
        data = self.prepare()
        response = self.client.get(data['image_url'])
        self.assertEqual(response.status_code, 200)
        response.close()
        response = self.client.get(data['depth_preview_url'])
        self.assertEqual(response.status_code, 200)
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape, (80, 80, 3))
        self.assertEqual(self.client.get(reverse('vision:rack_dual_point_depth')+'?token=forged').status_code, 400)
        np.save(self.root/'frame.npy', self.cloud + 1)
        self.assertEqual(self.client.get(data['depth_preview_url']).status_code, 400)

    def test_changed_frame_rejected_by_matching_and_teaching(self):
        payload = self.payload()
        np.save(self.root/'frame.npy', self.cloud + [1, 0, 0])
        for action in ('evaluate', 'save_template'):
            self.assertEqual(self.post('cloud_match', {**payload, 'action': action}).status_code, 400)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config, self.original)

    def test_forged_and_changed_image_rejected(self):
        payload = self.payload()
        self.assertEqual(self.post('save', {**payload, 'image_token': 'forged'}).status_code, 400)
        (self.root/'frame_image2d.png').write_bytes(b'changed')
        self.assertEqual(self.post('save', payload).status_code, 400)
        self.assertEqual(self.post('cloud_match', {**payload, 'action': 'save_template'}).status_code, 400)

    def test_invalid_regions_do_not_change_recipe(self):
        payload = self.payload()
        configs = []
        wrong_size = copy.deepcopy(self.config); wrong_size['imageSize'] = [1440, 1080]; configs.append(wrong_size)
        missing = copy.deepcopy(self.config); missing['rois'].pop(); configs.append(missing)
        outside = copy.deepcopy(self.config); outside['rois'][0]['x'] = -20; configs.append(outside)
        small = copy.deepcopy(self.config); small['rois'][0]['width'] = 2; configs.append(small)
        for config in configs:
            self.assertEqual(self.post('save', {**payload, 'config': config}).status_code, 400)
            self.assertEqual(self.post('cloud_match', {**payload, 'config': config, 'action': 'save_template'}).status_code, 400)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config, self.original)

    def test_traversal_and_missing_original_image_rejected(self):
        self.assertEqual(self.post('prepare', {'pointcloud_token': '../outside.npy'}).status_code, 400)
        (self.root/'frame_image2d.png').unlink()
        self.assertEqual(self.post('prepare', {'pointcloud_token': 'frame.npy'}).status_code, 400)

    def test_removed_algorithm_routes_are_unavailable(self):
        paths = ['dual-point/'+name for name in ('auto-rois', 'test', 'forensics', 'evaluate', 'teach')]
        paths += ['workbench/'+name for name in ('calculate', 'save', 'spatial-teach')]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve('/vision/api/rack-location/'+path+'/')

    def test_editor_is_in_existing_workbench(self):
        response = self.client.get(reverse('vision:rack_locator_panel'))
        self.assertContains(response, 'dp-canvas')
        self.assertContains(response, 'dp-depth-canvas')
        self.assertContains(response, 'id="dp-save-standard"')
        self.assertContains(response, '定位算法：点云模板匹配')
        for removed in ('dp-auto-rois', 'dp-algorithm', 'dp-localization-mode', 'dp-mode'):
            self.assertNotContains(response, f'id="{removed}"')
        self.assertNotContains(response, 'value="edges"')
        self.assertNotContains(response, 'value="legacy"')
        self.assertContains(response, 'rack_dual_point.js')
        self.assertContains(response, 'data-mode="dual"')
        self.assertContains(response, 'id="dp-evaluate"')
        self.assertContains(response, '标准模板 XYZ')
        self.assertContains(response, '差值 ΔXYZ')
        for removed in ('dp-fields', 'dp-transfer-fields', 'dp-json', 'dp-quality', 'dp-gate-status'):
            self.assertNotContains(response, f'id="{removed}"')
        self.assertNotContains(response, '<details id="dp-panel"')
