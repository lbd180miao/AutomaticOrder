import copy
import unittest

import cv2
import numpy as np

from .algorithms.rack_dual_point import detect_line, locate_2d, LocalizationError
from .rack_camera_points import teach_image_edges, camera_pointmap_measurement
from .tests_dual_point import fixture


class CameraPointTests(unittest.TestCase):
    def test_failed_edge_includes_actual_roi_and_quality_settings(self):
        image, _, config, *_ = fixture()
        roi = config['rois'][0]
        with self.assertRaises(LocalizationError) as caught:
            detect_line(np.zeros_like(image), roi, 'Projection', config['lineQuality'])
        message = str(caught.exception)
        for value in (f"x={roi['x']}", f"y={roi['y']}",
                      f"width={roi['width']}", f"height={roi['height']}",
                      '完整 ROI 参数', 'searchHalfWidth', 'expectedPosition',
                      '直线质量阈值', 'ransac_px', '原图宽×高=320×220'):
            self.assertIn(value, message)

    def test_missing_taught_edge_never_switches_to_another_edge(self):
        _, _, config, *_ = fixture()
        roi = dict(config['rois'][0], x=0, y=0, width=160, height=100,
                   imageDirection='horizontal', expectedPosition=20, expectedSlope=0,
                   edgeSelection='taught', searchHalfWidth=8)
        before = copy.deepcopy(roi)
        image = np.zeros((100, 160), np.uint8)
        image[50:] = 200
        for algorithm in ('Projection', 'CaliperFit'):
            with self.assertRaises(LocalizationError):
                detect_line(image, roi, algorithm, config['lineQuality'])
        self.assertEqual(roi, before)
        for invalid in (np.zeros_like(image), 200-image):
            with self.assertRaises(LocalizationError):
                detect_line(invalid, roi, 'Projection', config['lineQuality'])
        image[65:80] = 0  # Two distinct rising edges: do not guess identity.
        with self.assertRaises(LocalizationError) as caught:
            detect_line(image, roi, 'Projection', config['lineQuality'])
        self.assertEqual(caught.exception.code, 'INSUFFICIENT_EDGES')

    def test_auto_teaching_rejects_two_opposite_edges(self):
        image, _, config, *_ = fixture()
        with self.assertRaises(LocalizationError) as caught:
            teach_image_edges(image, config)
        self.assertEqual(caught.exception.code, 'AMBIGUOUS_EDGE')

    def test_search_band_rejects_multiple_same_polarity_edges(self):
        _, _, config, *_ = fixture()
        roi = dict(config['rois'][0], x=0, y=0, width=160, height=100,
                   imageDirection='horizontal', expectedPosition=49, expectedSlope=0,
                   edgeSelection='taught', searchHalfWidth=10)
        image = np.zeros((100, 160), np.uint8)
        image[44:49] = 200
        image[55:] = 200
        with self.assertRaises(LocalizationError) as caught:
            detect_line(image, roi, 'Projection', config['lineQuality'])
        self.assertEqual(caught.exception.code, 'AMBIGUOUS_EDGE')

    def test_spurious_peaks_do_not_reject_continuous_edge(self):
        _, _, config, *_ = fixture()
        roi = dict(config['rois'][0], x=0, y=0, width=160, height=100,
                   imageDirection='horizontal', expectedPosition=50, expectedSlope=0,
                   edgeSelection='taught', searchHalfWidth=10)
        image = np.zeros((100, 160), np.uint8)
        image[50:] = 200
        image[43:47, 40:60] = 220  # Only a few calipers contain a second peak.
        for algorithm in ('Projection', 'CaliperFit'):
            line = detect_line(image, roi, algorithm, config['lineQuality'])
            a, b, c = line['line_abc']
            self.assertAlmostEqual((-a*80-c)/b, 49.5, delta=.5)
            self.assertGreaterEqual(line['inlier_count'], 14)

    def test_extrapolation_uses_inliers_not_roi_extent(self):
        from .algorithms.rack_dual_point import validate_intersection_support
        line = {'target': 'P1_vertical', 'line_abc': [1, 0, -10],
                'inlier_points': [[10, 0], [10, 20]], 'roi': [0, 0, 100, 500]}
        validate_intersection_support([10, 25], [line], {})
        for point, quality in (([10, 35], {}), ([10, 80], {'max_extrapolation_ratio': 10})):
            with self.assertRaises(LocalizationError) as caught:
                validate_intersection_support(point, [line], quality)
            self.assertEqual(caught.exception.code, 'EXCESSIVE_EXTRAPOLATION')

    def test_explicit_image_direction_is_independent_of_part_name(self):
        image, _, config, *_ = fixture()
        roi = copy.deepcopy(config['rois'][1])
        roi.update(target='P1_horizontal', imageDirection='vertical')
        line = detect_line(image, roi, 'Projection', config['lineQuality'])
        self.assertAlmostEqual(line['angle'], 90, delta=1)

    def test_teach_polarity_and_strength_without_relaxing_line_quality(self):
        image, _, config, *_ = fixture()
        image = (255-image)//8  # weak, reversed polarity, original threshold cannot pass
        config['rois'][0]['edgeSelection'] = 'auto'
        quality = copy.deepcopy(config['lineQuality'])
        for roi in config['rois']:
            if roi['target'].endswith('horizontal'):
                roi['height'] = 20
            else:
                roi['width'] = 25
        taught = teach_image_edges(image, config)
        self.assertEqual(taught['lineQuality'], quality)
        self.assertEqual(taught['rois'][0]['edgePolarity'], 'light_to_dark')
        self.assertEqual(len(locate_2d(image, taught)['pixels']), 2)
        # Later frames must use the taught identity, not search another edge.
        self.assertEqual(teach_image_edges(np.zeros_like(image), taught), taught)

    def test_blank_roi_is_not_accepted_by_lowering_threshold(self):
        image, _, config, *_ = fixture()
        with self.assertRaises(LocalizationError):
            teach_image_edges(np.zeros_like(image), config)

    def test_rotated_image_resolves_pair_directions(self):
        image, _, config, *_ = fixture()
        height = image.shape[0]
        rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        config['imageSize'] = [rotated.shape[1], rotated.shape[0]]
        config['intersectionBounds'] = {p: [0, 0, rotated.shape[1]-1, rotated.shape[0]-1] for p in ('P1', 'P2')}
        for roi in config['rois']:
            if roi['target'].endswith('horizontal'):
                roi['height'] = 20
            else:
                roi['width'] = 25
            x, y, w, h = [roi[k] for k in ('x', 'y', 'width', 'height')]
            roi.update(x=height-y-h, y=x, width=h, height=w)
        taught = teach_image_edges(rotated, config)
        self.assertEqual([r['imageDirection'] for r in taught['rois']], ['vertical', 'horizontal']*2)
        self.assertEqual(len(locate_2d(rotated, taught)['pixels']), 2)

    def measurement(self, mutate=None):
        image, _, config, *_ = fixture()
        yy, xx = np.mgrid[:image.shape[0], :image.shape[1]]
        cloud = np.stack([(xx-160)*1000/300, (yy-110)*1000/300, np.full_like(xx, 1000)], axis=-1).astype(float)
        if mutate:
            mutate(cloud)
        metadata = {'source': 'rvc_camera', 'camera': {'pointcloud_unit': 'mm'}}
        return camera_pointmap_measurement(image, cloud, config, metadata)

    def test_camera_xyz_without_robot_contract(self):
        result = self.measurement()
        self.assertTrue(result['success'], result)
        self.assertEqual(result['coordinateSystem'], 'camera')
        for point in result['points']:
            self.assertAlmostEqual(point['xyz'][2], 1000, places=6)
            self.assertNotIn('robot', point)
        self.assertFalse(result['compensation_valid'])
        self.assertFalse(result['independent_3d_validated'])

    def test_reordered_point_map_rejected(self):
        def shuffle(cloud):
            rng = np.random.default_rng(7)
            flat = cloud.reshape(-1, 3)
            flat[:] = flat[rng.permutation(len(flat))]
        result = self.measurement(shuffle)
        self.assertFalse(result['success'])
        self.assertEqual(result['errorCode'], 'UNVERIFIED_MAPPING')

    def test_depth_hole_does_not_fabricate_xyz(self):
        def hole(cloud):
            cloud[50:80, 35:65] = np.nan
        result = self.measurement(hole)
        self.assertFalse(result['success'])
        self.assertNotIn('points', result)

    def test_error_identifies_roi_and_sample_count(self):
        image, _, config, *_ = fixture()
        with self.assertRaisesRegex(LocalizationError, 'P1_horizontal.*0/16'):
            detect_line(np.zeros_like(image), config['rois'][0], 'Projection', config['lineQuality'])
