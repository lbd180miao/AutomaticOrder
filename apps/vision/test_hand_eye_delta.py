import json

from django.test import TestCase
from django.urls import reverse

from apps.core.constants import DeviceType
from apps.devices.models import Device
from apps.vision.models_hand_eye import HandEyeCalibration


class HandEyeDeltaApiTests(TestCase):
    def setUp(self):
        robot = Device.objects.create(
            code='ROBOT-DELTA-TEST',
            name='偏差测试机器人',
            device_type=DeviceType.BOXING_ROBOT,
        )
        camera = Device.objects.create(
            code='CAMERA-DELTA-TEST',
            name='偏差测试相机',
            device_type=DeviceType.DEPTH_CAMERA,
        )
        self.calibration = HandEyeCalibration.objects.create(
            name='偏差转换测试标定',
            robot_device=robot,
            camera_device=camera,
            is_active=True,
            calibration_method='MANUAL',
            T_flange_camera={
                'matrix': [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            },
        )
        self.url = reverse('vision:compute_delta')

    @staticmethod
    def pose(**overrides):
        value = {'x': 0, 'y': 0, 'z': 0, 'rx': 0, 'ry': 0, 'rz': 0}
        value.update(overrides)
        return value

    def post_json(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_zero_delta_returns_zero_pose_and_identity_matrix(self):
        response = self.post_json({
            'delta_cam': self.pose(),
            'T_base_flange': self.pose(x=500, y=200, z=850, rz=37),
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        for value in data['delta_base'].values():
            self.assertAlmostEqual(value, 0.0, places=9)
        expected_identity = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        for actual_row, expected_row in zip(data['delta_T_base'], expected_identity):
            for actual, expected in zip(actual_row, expected_row):
                self.assertAlmostEqual(actual, expected, places=9)

    def test_known_translation_is_rotated_into_base_coordinates(self):
        response = self.post_json({
            'delta_cam': self.pose(x=10),
            'T_base_flange': self.pose(x=400, y=-120, z=700, rz=90),
            'calibration_id': self.calibration.id,
        })

        self.assertEqual(response.status_code, 200)
        delta = response.json()['data']['delta_base']
        self.assertAlmostEqual(delta['x'], 0.0, places=8)
        self.assertAlmostEqual(delta['y'], 10.0, places=8)
        self.assertAlmostEqual(delta['z'], 0.0, places=8)

    def test_manual_hand_eye_matrix_is_supported_for_ui_testing(self):
        response = self.post_json({
            'delta_cam': self.pose(x=12),
            'T_base_flange': self.pose(),
            'T_flange_camera': {
                'matrix': [
                    [0, -1, 0, 0],
                    [1, 0, 0, 0],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ]
            },
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIsNone(data['calibration_id'])
        self.assertEqual(data['calibration_name'], '手动输入')
        self.assertAlmostEqual(data['delta_base']['x'], 0.0, places=8)
        self.assertAlmostEqual(data['delta_base']['y'], 12.0, places=8)

    def test_invalid_requests_return_client_errors(self):
        invalid_json = self.client.post(self.url, data='{', content_type='application/json')
        self.assertEqual(invalid_json.status_code, 400)

        missing_field = self.post_json({
            'delta_cam': {'x': 0, 'y': 0, 'z': 0},
            'T_base_flange': self.pose(),
        })
        self.assertEqual(missing_field.status_code, 400)
        self.assertIn('缺少字段', missing_field.json()['error'])

        missing_calibration = self.post_json({
            'delta_cam': self.pose(),
            'T_base_flange': self.pose(),
            'calibration_id': 999999,
        })
        self.assertEqual(missing_calibration.status_code, 404)

        invalid_matrix = self.post_json({
            'delta_cam': self.pose(),
            'T_base_flange': self.pose(),
            'T_flange_camera': {'matrix': [[1, 0, 0, 0]] * 4},
        })
        self.assertEqual(invalid_matrix.status_code, 400)
        self.assertIn('最后一行', invalid_matrix.json()['error'])


class HandEyeCalculatorPageTests(TestCase):
    def test_page_contains_four_data_panels_and_api_controls(self):
        response = self.client.get(reverse('vision:hand_eye_page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '坐标转换计算器')
        self.assertContains(response, '<section class="he-panel', count=4)
        self.assertContains(response, 'id="computeButton"')
        self.assertContains(response, reverse('vision:compute_delta'))
        self.assertContains(response, 'T<sub>base_cam</sub>')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "'X-CSRFToken'")
        self.assertNotContains(response, 'data.success === false')
