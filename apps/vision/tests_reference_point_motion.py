"""Distinguish local feature displacement from rigid transform translation."""
from types import SimpleNamespace
import numpy as np
from django.test import SimpleTestCase
from scipy.spatial.transform import Rotation

from .rack_location import RackLocationService
from .rack_spatial_service import reference_point_motion


class ReferencePointMotionTests(SimpleTestCase):
    def measure(self, delta, reference, camera=None):
        camera = np.eye(4) if camera is None else camera
        base_delta = camera @ delta @ np.linalg.inv(camera)
        result = reference_point_motion(
            {'frame': (delta @ reference).tolist(), 'delta_T': delta.tolist()},
            {'matrix': base_delta.tolist(), 'T_base_camera': camera.tolist()},
        )
        movement = np.array(list(result['reference_point_displacement_mm'].values()))
        lever = np.array(list(result['rotation_lever_term_mm'].values()))
        np.testing.assert_allclose(movement + lever, base_delta[:3, 3], atol=1e-9)
        return movement, lever

    def test_rotation_about_feature_has_zero_feature_displacement(self):
        reference = np.eye(4)
        reference[:3, 3] = [1000, 2000, 500]
        delta = np.eye(4)
        delta[:3, :3] = Rotation.from_euler('z', .5, degrees=True).as_matrix()
        delta[:3, 3] = reference[:3, 3] - delta[:3, :3] @ reference[:3, 3]
        movement, lever = self.measure(delta, reference)
        np.testing.assert_allclose(movement, 0, atol=1e-9)
        self.assertGreater(abs(lever[0]), 17)

    def test_translation_is_rotated_into_base_without_lever_term(self):
        reference = np.eye(4)
        reference[:3, 3] = [1000, 2000, 500]
        delta = np.eye(4)
        delta[:3, 3] = [1, 2, 3]
        camera = np.eye(4)
        camera[:3, :3] = Rotation.from_euler('z', 90, degrees=True).as_matrix()
        camera[:3, 3] = [4000, -3000, 2000]
        movement, lever = self.measure(delta, reference, camera)
        np.testing.assert_allclose(movement, [-2, 1, 3], atol=1e-9)
        np.testing.assert_allclose(lever, 0, atol=1e-9)

    def test_identity_delta_stays_zero_far_from_base_origin(self):
        reference = np.eye(4)
        reference[:3, 3] = [1000, 2000, 500]
        movement, lever = self.measure(np.eye(4), reference)
        np.testing.assert_allclose(movement, 0, atol=1e-9)
        np.testing.assert_allclose(lever, 0, atol=1e-9)
