"""Synthetic registration checks; these do not establish field accuracy."""
import copy
import unittest
import numpy as np
from .rack_cloud_match import build_template, match_template, pointmap, add_display_pixels


def fixture():
    rng = np.random.default_rng(83)
    points = rng.uniform(-50, 50, (80, 80, 3))
    flat = points.reshape(-1, 3)
    for i in range(3):
        flat[i::3, i] = -50
    points[..., 2] += 1000
    config = {'imageSize': [80, 80], 'rois': [
        {'target': name, 'x': x, 'y': y, 'width': 40, 'height': 40}
        for name, x, y in [('P1_horizontal', 0, 0), ('P1_vertical', 40, 0),
                           ('P2_horizontal', 0, 40), ('P2_vertical', 40, 40)]]}
    metadata = {'source': 'rvc_camera', 'camera': {'pointcloud_unit': 'mm', 'sn': 'test'}}
    return points, config, metadata


class CloudMatchTests(unittest.TestCase):
    def test_display_projection_and_invalid_mapping(self):
        yy, xx = np.mgrid[:80, :80]
        cloud = np.stack([(xx-40)*2., (yy-40)*2., np.full_like(xx, 1000.)], axis=-1)
        _, _, metadata = fixture()
        result = {'success': False, 'points': [{'xyz': [0, 0, 1000]}, {'xyz': [20, 10, 1000]}]}
        add_display_pixels(result, cloud, metadata)
        np.testing.assert_allclose(result['pixels'], [[40, 40], [50, 45]], atol=1e-8)
        self.assertFalse(result['success'])
        cloud, _, metadata = fixture()
        add_display_pixels(result, cloud, metadata)
        self.assertEqual(result['pixels'], [None, None])
        self.assertTrue(result['warnings'])

    def test_dense_search_volume_preserves_target_density(self):
        rng = np.random.default_rng(91)
        cloud = rng.uniform([-100, -100, 900], [100, 100, 1100], (200, 200, 3))
        _, config, metadata = fixture()
        config['imageSize'] = [200, 200]
        for roi in config['rois']:
            roi['width'] = roi['height'] = 100
            roi['x'] *= 2.5
            roi['y'] *= 2.5
        template = build_template(cloud, config, metadata)
        result = match_template(cloud + [3, -2, 1], metadata, template)
        self.assertTrue(result['success'], result['errorMessage'])
        self.assertGreater(result['registration']['target_points'], 20000)
        self.assertLess(result['registration']['rmse_mm'], 1.)
        expected = np.array([p['xyz'] for p in template['measurement']['points']]) + [3, -2, 1]
        np.testing.assert_allclose([p['xyz'] for p in result['points']], expected, atol=.4)

    def test_known_rigid_motion_recovers_reference_points(self):
        cloud, config, metadata = fixture()
        template = build_template(cloud, config, metadata)
        theta = np.deg2rad(2)
        rotation = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
        moved = cloud @ rotation.T + [3, -2, 1]
        result = match_template(moved, metadata, template)
        self.assertTrue(result['success'], result['errorMessage'])
        expected = np.array([p['xyz'] for p in template['measurement']['points']]) @ rotation.T + [3, -2, 1]
        np.testing.assert_allclose([p['xyz'] for p in result['points']], expected, atol=.4)
        self.assertFalse(result['plc_publish_allowed'])

    def test_same_frame_and_partial_occlusion(self):
        cloud, config, metadata = fixture()
        template = build_template(cloud, config, metadata)
        self.assertTrue(match_template(cloud, metadata, template)['success'])
        occluded = cloud.copy()
        occluded[:8] = np.nan
        result = match_template(occluded, metadata, template)
        self.assertTrue(result['success'], result['errorMessage'])
        np.testing.assert_allclose(result['registration']['transform'], np.eye(4), atol=.3)

    def test_plane_is_reported_as_underconstrained(self):
        cloud, config, metadata = fixture()
        cloud[..., 2] = 1000
        template = build_template(cloud, config, metadata)
        result = match_template(cloud, metadata, template)
        self.assertFalse(result['success'])
        self.assertFalse(result['registration']['quality_passed'])
        self.assertFalse(result['points'][0]['success'])
        self.assertTrue(any('结构约束不足' in reason for reason in result['registration']['failure_reasons']))

    def test_missing_template_and_wrong_sensor(self):
        cloud, config, metadata = fixture()
        with self.assertRaisesRegex(ValueError, '保存点云模板'):
            match_template(cloud, metadata, None)
        template = build_template(cloud, config, metadata)
        other = copy.deepcopy(metadata)
        other['camera']['sn'] = 'other'
        with self.assertRaisesRegex(ValueError, '相机'):
            match_template(cloud, other, template)
        other['camera']['pointcloud_unit'] = None
        with self.assertRaisesRegex(ValueError, '单位'):
            pointmap(cloud, other)

    def test_outside_search_range_is_not_success(self):
        cloud, config, metadata = fixture()
        template = build_template(cloud, config, metadata)
        with self.assertRaisesRegex(ValueError, '有效点不足'):
            match_template(cloud + [1000, 0, 0], metadata, template)
