"""REAL 模式结构性测试（用假相机服务，无需真实硬件）。Requirements: 14/16/17

验证 REAL 数据链路可跑通：
- RealHandEyeProvider   从配方 hand_eye_config 读矩阵
- RealRobotPoseProvider 从配方 capture_pose 读位姿（无机器人服务时回退）
- RealDepthCameraProvider 归一化 SDK 各种点云形态 + 从注入服务取帧
- RackPositioningService(mode='REAL') 端到端
"""

from decimal import Decimal

import numpy as np
from django.test import TestCase

from apps.vision.models import RackLocationRecipe, RackLocationROI3DEnhanced
from apps.vision.rack_3d.providers import (
    MockHandEyeProvider,
    MockDepthCameraProvider,
    RealDepthCameraProvider,
    RealHandEyeProvider,
    RealRobotPoseProvider,
)
from apps.vision.rack_3d.services import RackPositioningService
from apps.vision.rack_3d.exceptions import PointCloudError

from .test_services import ROIS, LAYER


class FakeDMCameraService:
    """模拟 apps.dm_camera 的 DMCameraService，返回预置点云帧。"""

    def __init__(self, data, width, height):
        self._data, self._w, self._h = data, width, height
        self.is_connected = True
        self.is_streaming = True

    def capture_frame_data(self, frame_type='POINTCLOUD', save_record=False):
        return {
            'data': self._data, 'width': self._w, 'height': self._h,
            'frame_index': 4321, 'frame_type': frame_type,
        }


class RealDepthNormalizeTest(TestCase):
    def test_normalize_shapes(self):
        p = RealDepthCameraProvider(dm_camera_service=object())
        n3 = np.zeros((10, 3))
        self.assertEqual(p._normalize_pointcloud(n3, 0, 0).shape, (10, 3))
        hwc = np.zeros((4, 5, 3))
        self.assertEqual(p._normalize_pointcloud(hwc, 5, 4).shape, (4, 5, 3))
        flat = np.zeros(4 * 5 * 3)
        self.assertEqual(p._normalize_pointcloud(flat, 5, 4).shape, (4, 5, 3))
        self.assertEqual(p._normalize_pointcloud(None, 0, 0).size, 0)

    def test_empty_frame_raises(self):
        svc = FakeDMCameraService(np.empty((0, 3)), 0, 0)
        with self.assertRaises(PointCloudError):
            RealDepthCameraProvider(svc).capture_pointcloud()


class RealProvidersFromRecipeTest(TestCase):
    def setUp(self):
        # 用 Mock 手眼矩阵 + Mock L2 拍照位姿写入配方，使 REAL 变换等价于 MOCK L2
        he = MockHandEyeProvider().get_hand_eye_matrix().tolist()
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='REAL-Demo-POS1-L2',
            position_no=1, layer_no=LAYER, layer_count=3,
            standard_x=Decimal('900'), standard_y=Decimal('530'), standard_z=Decimal('1220'),
            confidence_threshold=Decimal('0.5000'),
            hand_eye_config={'matrix': he},
            capture_pose={'x': 1000, 'y': 500, 'z': 900, 'rx': 0, 'ry': 0, 'rz': 0},
        )
        for roi_type, bounds in ROIS.items():
            RackLocationROI3DEnhanced.objects.create(
                recipe=self.recipe, roi_name=f'L{LAYER}-{roi_type}', roi_type=roi_type,
                position_no=1, layer_no=LAYER,
                **{k: Decimal(str(v)) for k, v in bounds.items()},
            )

    def test_real_hand_eye_from_config(self):
        m = RealHandEyeProvider().get_hand_eye_matrix(self.recipe.id)
        self.assertEqual(m.shape, (4, 4))
        np.testing.assert_allclose(m[:3, 3], [30, -60, 120])

    def test_real_robot_pose_from_capture_pose(self):
        m = RealRobotPoseProvider().get_robot_pose_matrix(LAYER, self.recipe.id)
        np.testing.assert_allclose(m[:3, 3], [1000, 500, 900])

    def test_real_end_to_end_with_fake_camera(self):
        pc = MockDepthCameraProvider(seed=7).capture_pointcloud()
        fake = FakeDMCameraService(pc['data'], pc['width'], pc['height'])
        svc = RackPositioningService(mode='REAL', dm_camera_service=fake)

        result = svc.execute_positioning(self.recipe.id, LAYER, save=True)

        self.assertTrue(result['is_success'], msg=result.get('error_message'))
        self.assertEqual(result['mode'], 'REAL')
        self.assertAlmostEqual(result['actual_z'], 1220, delta=5)
        self.assertAlmostEqual(result['actual_x'], 900, delta=5)
        self.assertIn('result_id', result)
