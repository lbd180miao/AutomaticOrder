"""A capture never replaces the saved standard; missing references are optional."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from django.test import SimpleTestCase

from . import rack_spatial_service as service


class StandardReferenceTests(SimpleTestCase):
    def test_unsaved_frame_keeps_previous_standard_and_computes_delta(self):
        standard = {key: {'frame': np.eye(4).tolist()} for key in ('A', 'B')}
        recipe = SimpleNamespace(pk=8, roi_config={}, local_template_std={
            'source_result_id': 337,
            'dual_axis_standard': {'recipe_id': 8, 'source_result_id': 337, 'groups': standard},
        })
        before = deepcopy(recipe.local_template_std)
        current = deepcopy(standard)
        current['A']['frame'][0][3] = 12
        current['B']['frame'][1][3] = -7
        with patch.object(service, 'legacy_axis_frames', return_value=current), \
                patch.object(service, 'robot_group_results', side_effect=lambda s, r, g: {'robot_groups': g}), \
                patch.object(service.RackLocationResult.objects, 'get') as lookup:
            result = service.legacy_robot_groups(Mock(), recipe, None, {})
        self.assertEqual(result['robot_groups_status'], 'ready')
        self.assertEqual(result['robot_groups_reference_result_id'], 337)
        self.assertEqual(result['robot_groups']['A']['delta_T'][0][3], 12)
        self.assertEqual(result['robot_groups']['B']['delta_T'][1][3], -7)
        self.assertEqual(recipe.local_template_std, before)
        lookup.assert_not_called()  # Frozen standard works even without the raw cloud.

    def test_missing_old_cloud_does_not_fail_current_measurement(self):
        recipe = SimpleNamespace(pk=8, roi_config={}, local_template_std={'source_result_id': 337})
        record = SimpleNamespace(pk=337, recipe_id=8, raw_data_path='missing.npy')
        loader = Mock()
        loader._load_workbench_pointcloud.side_effect = ValueError('点云文件缺失')
        with patch.object(service.RackLocationResult.objects, 'get', return_value=record):
            result = service.legacy_robot_groups(loader, recipe, None, {})
        self.assertEqual(result['robot_groups_status'], 'standard_unavailable')
        self.assertEqual(result['robot_conversion_error'], '')
        self.assertEqual(result['robot_groups'], {})
        self.assertIn('#337', result['standard_reference_diagnostic'])
        self.assertEqual(recipe.local_template_std, {'source_result_id': 337})

    def test_current_fit_failure_is_not_hidden_as_missing_standard(self):
        recipe = SimpleNamespace(pk=8, roi_config={}, local_template_std={
            'source_result_id': 337,
            'dual_axis_standard': {'recipe_id': 8, 'source_result_id': 337, 'groups': {}},
        })
        with patch.object(service, 'legacy_axis_frames', side_effect=ValueError('当前帧点数不足')):
            result = service.legacy_robot_groups(Mock(), recipe, None, {})
        self.assertEqual(result['robot_groups_status'], 'calculation_failed')
        self.assertIn('当前帧点数不足', result['robot_conversion_error'])
