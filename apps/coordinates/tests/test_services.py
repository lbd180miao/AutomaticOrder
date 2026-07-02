from copy import deepcopy

import numpy as np
from django.test import TestCase

from apps.coordinates.services import CoordinateWorkbenchService
from apps.vision.models import RackLocationRecipe


class CoordinateWorkbenchServiceTests(TestCase):
    def setUp(self):
        self.service = CoordinateWorkbenchService(seed=20260702)

    def test_requested_chain_transforms_layer_two_camera_point(self):
        config = self.service.default_draft(2)

        transformed = self.service.transform_points(
            np.array([[0.0, 0.0, 800.0]]), config
        )

        np.testing.assert_allclose(transformed, [[1030.0, 440.0, 1820.0]])

    def test_requested_camera_support_cloud_ranges_are_deterministic(self):
        first = self.service.generate_camera_points(2)
        second = self.service.generate_camera_points(2)

        np.testing.assert_array_equal(first, second)
        self.assertGreaterEqual(first[:, 0].min(), -200)
        self.assertLessEqual(first[:, 0].max(), 200)
        self.assertGreaterEqual(first[:, 1].min(), -100)
        self.assertLessEqual(first[:, 1].max(), 100)
        self.assertGreaterEqual(first[:, 2].min(), 800)
        self.assertLessEqual(first[:, 2].max(), 820)

    def test_default_three_layer_photo_poses(self):
        self.assertEqual(
            [self.service.default_draft(layer)['robot_pose']['z'] for layer in (1, 2, 3)],
            [600.0, 900.0, 1200.0],
        )

    def test_save_persists_existing_recipe_coordinate_fields(self):
        recipe = RackLocationRecipe.objects.create(
            recipe_name='COORD-L2', position_no=1, layer_no=2, layer_count=3,
            rack_side='BOTH', enabled=True,
        )
        draft = self.service.default_draft(2)
        draft['recipe_id'] = recipe.id
        draft['hand_eye_matrix'][0][3] = 35
        draft['robot_pose']['rz'] = 5
        draft['theoretical']['x'] = 1001.5
        draft['roi']['x_min'] += 1

        saved = self.service.save(draft)

        recipe.refresh_from_db()
        self.assertEqual(recipe.hand_eye_config['matrix'][0][3], 35.0)
        self.assertEqual(recipe.capture_pose['rz'], 5.0)
        self.assertEqual(float(recipe.standard_x), 1001.5)
        self.assertEqual(recipe.roi_config['coordinate_system'], 'robot')
        self.assertEqual(recipe.roi_config['x_min'], saved['roi']['x_min'])

    def test_preview_draft_never_writes_database(self):
        recipe = RackLocationRecipe.objects.create(
            recipe_name='COORD-L1', position_no=1, layer_no=1, layer_count=3,
            rack_side='BOTH', enabled=True,
        )
        config = self.service.get_config(1)
        original_pose = deepcopy(recipe.capture_pose)
        config['theoretical']['x'] += 25

        result = self.service.preview(config)

        recipe.refresh_from_db()
        self.assertEqual(recipe.capture_pose, original_pose)
        self.assertEqual(
            result['config']['theoretical']['x'], config['theoretical']['x']
        )
