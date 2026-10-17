import copy
import numpy as np
from django.test import SimpleTestCase
from .rack_robot_points import robot_point_difference


class RobotPointsTests(SimpleTestCase):
    def test_legacy_invalidated_template_can_produce_offsets(self):
        context = {'T_flange_camera': np.eye(4).tolist(), 'T_base_flange': np.eye(4).tolist()}
        standard = {'success': True, 'coordinateSystem': 'camera', 'unit': 'mm',
                    'points': [{'name': n, 'success': True, 'xyz': [1, 2, 3]} for n in ('P1', 'P2')]}
        current = copy.deepcopy(standard)
        current['points'][0]['xyz'] = [4, 6, 8]
        reference = {'measurement': standard, 'invalidated_reason': 'ROI 已改变，请重新示教'}
        result = robot_point_difference(current, reference, context)
        np.testing.assert_allclose(result['offsets'], [[3, 4, 5], [0, 0, 0]])
        self.assertFalse(result['plc_publish_allowed'])

    def test_raw_camera_delta_rotates_and_translation_cancels(self):
        hand = np.eye(4); hand[:3, 3] = [100, 200, 300]
        pose = np.array([[0,-1,0,1000],[1,0,0,2000],[0,0,1,3000],[0,0,0,1]], float)
        context = {'T_flange_camera': hand.tolist(), 'T_base_flange': pose.tolist()}
        standard = {'success': True, 'coordinateSystem': 'camera', 'unit': 'mm',
                    'points': [{'name': name, 'success': True, 'xyz': [10,20,30]} for name in ('P1','P2')]}
        current = copy.deepcopy(standard)
        current['points'][0]['xyz'] = [11,22,33]
        current['points'][1]['xyz'] = [9,18,27]
        result = robot_point_difference(current, {'measurement':standard}, context)
        np.testing.assert_allclose(result['offsets'], [[-2,1,3],[2,-1,-3]])
        self.assertTrue(result['same_pose_assumed'])
        self.assertFalse(result['plc_publish_allowed'])

    def test_distinct_template_pose_is_used(self):
        context = {'T_flange_camera': np.eye(4).tolist(), 'T_base_flange': np.eye(4).tolist()}
        standard = {'success':True, 'coordinateSystem':'camera', 'unit':'mm',
                    'points':[{'name':n,'success':True,'xyz':[1,2,3]} for n in ('P1','P2')],
                    'robot_transform_context':copy.deepcopy(context)}
        current = copy.deepcopy(standard)
        context['T_base_flange'][0][3] = 50
        result = robot_point_difference(current, {'measurement':standard}, context)
        np.testing.assert_allclose(result['offsets'], [[50,0,0],[50,0,0]])
        self.assertFalse(result['same_pose_assumed'])
        context['T_flange_camera'][0][3] = 10
        with self.assertRaisesRegex(ValueError, '手眼矩阵'):
            robot_point_difference(current, {'measurement':standard}, context)

    def test_missing_template_does_not_produce_offsets(self):
        context = {'T_flange_camera':np.eye(4).tolist(), 'T_base_flange':np.eye(4).tolist()}
        with self.assertRaises(ValueError):
            robot_point_difference({}, None, context)
