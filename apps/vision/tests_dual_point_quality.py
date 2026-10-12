"""Independent geometry, transfer calibration and numerical study regressions."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from .algorithms import rack_dual_point as dp
from .rack_dual_point_quality import cloud_forensics, repeatability, crossed_grr, acceptance_report
from .tests_dual_point import fixture, next_frame


class IndependentGateTests(unittest.TestCase):
    def test_center_requires_two_distinct_depth_edges_with_matching_width(self):
        from .vision_result_validator import VisionResultValidator
        image, cloud, config, metadata, *_ = fixture()
        line = dp.locate_2d(image, config)['lines'][0]
        roi = copy.deepcopy(config['rois'][0])
        roi.update(edgeMode='center', edgeSide='center', expectedWidth=18, widthTolerance=2)
        geometry = copy.deepcopy(config['geometry']['P1']['consistency'])
        geometry.update(edgeSide='center', sideFaces=geometry['sideFaces']*2)
        with self.assertRaisesRegex(dp.LocalizationError, '投影宽度'):
            VisionResultValidator().validate_beam(cloud, line, roi, {},
                metadata['dual_point_contract']['camera_model'], geometry)

    def test_same_gray_algorithms_agree_but_wrong_depth_edge_fails(self):
        data = list(fixture())
        data[2].update(compareAlgorithms=True, maxAlgorithmDifferencePx=1)
        # Both 2D algorithms see identical image; depth-derived upper face moves 10 mm.
        data[1][:10, :, 1] += 10
        result = dp.locate(*data)
        self.assertTrue(result['comparison']['within_debug_limit'])
        self.assertFalse(result['success'])
        self.assertEqual(result['errorCode'], 'TWO_D_THREE_D_MISMATCH')
        self.assertGreater(result['validation_metrics']['max_px'], 1.5)

    def test_front_plane_alone_cannot_self_validate(self):
        data = list(fixture())
        data[1][:10] = np.nan
        result = dp.locate(*data)
        self.assertEqual(result['errorCode'], 'INDEPENDENT_GEOMETRY_FAILED')
        data = list(fixture())
        del data[2]['geometry']['P1']['consistency']
        self.assertEqual(dp.locate(*data)['errorCode'], 'CONSISTENCY_EVIDENCE_MISSING')

    def test_depth_surface_and_edge_identity_are_checked(self):
        data = list(fixture())
        data[2]['geometry']['P1']['consistency']['edgeSide'] = 'lower'
        self.assertEqual(dp.locate(*data)['errorCode'], 'EDGE_IDENTITY_MISMATCH')
        data = list(fixture())
        # Corrupt only the 2D-derived depth sampling band; independent faces remain at z=1000.
        original = dp.recover_point
        def shifted(*args):
            result = original(*args)
            result['xyz'][2] += 5
            return result
        with patch.object(dp, 'recover_point', side_effect=shifted):
            self.assertEqual(dp.locate(*data)['errorCode'], 'TWO_D_THREE_D_MISMATCH')

    def test_comparison_failure_and_toggle_do_not_change_measurement_identity(self):
        data = list(fixture())
        first = dp.locate_2d(data[0], data[2])
        with patch.object(dp, 'locate_2d', side_effect=ValueError('occluded')):
            debug = dp.compare_2d_debug(data[0], data[2], first)
        self.assertFalse(debug['available'])
        result = dp.locate(*data)
        data[2].update(compareAlgorithms=True, maxAlgorithmDifferencePx=.00001)
        current = dp.locate(*data)
        self.assertTrue(current['success'], current)
        self.assertEqual(result['config_digest'], current['config_digest'])

    def test_projection_and_caliper_share_identical_kernel_for_same_footprint(self):
        image, _, config, *_ = fixture()
        roi = copy.deepcopy(config['rois'][0])
        roi.update(caliperCount=15, caliperWidth=10)
        a = dp.detect_line(image, roi, 'Projection', config['lineQuality'])
        b = dp.detect_line(image, roi, 'CaliperFit', config['lineQuality'])
        np.testing.assert_allclose(a['edge_points'], b['edge_points'], atol=1e-12)

    def test_transfer_ratio_axis_permutation_and_sign(self):
        config = fixture()[2]['placementTransfer']
        config['layers']['1'].update(k_layer=2, axisMap=[[0,-1,0],[1,0,0],[0,0,-1]])
        config['layers']['2']['k_layer'] = .5
        mapped, _ = dp.placement_offsets(np.array([[1,2,3],[4,6,8]]), config)
        np.testing.assert_allclose(mapped, [[-4,2,-6],[2,3,4]])

    def test_transfer_missing_invalid_and_mapped_limit(self):
        data = np.ones((2,3))
        with self.assertRaisesRegex(dp.LocalizationError, '标定'):
            dp.placement_offsets(data, None)
        config = fixture()[2]['placementTransfer']
        config['layers']['1']['axisMap'] = [[1,0,0],[1,0,0],[0,0,1]]
        with self.assertRaisesRegex(dp.LocalizationError, '排列'):
            dp.placement_offsets(data, config)
        config = fixture()[2]['placementTransfer']
        config['layers']['1']['k_layer'] = 30
        with self.assertRaisesRegex(dp.LocalizationError, '超限'):
            dp.placement_offsets(data, config)

    def test_mapped_limit_prevents_six_value_output(self):
        data = list(fixture())
        data[2]['placementTransfer']['layers']['1']['k_layer'] = 30
        ref = dp.teach_reference(dp.locate(*data))
        data[3] = next_frame(data[3]); data[5][0, 3] = 1
        result = dp.compensation(dp.locate(*data), ref, data[2])
        self.assertEqual(result['errorCode'], 'PLACEMENT_OFFSET_LIMIT')
        self.assertNotIn('six_values', result)
        self.assertFalse(result['plc_publish_allowed'])


class MeasurementStudyTests(unittest.TestCase):
    def records(self):
        return [{'frame_id': str(i), 'success': True, 'robot_points': np.full((2,3), value).tolist(),
                 'condition_id': 'fixed-unloaded', 'config_digest': 'cfg', 'calibration_digest': 'cal', 'robot_frame': 'base'}
                for i, value in enumerate([-.1,0,.1])]

    def test_repeatability_uses_sample_sigma_and_reports_failures(self):
        rows = self.records()
        rows.append({**rows[0], 'frame_id': 'failed', 'success': False})
        result = repeatability(rows, min_frames=3, target_three_sigma_mm=.5)
        np.testing.assert_allclose(result['three_sigma_mm'], .3)
        self.assertEqual(result['failure_rate'], .25)
        self.assertFalse(result['production_accepted'])

    def test_repeated_frame_or_mixed_load_not_repeatability(self):
        rows = self.records(); rows[1]['frame_id'] = rows[0]['frame_id']
        with self.assertRaises(dp.LocalizationError):
            repeatability(rows, min_frames=3, target_three_sigma_mm=.5)
        rows = self.records(); rows[1]['condition_id'] = 'loaded'
        with self.assertRaises(dp.LocalizationError):
            repeatability(rows, min_frames=3, target_three_sigma_mm=.5)

    def test_grr_known_balanced_design(self):
        v = np.zeros((3,2,2,2,3))
        for p in range(3):
            for o, operator in enumerate([-.2,.2]):
                for r, noise in enumerate([-.1,.1]):
                    v[p,o,r] = 5*p+operator+noise
        result = crossed_grr(v, 10)
        np.testing.assert_allclose(result['repeatability_variance_mm2'], .02, atol=1e-12)
        np.testing.assert_allclose(result['operator_variance_mm2'], .08, atol=1e-12)
        np.testing.assert_allclose(result['grr_percent_tolerance'], 60*np.sqrt(.1), atol=1e-10)
        v[0,0,0,0,0] = np.nan
        with self.assertRaises(dp.LocalizationError):
            crossed_grr(v, 10)

    def test_exploratory_target_is_not_acceptance(self):
        study = {'repeatability_records': self.records(), 'acceptance': {
            'minFrames':3, 'exploratoryThreeSigmaMm':.5, 'verified':False,
            'maxThreeSigmaMm':None, 'maxGrrPercentTolerance':None, 'maxFailureRate':None}}
        result = acceptance_report(study)
        self.assertFalse(result['production_accepted'])
        self.assertNotIn('statistical_limits_passed', result)

    def test_cloud_forensics_requires_no_image_or_2d_rois(self):
        cloud = np.ones((8,8,3))*1000
        cloud[:4] = np.nan
        result = cloud_forensics(cloud, 'mm')
        self.assertEqual(result['valid_ratio'], .5)
        self.assertEqual(result['stage'], 'before_2d')
        self.assertFalse(result['production_ready'])
        self.assertIn('geometry_blocker', result)
        self.assertNotIn('xyz_percentiles_mm', cloud_forensics(cloud, None))

    def test_local_plane_and_line_forensics_preserve_failure_reasons(self):
        x,y = np.meshgrid(np.linspace(-10,10,20), np.linspace(-5,5,10))
        p = np.column_stack([x.ravel(),y.ravel(),np.full(x.size,1000)])
        region = {'boundsMm':[[-11,-6,999],[11,6,1001]], 'planeRansacMm':.1,
                  'lineRansacMm':.1, 'min_points':30, 'iterations':40}
        report = cloud_forensics(p,'mm',{'beam':region})['regions']['beam']
        self.assertTrue(report['plane']['fit_available'])
        self.assertFalse(report['line']['fit_available'])
        self.assertIn('reason', report['line'])
