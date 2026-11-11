import json

from django.test import TestCase, RequestFactory

from .models import VisionRecipe
from .recipe_utils import build_foam_inspection_config
from .views import api_foam_recipe_save


class FoamRecipeSaveTests(TestCase):
    def test_color_is_not_inferred_from_segmentation(self):
        from .recipe_utils import serialize_recipe
        self.recipe.algorithm_config = {'foam_segmentation': 'shadow-graphcut-fast-v2'}
        summary = serialize_recipe(self.recipe)['foam_summary']
        self.assertEqual(summary['material_label'], '未标注颜色')
        self.assertEqual(summary['segmentation_label'], '快速阴影分割')
        self.assertEqual(summary['effective_mode'], 'shadow-graphcut-fast-v2')

    def test_explicit_color_and_thresholds_round_trip(self):
        payload = {'id': self.recipe.pk, 'pos': 0, 'save_mode': 'draft',
                   'roi_config': self.rois, 'image_width': 4096, 'image_height': 2460,
                   'algorithm_config': {'material_type': 'white',
                                        'segmentation_config': {'foam_min_v': 0, 'foam_max_s': 255}}}
        response = api_foam_recipe_save(RequestFactory().post(
            '/', json.dumps(payload), content_type='application/json'))
        self.assertEqual(response.status_code, 200, response.content)
        saved = json.loads(response.content)['recipe']
        self.assertEqual(saved['foam_summary']['material_label'], '白色')
        self.recipe.refresh_from_db()
        self.assertEqual(build_foam_inspection_config(self.recipe)['foam_min_v'], 0)
        payload['algorithm_config']['segmentation_config']['foam_min_v'] = 256
        response = api_foam_recipe_save(RequestFactory().post(
            '/', json.dumps(payload), content_type='application/json'))
        self.assertEqual(response.status_code, 400)
        self.recipe.refresh_from_db()
        self.assertEqual(build_foam_inspection_config(self.recipe)['foam_min_v'], 0)

    def test_many_recipes_can_publish_at_same_position_without_replacing_others(self):
        ids = []
        for index in range(6):
            request = RequestFactory().post('/', json.dumps({
                'create_new': True, 'name': f'product-{index}', 'pos': 0,
                'save_mode': 'publish', 'image_width': 4096, 'image_height': 2460,
                'roi_config': self.rois,
            }), content_type='application/json')
            response = api_foam_recipe_save(request)
            self.assertEqual(response.status_code, 200, response.content)
            ids.append(json.loads(response.content)['recipe']['id'])
        self.assertEqual(len(set(ids)), 6)
        self.assertEqual(VisionRecipe.objects.filter(pk__in=ids, is_active=True).count(), 6)
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.is_active)
        from .views import api_vision_recipes
        response = api_vision_recipes(RequestFactory().get('/', {
            'recipe_type': 'FOAM_2D', 'is_active': 'true',
        }))
        listed = {r['id'] for r in json.loads(response.content)['recipes']}
        self.assertTrue(set(ids).issubset(listed))

    def setUp(self):
        self.rois = {
            'leftFoamROI': {'type': 'polygon', 'points': [[.20, .18], [.37, .18], [.37, .39], [.20, .39]]},
            'rightFoamROI': {'type': 'polygon', 'points': [[.38, .21], [.59, .21], [.59, .38], [.38, .38]]},
            'layerSearchROI': {'x': 784, 'y': 382, 'width': 1758, 'height': 630},
        }
        self.recipe = VisionRecipe.objects.create(
            name='mixed-coordinate-test', recipe_type='FOAM_2D', pos=0,
            image_width=4096, image_height=2460, roi_config=self.rois,
        )

    def save(self, width, height, rois):
        request = RequestFactory().post('/', json.dumps({
            'id': self.recipe.pk, 'pos': 0, 'save_mode': 'draft',
            'image_width': width, 'image_height': height, 'roi_config': rois,
        }), content_type='application/json')
        return api_foam_recipe_save(request)

    def test_unchanged_legacy_pixels_follow_original_resolution(self):
        before = build_foam_inspection_config(self.recipe)['layer_search_roi']
        response = self.save(5472, 3648, self.rois)
        self.assertEqual(response.status_code, 200, response.content)
        self.recipe.refresh_from_db()
        self.assertEqual(build_foam_inspection_config(self.recipe)['layer_search_roi'], before)
        self.assertEqual(self.recipe.roi_config['leftFoamROI'], self.rois['leftFoamROI'])

    def test_parameter_only_save_keeps_template_roi_identity(self):
        response = self.save(4096, 2460, self.rois)
        self.assertEqual(response.status_code, 200, response.content)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.roi_config, self.rois)

    def test_new_invalid_search_box_reports_side_and_rolls_back(self):
        rois = {**self.rois, 'layerSearchROI': {'x1r': .25, 'y1r': .15, 'x2r': .65, 'y2r': .42}}
        response = self.save(5472, 3648, rois)
        self.assertEqual(response.status_code, 400)
        self.assertIn('左标准 ROI', json.loads(response.content)['error'])
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.image_width, 4096)
        self.assertEqual(self.recipe.roi_config, self.rois)

    def test_quality_settings_saved_and_invalid_update_rolled_back(self):
        payload = {
            'id': self.recipe.pk, 'pos': 0, 'save_mode': 'draft',
            'image_width': 4096, 'image_height': 2460, 'roi_config': self.rois,
            'algorithm_config': {'material_type': 'gray', 'foam_segmentation': 'gray-graphcut-v3'},
            'threshold_config': {'decision_mode': 'separated-v2', 'min_area_ratio': .8,
                'max_area_ratio': 1.25, 'max_missing_ratio': .2, 'max_excess_ratio': .25},
        }
        def submit():
            return api_foam_recipe_save(RequestFactory().post('/', json.dumps(payload),
                                        content_type='application/json'))
        response = submit()
        self.assertEqual(response.status_code, 200, response.content)
        self.recipe.refresh_from_db()
        cfg = build_foam_inspection_config(self.recipe)
        self.assertEqual(cfg['foam_segmentation'], 'gray-graphcut-v3')
        self.assertEqual(cfg['min_area_ratio'], .8)
        payload['threshold_config']['max_area_ratio'] = .1
        self.assertEqual(submit().status_code, 400)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.threshold_config['max_area_ratio'], 1.25)
