"""Synthetic geometry tests, never a claim of M2600/robot production accuracy."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import cv2
import numpy as np

from .algorithms import rack_dual_point as dp
from .rack_dual_point_offline import atomic_json, main


def fixture(algorithm='Projection', z=1000):
    yy, xx = np.mgrid[:220, :320]
    image = np.zeros((220, 320), np.uint8)
    for y in (60, 150):
        image[(yy >= y+.03*xx) & (yy < y+18+.03*xx)] = 200
    image[(xx >= 50) & (xx < 68)] = 200
    k = [[300., 0, 160], [0, 300., 110], [0, 0, 1]]
    cloud = np.stack([(xx-160)*z/300, (yy-110)*z/300, np.full_like(xx, z)], axis=-1).astype(float)
    rois = []
    for index, y in enumerate((60, 150), 1):
        common = {'edgePolarity': 'dark_to_light', 'edgeMode': 'single', 'caliperCount': 16,
                  'searchHalfWidth': 9, 'gradientThreshold': 5, 'caliperWidth': 3}
        rois.extend([
            {**common, 'id': f'roi{2*index-1}', 'target': f'P{index}_horizontal',
             'x': 90, 'y': y-10, 'width': 150, 'height': 40, 'edgeSide': 'upper',
             'expectedPosition': y+5, 'expectedSlope': .03},
            {**common, 'id': f'roi{2*index}', 'target': f'P{index}_vertical',
             'x': 35, 'y': y-45, 'width': 45, 'height': 32, 'edgeSide': 'left', 'expectedPosition': 50},
        ])
    geometry = {'model': 'beam_plane_ray', 'surfaceBandPx': [3, 12], 'depthRangeMm': [800, 1200],
                'intersectionExclusionPx': 20, 'min_points': 30, 'ransac_mm': 1,
                'iterations': 60, 'min_inlier_ratio': .8, 'max_residual_mm': .5,
                'max_eigenvalue_ratio': .05, 'min_ray_cosine': .1, 'max_extrapolation_mm': 600}
    config = {'algorithm': algorithm, 'rois': rois, 'imageSize': [320, 220],
              'lineQuality': {'max_extrapolation_px': 60, 'max_extrapolation_ratio': 1, 'min_points': 8, 'ransac_px': 1.5, 'iterations': 100,
                              'min_inlier_ratio': .7, 'min_valid_ratio': .5,
                              'max_residual_px': .7, 'max_tilt_deg': 10},
              'intersectionBounds': {'P1': [35, 40, 80, 90], 'P2': [35, 130, 80, 180]},
              'minIntersectionSine': .2, 'geometry': {'P1': copy.deepcopy(geometry), 'P2': copy.deepcopy(geometry)},
              'maxOffsetMm': [[20, 20, 20], [20, 20, 20]], 'maxResultAgeSeconds': 3}
    # Separate depth-only faces: these are NOT obtained from measured 2D lines.
    for index, edge_y in enumerate((60, 150)):
        intercept = (edge_y+.03*160-110)*z/300
        sx, sz = np.meshgrid(np.linspace(-200, 200, 320), np.linspace(z+5, z+45, 10))
        start = index*90
        cloud[start:start+10] = np.stack([sx, .03*sx+intercept, sz], axis=-1)
        config['geometry'][f'P{index+1}']['consistency'] = {
            'model': 'two_face_edge', 'edgeSide': 'upper',
            'frontFace': {'boundsMm': [[-200, intercept+10, z-1], [200, intercept+50, z+1]],
                          'normal': [0, 0, 1], 'normalToleranceDeg': 5},
            'sideFaces': [{'boundsMm': [[-210, intercept-10, z+4], [210, intercept+10, z+46]],
                           'normal': [-.03, 1, 0], 'normalToleranceDeg': 5}],
            'fit': copy.deepcopy(geometry), 'minPlaneSine': .1, 'minSpanMm': 100,
            'maxSupportGapMm': 60, 'minSpanPx': 50, 'maxRmsPx': 1, 'maxDistancePx': 1.5,
            'maxAngleDeg': 1, 'maxSurfaceDistanceMm': 1, 'maxSurfaceAngleDeg': 2}
    config['placementTransfer'] = {'verified': True, 'calibrationVersion': 'synthetic-transfer',
        'evidence': 'synthetic fixture only', 'inputFrame': 'robot_base', 'outputFrame': 'robot_base',
        'layers': {str(i): {'k_layer': 1, 'axisMap': np.eye(3).tolist(), 'maxPlacementOffsetMm': [20,20,20]} for i in (1,2)}}
    contract = {'frame_id': 'teach', 'image_frame_id': 'teach', 'cloud_frame_id': 'teach',
                'pose_frame_id': 'teach', 'pose_synchronized': True,
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'sensor_id': 'SYNTHETIC', 'sensor_config_version': 'synthetic-v1',
                'calibration_version': 'synthetic-v1', 'robot_frame': 'test_base',
                'mapping_verified': True, 'mapping_evidence': 'synthetic pinhole fixture',
                'mapping_mode': 'organized_registered', 'calibration_verified': True,
                'unit': 'mm', 'matrix_unit': 'mm', 'cloud_frame': 'camera',
                'transform_mode': 'eye_in_hand', 'hand_eye_direction': 'T_flange_camera',
                'pose_direction': 'T_base_flange',
                'camera_model': {'type': 'pinhole', 'K': k, 'rectified': True}}
    return image, cloud, config, {'dual_point_contract': contract}, np.eye(4), np.eye(4)


def next_frame(metadata):
    metadata = copy.deepcopy(metadata)
    for field in ('frame_id', 'image_frame_id', 'cloud_frame_id', 'pose_frame_id'):
        metadata['dual_point_contract'][field] = 'run'
    return metadata


class DualPointTests(unittest.TestCase):
    def test_canvas_inverse_with_pan_crop_and_nonuniform_scale(self):
        roi = dp.canvas_to_image({'x': 30, 'y': 50, 'w': 80, 'h': 60},
                                 scale_x=2, scale_y=3, offset_x=10, offset_y=20, crop_x=100, crop_y=200)
        self.assertEqual([roi[k] for k in ('x', 'y', 'width', 'height')], [110, 210, 40, 20])

    def test_roi_alias_and_out_of_bounds(self):
        self.assertEqual(dp.image_roi({'x': 1.2, 'y': 2.1, 'w': 4, 'h': 5}, (20, 20)), (1, 2, 6, 8))
        with self.assertRaises(dp.LocalizationError):
            dp.image_roi({'x': -1, 'y': 2, 'w': 4, 'h': 5}, (20, 20))

    def test_subpixel_parabola(self):
        x = np.arange(9)
        self.assertAlmostEqual(dp.subpixel_peak(20-(x-4.3)**2, 4), 4.3)

    def test_ransac_rejects_outliers(self):
        q = fixture()[2]['lineQuality']
        x = np.arange(40.)
        p = np.column_stack([x, .04*x+3])
        p[::7, 1] += 25
        result = dp.fit_line(p, q, 40)
        self.assertLess(result['residual'], 1e-10)
        self.assertEqual(result['inlier_count'], 34)

    def test_intersection_and_parallel(self):
        np.testing.assert_allclose(dp.intersection([0, 1, -4.2], [1, 0, -3.1], [0, 0, 8, 8], .1), [3.1, 4.2])
        with self.assertRaisesRegex(dp.LocalizationError, '平行'):
            dp.intersection([0, 1, -4], [.00001, 1, -3], [0, 0, 8, 8], .1)

    def test_both_algorithms_follow_tilt_and_recover_plane_ray(self):
        for algorithm in ('Projection', 'CaliperFit'):
            data = fixture(algorithm)
            result = dp.locate(*data)
            self.assertTrue(result['success'], result)
            for i, y in enumerate((60, 150)):
                np.testing.assert_allclose(result['pixels'][i], [49.5, y+.03*49.5], atol=.7)
                self.assertAlmostEqual(result['points'][i]['xyz'][2], 1000, places=6)
                np.testing.assert_allclose(result['points'][i]['robot'], result['points'][i]['xyz'])

    def test_calipers_partial_occlusion(self):
        image, cloud, config, *rest = fixture('CaliperFit')
        image[50:90, 140:160] = 0
        result = dp.locate(image, cloud, config, *rest)
        self.assertTrue(result['success'], result)
        self.assertLess(result['lines'][0]['valid_count'], 16)

    def test_dual_edge_center_requires_both_edges(self):
        image, _, config, *_ = fixture()
        roi = config['rois'][0]
        roi.update(edgeMode='center', edgeSide='center', expectedPosition=74,
                   expectedWidth=18, widthTolerance=2, searchHalfWidth=4)
        result = dp.detect_line(image, roi, 'Projection', config['lineQuality'])
        self.assertTrue(result['success'])
        image[75:100, 90:240] = 200  # bottom edge disappears outside the ROI
        with self.assertRaises(dp.LocalizationError):
            dp.detect_line(image, roi, 'Projection', config['lineQuality'])

    def test_wrong_polarity_fails(self):
        data = list(fixture())
        data[2]['rois'][0]['edgePolarity'] = 'light_to_dark'
        result = dp.locate(*data)
        self.assertFalse(result['success'])
        self.assertEqual(result['errorCode'], 'INSUFFICIENT_EDGES')

    def test_compare_algorithms(self):
        data = list(fixture())
        data[2].update(compareAlgorithms=True, maxAlgorithmDifferencePx=1)
        result = dp.locate(*data)
        self.assertTrue(result['success'], result)
        self.assertEqual(len(result['comparison']['difference_px']), 2)

    def test_nan_inf_zero_and_background_are_filtered(self):
        data = list(fixture())
        data[1][::5, ::5] = np.nan
        data[1][::7, ::7] = np.inf
        data[1][::11, ::11] = 0
        data[1][::13, ::13, 2] = 9000
        result = dp.locate(*data)
        self.assertTrue(result['success'], result)
        self.assertAlmostEqual(result['points'][0]['z'], 1000)

    def test_missing_one_beam_depth_invalidates_pair(self):
        data = list(fixture())
        data[1][140:190] = np.nan
        result = dp.locate(*data)
        self.assertFalse(result['success'])
        self.assertFalse(result['compensation_valid'])
        self.assertNotIn('points', result)

    def test_degenerate_plane_failure(self):
        data = list(fixture())
        data[1][:] = [0, 0, 1000]
        result = dp.locate(*data)
        self.assertEqual(result['errorCode'], 'GEOMETRY_FIT_FAILED')

    def test_missing_registration_not_inferred_from_shape(self):
        data = list(fixture())
        data[3]['dual_point_contract']['mapping_verified'] = False
        result = dp.locate(*data)
        self.assertEqual(result['errorCode'], 'UNVERIFIED_MAPPING')

    def test_sync_and_calibration_rejections(self):
        for key, value, code in [('cloud_frame_id', 'wrong', 'FRAME_MISMATCH'),
                                 ('pose_frame_id', 'wrong', 'POSE_FRAME_MISMATCH'),
                                 ('hand_eye_direction', 'T_camera_flange', 'TRANSFORM_DIRECTION'),
                                 ('calibration_verified', False, 'UNVERIFIED_CALIBRATION'),
                                 ('cloud_frame', 'unknown', 'COORDINATE_MISMATCH')]:
            data = list(fixture())
            data[3]['dual_point_contract'][key] = value
            self.assertEqual(dp.locate(*data)['errorCode'], code)

    def test_metre_cloud_is_scaled_once(self):
        data = list(fixture())
        data[1] /= 1000
        data[3]['dual_point_contract']['unit'] = 'm'
        self.assertAlmostEqual(dp.locate(*data)['points'][0]['z'], 1000)

    def test_flat_cloud_requires_mapping(self):
        data = list(fixture())
        shape = data[1].shape[:2]
        data[1] = data[1].reshape(-1, 3)
        self.assertFalse(dp.locate(*data)['success'])
        data[3]['dual_point_contract']['mapping_mode'] = 'pixel_index_map'
        index = np.arange(len(data[1])).reshape(shape)
        index[0, 0] = -1
        self.assertTrue(dp.locate(*data, pixel_index_map=index)['success'])
        index[0, 0] = len(data[1])
        self.assertEqual(dp.locate(*data, pixel_index_map=index)['errorCode'], 'INVALID_MAPPING')

    def test_matrix_order_and_moving_capture_pose(self):
        data = list(fixture())
        data[4][:3, 3] = [10, 20, 30]
        data[5][:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        data[5][:3, 3] = [100, 200, 300]
        result = dp.locate(*data)
        xyz = result['points'][0]['xyz']
        expected = (data[5] @ data[4] @ np.array([*xyz, 1]))[:3]
        np.testing.assert_allclose(result['points'][0]['robot'], expected)
        reference = dp.teach_reference(result)
        data[3] = next_frame(data[3])
        data[5][:3, 3] += [1, 2, 3]
        current = dp.locate(*data)
        delta = dp.compensation(current, reference, data[2])
        self.assertTrue(delta['success'], delta)
        np.testing.assert_allclose(delta['offsets'], [[1, 2, 3], [1, 2, 3]])
        self.assertEqual(delta['layer_offsets']['3'], [0, 0, 0])
        self.assertFalse(delta['plc_publish_allowed'])

    def test_robot_frame_cloud_not_transformed_twice(self):
        data = list(fixture())
        baseline = dp.locate(*data)
        matrix = np.eye(4)
        matrix[:3, 3] = [100, 200, 300]
        data[1] += [100, 200, 300]
        data[3]['dual_point_contract'].update(transform_mode='robot_base', cloud_frame='robot_base', T_base_camera=matrix.tolist())
        result = dp.locate(*data)
        np.testing.assert_allclose(np.asarray(result['points'][0]['robot'])-baseline['points'][0]['robot'], [100, 200, 300])

    def test_invalid_transform_not_used(self):
        data = list(fixture())
        data[4][0, 0] = 2
        self.assertEqual(dp.locate(*data)['errorCode'], 'INVALID_TRANSFORM')

    def test_fixed_camera_needs_no_robot_capture_pose(self):
        data = list(fixture())
        data[3]['dual_point_contract'].update(transform_mode='fixed_camera', hand_eye_direction='T_base_camera')
        data[4][:3, 3] = [2, 3, 4]
        data[5] = None
        result = dp.locate(*data)
        self.assertTrue(result['success'], result)
        np.testing.assert_allclose(np.asarray(result['points'][0]['robot'])-result['points'][0]['xyz'], [2, 3, 4])

    def test_surface_side_and_extrapolation_fail_closed(self):
        data = list(fixture())
        data[2]['geometry']['P1']['surfaceBandPx'] = [-12, -3]
        self.assertEqual(dp.locate(*data)['errorCode'], 'SURFACE_SELECTION')
        data[2]['geometry']['P1']['surfaceBandPx'] = [3, 12]
        data[2]['geometry']['P1']['max_extrapolation_mm'] = 1
        self.assertEqual(dp.locate(*data)['errorCode'], 'EXTRAPOLATION_LIMIT')

    def test_algorithm_disagreement_is_debug_only(self):
        data = fixture()
        config = copy.deepcopy(data[2])
        config.update(compareAlgorithms=True, maxAlgorithmDifferencePx=.5)
        first = dp.locate_2d(data[0], config)
        other = copy.deepcopy(first)
        other['pixels'][0][0] += 3
        with patch.object(dp, 'locate_2d', side_effect=[first, other]):
            result = dp.locate(data[0], data[1], config, *data[3:])
        self.assertTrue(result['success'], result)
        self.assertFalse(result['comparison']['within_debug_limit'])
        self.assertTrue(result['comparison']['debug_only'])

    def test_missing_contract_and_unit_conflict(self):
        data = list(fixture())
        data[3]['camera'] = {'pointcloud_unit': 'm'}
        self.assertEqual(dp.locate(*data)['errorCode'], 'UNIT_MISMATCH')
        data[3] = {}
        self.assertEqual(dp.locate(*data)['errorCode'], 'MISSING_FRAME_CONTRACT')

    def test_corrupt_point_identity_and_nonfinite_coordinates(self):
        data = list(fixture())
        reference = dp.teach_reference(dp.locate(*data))
        data[3] = next_frame(data[3])
        current = dp.locate(*data)
        bad = copy.deepcopy(current)
        bad['points'].reverse()
        self.assertEqual(dp.compensation(bad, reference, data[2])['errorCode'], 'INCOMPLETE_RESULT')
        bad = copy.deepcopy(current)
        bad['points'][0]['robot'][0] = float('nan')
        self.assertEqual(dp.compensation(bad, reference, data[2])['errorCode'], 'INVALID_RESULT')

    def test_plane_residual_rejects_nonplanar_surface(self):
        data = list(fixture())
        # Two equally sized depth surfaces cannot meet the configured 80% support.
        data[1][:, ::2, 2] += 10
        result = dp.locate(*data)
        self.assertFalse(result['success'])
        self.assertIn(result['errorCode'], ('GEOMETRY_FIT_FAILED', 'GEOMETRY_QUALITY'))

    def test_version_limits_stale_and_reused_frame_block_publication(self):
        data = list(fixture())
        taught = dp.locate(*data)
        reference = dp.teach_reference(taught)
        self.assertEqual(dp.compensation(taught, reference, data[2])['errorCode'], 'REUSED_TEACH_FRAME')
        data[3] = next_frame(data[3])
        current = dp.locate(*data)
        for field in ('calibration_digest', 'config_digest', 'robot_frame'):
            bad = {**current, field: 'changed'}
            self.assertEqual(dp.compensation(bad, reference, data[2])['errorCode'], 'VERSION_MISMATCH')
        data[2]['rois'][0]['algorithm'] = 'CaliperFit'
        self.assertEqual(dp.compensation(current, reference, data[2])['errorCode'], 'VERSION_MISMATCH')
        del data[2]['rois'][0]['algorithm']
        bad = copy.deepcopy(current)
        bad['points'][0]['robot'][0] += 21
        rejected = dp.compensation(bad, reference, data[2])
        self.assertEqual(rejected['errorCode'], 'OFFSET_LIMIT')
        self.assertNotIn('six_values', rejected)
        self.assertFalse(rejected['plc_publish_allowed'])
        now = datetime.fromisoformat(current['captured_at']) + timedelta(seconds=5)
        self.assertEqual(dp.compensation(current, reference, data[2], now=now)['errorCode'], 'RESULT_EXPIRED')

    def test_atomic_teach_and_failed_pair_offline_report(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temporary:
            root = Path(temporary)
            image, cloud, config, meta, hand, pose = fixture()
            for name in ('teach', 'run'):
                path = root/name
                path.mkdir()
                cv2.imwrite(str(path/'image2d.png'), image)
                np.save(path/'pointcloud.npy', cloud)
                np.save(path/'hand_eye_matrix.npy', hand)
                np.save(path/'robot_pose_matrix.npy', pose)
                atomic_json(path/'metadata.json', meta if name == 'teach' else next_frame(meta))
                atomic_json(path/'roi_config.json', {'legacy_untouched': True, 'dual_point': config})
            with patch('builtins.print'):
                self.assertEqual(main([str(root/'teach'), '--run', str(root/'run'), '--output', str(root/'out')]), 0)
            result = json.loads((root/'out/report.json').read_text(encoding='utf-8'))
            np.testing.assert_allclose(result['compensation']['six_values'], [0]*6)
            self.assertTrue((root/'out/teach_reference.json').exists())
            self.assertTrue((root/'out/run/preview.png').exists())
            cloud[:] = np.nan
            np.save(root/'run/pointcloud.npy', cloud)
            with patch('builtins.print'):
                self.assertEqual(main([str(root/'teach'), '--run', str(root/'run'), '--output', str(root/'failed')]), 2)
            result = json.loads((root/'failed/report.json').read_text(encoding='utf-8'))
            self.assertFalse(result['success'])
            self.assertNotIn('six_values', result['compensation'])


if __name__ == '__main__':
    unittest.main()
