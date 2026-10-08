import json
from unittest.mock import patch

import numpy as np
from django.test import RequestFactory, SimpleTestCase

from .rack_location import PointcloudRoiError, RackLocationService
from .views import api_rack_location_workbench_calculate


class RackWorkbenchFeedbackTests(SimpleTestCase):
    def setUp(self):
        self.cloud = np.ones((10, 30, 3), dtype=np.float32)
        self.regions = {
            f'plane{index + 1}': {'x': index * 10, 'y': 0, 'w': 10, 'h': 10}
            for index in range(3)
        }

    def test_valid_regions_still_return_three_clouds(self):
        clouds = RackLocationService._crop_local_template_clouds(self.cloud, self.regions)
        self.assertEqual([cloud.shape for cloud in clouds], [(100, 3)] * 3)

    def test_reports_all_invalid_regions_including_nan_and_zero_depth(self):
        self.cloud[:, :10] = np.nan
        self.cloud[:, 20:, 2] = 0
        with self.assertRaises(PointcloudRoiError) as caught:
            RackLocationService._crop_local_template_clouds(self.cloud, self.regions)
        error = caught.exception
        self.assertEqual(error.invalid_roi_keys, ['plane1', 'plane3'])
        self.assertEqual(error.roi_diagnostics['plane2']['valid_points'], 100)
        self.assertEqual(error.roi_diagnostics['plane1'], {'valid_points': 0, 'total_points': 100})

    def test_minimum_valid_point_boundary(self):
        self.cloud[:5, :, 2] = 0
        self.assertEqual(
            [len(cloud) for cloud in RackLocationService._crop_local_template_clouds(self.cloud, self.regions)],
            [50, 50, 50],
        )
        self.cloud[5, 0, 2] = 0
        with self.assertRaises(PointcloudRoiError) as caught:
            RackLocationService._crop_local_template_clouds(self.cloud, self.regions)
        self.assertEqual(caught.exception.invalid_roi_keys, ['plane1'])

    @patch('apps.vision.views.RackLocationService')
    def test_api_exposes_roi_diagnostics_without_saving_result(self, service):
        service.return_value.calculate_workbench.side_effect = PointcloudRoiError({
            'plane1': {'valid_points': 0, 'total_points': 100},
        })
        request = RequestFactory().post(
            '/vision/api/rack-location/workbench/calculate/',
            data=json.dumps({'pointcloud_token': 'test-frame'}),
            content_type='application/json',
        )
        response = api_rack_location_workbench_calculate(request)
        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['invalid_roi_keys'], ['plane1'])
        self.assertEqual(payload['roi_diagnostics']['plane1']['valid_points'], 0)
        self.assertEqual([payload['plc_payload'][f'offset_{axis}'] for axis in 'xyz'], [999.0] * 3)
        self.assertFalse(payload['plc_payload']['compensation_valid'])
        self.assertFalse(payload['plc_payload']['position_success'])
