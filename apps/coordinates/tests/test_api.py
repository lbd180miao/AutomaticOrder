import json

from django.test import TestCase

from apps.coordinates.services import CoordinateWorkbenchService


class CoordinateApiTests(TestCase):
    def setUp(self):
        self.service = CoordinateWorkbenchService()

    def test_workbench_returns_three_clouds_for_layer_two(self):
        response = self.client.get('/coordinates/api/workbench/?layer_no=2')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['config']['robot_pose']['z'], 900.0)
        self.assertIn('camera_points', payload['data'])
        self.assertIn('base_points', payload['data'])
        self.assertIn('roi_points', payload['data'])

    def test_preview_uses_draft_without_persisting(self):
        draft = self.service.default_draft(2)
        draft['theoretical']['x'] += 10

        response = self.client.post(
            '/coordinates/api/preview/', data=json.dumps(draft),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()['data']['offset']['x'], -10, delta=1)

    def test_save_survives_workbench_reload(self):
        draft = self.service.default_draft(3)
        draft['theoretical']['x'] = 999.5

        saved = self.client.post(
            '/coordinates/api/save/', data=json.dumps(draft),
            content_type='application/json',
        )
        loaded = self.client.get('/coordinates/api/workbench/?layer_no=3')

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(loaded.json()['data']['config']['theoretical']['x'], 999.5)

    def test_invalid_rigid_matrix_returns_400(self):
        draft = self.service.default_draft(1)
        draft['hand_eye_matrix'][0][0] = 2

        response = self.client.post(
            '/coordinates/api/preview/', data=json.dumps(draft),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'INVALID_MATRIX')

    def test_empty_roi_returns_422(self):
        draft = self.service.default_draft(1)
        draft['roi'] = {
            'x_min': 0, 'x_max': 1, 'y_min': 0, 'y_max': 1,
            'z_min': 0, 'z_max': 1,
        }

        response = self.client.post(
            '/coordinates/api/preview/', data=json.dumps(draft),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'EMPTY_ROI')

    def test_unknown_recipe_id_returns_404_without_creating(self):
        draft = self.service.default_draft(1)
        draft['recipe_id'] = 999999

        response = self.client.post(
            '/coordinates/api/save/', data=json.dumps(draft),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'RECIPE_NOT_FOUND')

    def test_transform_roi_returns_robot_coordinates_from_coordinate_module(self):
        response = self.client.post(
            '/coordinates/api/transform-roi/',
            data=json.dumps({
                'layer_no': 2,
                'camera_roi': {
                    'x_min': -10, 'x_max': 20,
                    'y_min': -5, 'y_max': 15,
                    'z_min': 800, 'z_max': 820,
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']
        self.assertEqual(payload['coordinate_system'], 'robot')
        self.assertEqual(payload['robot_roi']['z_min'], 1820.0)

    def test_transform_roi_rejects_inverted_camera_bounds(self):
        response = self.client.post(
            '/coordinates/api/transform-roi/',
            data=json.dumps({
                'layer_no': 1,
                'camera_roi': {
                    'x_min': 10, 'x_max': 0,
                    'y_min': 0, 'y_max': 1,
                    'z_min': 0, 'z_max': 1,
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'INVALID_ROI')

    def test_3d_recipe_persists_robot_roi_and_coordinate_snapshot(self):
        transformed = self.service.transform_camera_roi(1, {
            'x_min': -10, 'x_max': 20,
            'y_min': -5, 'y_max': 15,
            'z_min': 800, 'z_max': 820,
        })
        robot_roi = transformed['robot_roi']
        response = self.client.post(
            '/vision/api/vision/3d/recipes/',
            data=json.dumps({
                'recipe_name': 'ROI-COORDINATE-SNAPSHOT',
                'layer_no': 1,
                'roi_config': {
                    'coordinate_system': 'robot',
                    **robot_roi,
                    'camera_roi': transformed['camera_roi'],
                },
                'hand_eye_config': {'matrix': transformed['hand_eye_matrix']},
                'capture_pose': transformed['robot_pose'],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        recipe = response.json()['recipe']
        self.assertEqual(recipe['roi_config']['coordinate_system'], 'robot')
        self.assertEqual(recipe['roi_config']['x_min'], robot_roi['x_min'])
        self.assertEqual(recipe['hand_eye_config']['matrix'], transformed['hand_eye_matrix'])

