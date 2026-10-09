import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from .models import RackLocationRecipe
from .views import api_vision_3d_recipes, api_rack_location_workbench_calculate


class RoiRecipeSaveTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.old = {'x': 1, 'y': 2, 'w': 30, 'h': 40}
        self.new = {'x': 100, 'y': 200, 'w': 50, 'h': 60}
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='ROI regression', roi_config={
                'target_roi': self.old,
                'local_template_rois': {'plane1': self.old, 'plane2': self.old},
            },
        )

    def test_save_replaces_new_frame_and_clears_old_regions_on_reload(self):
        request = self.factory.patch('/recipes/', data=json.dumps({
            'id': self.recipe.pk, 'roi_config': {
                'target_roi': self.new,
                'local_template_rois': {'plane1': self.new, 'plane2': None, 'plane3': None},
                'layer_spacing_line': None,
            },
        }), content_type='application/json')
        response = api_vision_3d_recipes(request)
        self.assertTrue(json.loads(response.content)['success'])
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config['target_roi'], self.new)
        self.assertIsNone(self.recipe.roi_config['local_template_rois']['plane2'])
        response = api_vision_3d_recipes(self.factory.get('/recipes/', {'id': self.recipe.pk}))
        payload = json.loads(response.content)
        self.assertEqual(payload['data']['recipes'][0]['roi_config']['target_roi'], self.new)

    @patch('apps.vision.views.RackLocationService')
    def test_calculating_draft_does_not_save_or_restore_cleared_roi(self, service):
        service.return_value.calculate_workbench.return_value = {}
        request = self.factory.post('/calculate/', data=json.dumps({
            'recipe_id': self.recipe.pk, 'save_record': False, 'save_recipe_roi': False,
            'roi_config': {'target_roi': None, 'local_template_rois': {'plane1': self.new}, 'layer_spacing_line': None},
        }), content_type='application/json')
        response = api_rack_location_workbench_calculate(request)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(service.return_value.calculate_workbench.call_args.kwargs['roi_config']['target_roi'])
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config['target_roi'], self.old)


    def test_spatial_parameters_roundtrip_preserves_editor_and_updates_bounds(self):
        box = {axis + edge: value for axis in 'XYZ' for edge, value in [('min', -5), ('max', 15)]}
        self.recipe.roi_config.update(spatial_rois={name: dict(box) for name in ('plane1', 'plane2', 'plane3')}, margin_mm=5, voxel_mm=0)
        self.recipe.save()
        for margin in (8, 8, 0):
            response = api_vision_3d_recipes(self.factory.patch('/recipes/', data=json.dumps({
                'id': self.recipe.pk, 'roi_config': {'margin_mm': margin, 'voxel_mm': 2},
            }), content_type='application/json'))
            self.assertTrue(json.loads(response.content)['success'], response.content)
            response = api_vision_3d_recipes(self.factory.get('/recipes/', {'id': self.recipe.pk}))
            config = json.loads(response.content)['data']['recipes'][0]['roi_config']
            self.assertEqual(config['margin_mm'], margin)
            self.assertEqual(config['voxel_mm'], 2)
            self.assertEqual(config['target_roi'], self.old)
            self.assertEqual(config['spatial_rois']['plane1']['Xmin'], -margin)
            self.assertEqual(config['spatial_rois']['plane1']['Xmax'], 10 + margin)

    def test_invalid_spatial_parameters_are_rejected(self):
        from .views import _merge_rack_roi_config
        for config in ({'margin_mm': -1}, {'voxel_mm': 51}, {'margin_mm': float('nan')}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                _merge_rack_roi_config({}, config)
