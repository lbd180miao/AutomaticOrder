import tempfile
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from django.test import RequestFactory, SimpleTestCase

from .offline_data_service import OfflineDataPackageError, OfflineDataPackageService
from .offline_data_views import packages
from .rack_3d.providers import (
    OfflineDepthCameraProvider,
    OfflineHandEyeProvider,
    OfflineRobotPoseProvider,
    ProviderFactory,
)


class OfflineDataPackageServiceTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = OfflineDataPackageService(self.temp_dir.name)
        self.recipe = SimpleNamespace(
            id=7,
            recipe_name="离线测试配方",
            position_no=1,
            rack_side="BOTH",
            standard_x=1000,
            standard_y=500,
            standard_z=800,
            max_offset_x=10,
            max_offset_y=10,
            max_offset_z=10,
            confidence_threshold=0.7,
            capture_pose={"X": 1, "Y": 2, "Z": 3},
        )
        y, x = np.mgrid[0:12, 0:16]
        self.pointcloud = np.dstack((x, y, np.full_like(x, 100))).astype(np.float32)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_list_load_and_delete_round_trip(self):
        created = self.service.create_package(
            pointcloud=self.pointcloud,
            hand_eye_matrix=np.eye(4),
            robot_pose_matrix=np.eye(4),
            roi_config={"x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10, "z_min": 50, "z_max": 150},
            recipe=self.recipe,
            layer_no=2,
            camera_info={"source": "unit_test", "width": 16, "height": 12},
            result={"is_success": True, "confidence": 0.9},
        )

        package_name = created["package_name"]
        self.assertEqual(self.service.list_packages()[0]["package_name"], package_name)
        loaded = self.service.load_package(package_name)
        np.testing.assert_array_equal(loaded["pointcloud"], self.pointcloud)
        np.testing.assert_array_equal(loaded["hand_eye_matrix"], np.eye(4))
        self.assertEqual(loaded["metadata"]["layer"]["layer_no"], 2)
        self.assertTrue(self.service.preview_path(package_name).is_file())
        self.assertTrue(Path(self.temp_dir.name, "index.json").is_file())

        self.assertTrue(self.service.delete_package(package_name))
        self.assertEqual(self.service.list_packages(), [])
        with self.assertRaises(OfflineDataPackageError):
            self.service.load_package(package_name)

    def test_rejects_path_traversal_and_invalid_pointcloud(self):
        with self.assertRaises(OfflineDataPackageError):
            self.service.load_package("../outside")
        with self.assertRaises(OfflineDataPackageError):
            self.service.create_package(
                pointcloud=np.ones((5, 2)),
                hand_eye_matrix=np.eye(4),
                robot_pose_matrix=np.eye(4),
                roi_config={},
                recipe=self.recipe,
                layer_no=1,
                camera_info={},
            )

    def test_raw_package_restores_organized_cloud_and_workbench_token(self):
        raw_dir = Path(self.temp_dir.name, "4")
        raw_dir.mkdir()
        np.save(raw_dir / "pointcloud.npy", self.pointcloud.reshape(-1, 3), allow_pickle=False)
        Image.new("RGB", (16, 12), color=(20, 30, 40)).save(raw_dir / "Image.png")

        loaded = self.service.load_raw_package("4")

        self.assertEqual(loaded["pointcloud"].shape, (12, 16, 3))
        self.assertEqual(loaded["metadata"]["camera"], {"width": 16, "height": 12})
        with self.settings(MEDIA_ROOT=self.temp_dir.name):
            payload = self.service.create_workbench_copy_from_raw("4")
            persisted = np.load(Path(self.temp_dir.name, payload["pointcloud_token"]))
        self.assertEqual(payload["image_width"], 16)
        self.assertEqual(payload["image_height"], 12)
        self.assertEqual(persisted.shape, (12, 16, 3))
        self.assertFalse(payload["pointcloud_token"].startswith("."))


class OfflineProviderTests(SimpleTestCase):
    def test_factory_accepts_offline_data_without_hardware(self):
        cloud = np.ones((4, 5, 3), dtype=np.float32)
        loaded = {"pointcloud": cloud, "metadata": {"camera": {"width": 5, "height": 4}}}
        depth = ProviderFactory.create_depth_camera_provider("OFFLINE", loaded_data=loaded)
        hand_eye = ProviderFactory.create_hand_eye_provider("OFFLINE", hand_eye_matrix=np.eye(4))
        robot = ProviderFactory.create_robot_pose_provider("OFFLINE", robot_pose_matrix=np.eye(4))

        self.assertIsInstance(depth, OfflineDepthCameraProvider)
        self.assertIsInstance(hand_eye, OfflineHandEyeProvider)
        self.assertIsInstance(robot, OfflineRobotPoseProvider)
        np.testing.assert_array_equal(depth.capture_pointcloud()["data"], cloud)


class OfflineDataPackageViewTests(SimpleTestCase):
    def test_create_requires_explicit_manual_save_marker(self):
        request = RequestFactory().post(
            "/vision/offline/packages/",
            data={"recipe_id": 1},
            content_type="application/json",
        )
        response = packages(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("手动创建", json.loads(response.content)["error"])
