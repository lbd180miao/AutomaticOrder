"""rack_3d REST API 测试。Requirements: 26.4"""

import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.vision.models import RackLocationRecipe, RackLocationROI3DEnhanced, ROI3DType

from .test_services import ROIS, LAYER


class RackThreeDApiTest(TestCase):
    def setUp(self):
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='API-Demo-POS1-L2',
            position_no=1, layer_no=LAYER, layer_count=3,
            standard_x=Decimal('900'), standard_y=Decimal('530'), standard_z=Decimal('1220'),
            confidence_threshold=Decimal('0.5000'),
        )
        for roi_type, bounds in ROIS.items():
            RackLocationROI3DEnhanced.objects.create(
                recipe=self.recipe, roi_name=f'L{LAYER}-{roi_type}', roi_type=roi_type,
                position_no=1, layer_no=LAYER,
                **{k: Decimal(str(v)) for k, v in bounds.items()},
            )

    def _post(self, name, payload):
        return self.client.post(
            reverse(name), data=json.dumps(payload), content_type='application/json'
        )

    def test_recipes_list(self):
        resp = self.client.get(reverse('vision:rack_3d:recipes'))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['data'][0]['recipe_name'], 'API-Demo-POS1-L2')

    def test_recipe_rois(self):
        resp = self.client.get(
            reverse('vision:rack_3d:recipe_rois', args=[self.recipe.id]) + f'?layer_no={LAYER}'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['data']), 3)

    def test_capture_returns_preview(self):
        resp = self._post('vision:rack_3d:capture', {'recipe_id': self.recipe.id, 'layer_no': LAYER})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertGreater(data['point_count'], 0)
        self.assertTrue(len(data['preview_points']) > 0)
        self.assertIn('bounds', data)

    def test_calculate_success(self):
        resp = self._post('vision:rack_3d:calculate',
                          {'recipe_id': self.recipe.id, 'layer_no': LAYER, 'save': True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertTrue(data['is_success'], msg=data.get('error_message'))
        self.assertIn('result_id', data)
        self.assertAlmostEqual(data['actual_z'], 1220, delta=5)

    def test_calculate_missing_recipe_404(self):
        resp = self._post('vision:rack_3d:calculate', {'recipe_id': 999999, 'layer_no': 1})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()['success'])

    def test_upsert_roi_validates_bounds(self):
        resp = self._post('vision:rack_3d:upsert_roi', {
            'recipe_id': self.recipe.id, 'layer_no': 1, 'roi_type': ROI3DType.MAIN,
            'x_min': 10, 'x_max': 5, 'y_min': 0, 'y_max': 10, 'z_min': 0, 'z_max': 10,
        })
        self.assertEqual(resp.status_code, 400)

    def test_upsert_roi_creates(self):
        resp = self._post('vision:rack_3d:upsert_roi', {
            'recipe_id': self.recipe.id, 'layer_no': 1, 'roi_type': ROI3DType.MAIN,
            'x_min': 0, 'x_max': 10, 'y_min': 0, 'y_max': 10, 'z_min': 0, 'z_max': 10,
        })
        self.assertEqual(resp.status_code, 201)

    def test_update_coordinates(self):
        resp = self.client.patch(
            reverse('vision:rack_3d:update_coordinates', args=[self.recipe.id]),
            data=json.dumps({'standard_z': 1225.5}), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.recipe.refresh_from_db()
        self.assertEqual(float(self.recipe.standard_z), 1225.5)

    def test_results_history(self):
        self._post('vision:rack_3d:calculate',
                   {'recipe_id': self.recipe.id, 'layer_no': LAYER, 'save': True})
        resp = self.client.get(reverse('vision:rack_3d:results') + f'?layer_no={LAYER}')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['data']), 1)
