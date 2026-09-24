"""RVC 相机应用单元测试（不依赖真实相机/独立服务，HTTP 层全部 mock）。"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.rvc_camera.client import (
    RvcCameraClient,
    RvcCameraConfigurationError,
    RvcCameraError,
)
from apps.rvc_camera.services import RvcCameraService


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class RvcCameraClientTests(TestCase):
    def setUp(self):
        # 单例服务可能被其它测试实例化，重置其 client
        RvcCameraService._instance = None

    def test_status_success(self):
        client = RvcCameraClient(base_url="http://127.0.0.1:8001")
        client._session = MagicMock()
        client._session.request.return_value = FakeResponse(
            {"success": True, "data": {"connected": True}}
        )
        self.assertTrue(client.status()["connected"])

    def test_connection_error_has_chinese_hint(self):
        import requests
        client = RvcCameraClient(base_url="http://127.0.0.1:8001")
        client._session = MagicMock()
        client._session.request.side_effect = requests.exceptions.ConnectionError("boom")
        with self.assertRaises(RvcCameraError) as ctx:
            client.status()
        self.assertIn("python -m rvc_service", str(ctx.exception))

    def test_bad_request_maps_to_configuration_error(self):
        client = RvcCameraClient(base_url="http://127.0.0.1:8001")
        client._session = MagicMock()
        client._session.request.return_value = FakeResponse(
            {"success": False, "error": "不支持的 RVC 采集模式: X"}, status_code=400
        )
        with self.assertRaises(RvcCameraConfigurationError):
            client.set_mode("X")


@override_settings()
class RvcCameraServiceCaptureTests(TestCase):
    def setUp(self):
        RvcCameraService._instance = None
        self.tmp_media = Path(settings.MEDIA_ROOT) / "_rvc_test_tmp"
        self.tmp_media.mkdir(parents=True, exist_ok=True)
        # 造一份服务"采集"出来的点云 npy + 2D png
        self.cloud = (np.ones((3, 4, 3), dtype=np.float64) *
                      np.array([1.0, 2.0, 300.0]))
        self.npy = self.tmp_media / "pointcloud_000001.npy"
        np.save(self.npy, self.cloud)
        from PIL import Image
        self.png = self.tmp_media / "image2d_000001.png"
        Image.new("RGB", (4, 3), (10, 20, 30)).save(self.png)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_media, ignore_errors=True)
        RvcCameraService._instance = None

    def test_capture_frame_data_matches_dm_contract(self):
        fake_client = MagicMock()
        fake_client.capture.return_value = {
            "frame_index": 7,
            "mode": "Robust",
            "width": 4,
            "height": 3,
            "point_count": 12,
            "image_width": 4,
            "image_height": 3,
            "pointcloud_npy": str(self.npy),
            "pointcloud_ply": "",
            "image_2d": str(self.png),
        }
        svc = RvcCameraService(client=fake_client)
        frame = svc.capture_frame_data("POINTCLOUD", save_record=False)

        self.assertEqual(frame["source"], "rvc_camera")
        self.assertEqual(frame["frame_type"], "POINTCLOUD")
        self.assertEqual(frame["width"], 4)
        self.assertEqual(frame["height"], 3)
        self.assertEqual(frame["frame_index"], 7)
        self.assertEqual(frame["data"].shape, (3, 4, 3))
        self.assertTrue(frame["raw_data_path"].endswith("pointcloud_000001.npy"))
        self.assertIn("/media/", frame["preview_url"])
        np.testing.assert_array_equal(frame["data"], self.cloud)

    def test_unsupported_frame_type_raises(self):
        svc = RvcCameraService(client=MagicMock())
        with self.assertRaises(RvcCameraError):
            svc.capture_frame_data("IR")


class RvcCameraViewTests(TestCase):
    def setUp(self):
        RvcCameraService._instance = None

    def test_demo_page(self):
        resp = self.client.get(reverse("rvc_camera:demo"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RVC 3D 相机控制台")

    @patch("apps.rvc_camera.views.service")
    def test_status_api(self, mock_service):
        mock_service.get_status.return_value = {"connected": True, "mode": "Robust"}
        resp = self.client.get(reverse("rvc_camera:status"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["mode"], "Robust")

    @patch("apps.rvc_camera.views.service")
    def test_capture_api_strips_numpy(self, mock_service):
        mock_service.capture_frame_data.return_value = {
            "data": np.zeros((2, 2, 3)),
            "width": 2,
            "height": 2,
            "source": "rvc_camera",
        }
        resp = self.client.post(
            reverse("rvc_camera:capture"),
            data=json.dumps({"frame_type": "POINTCLOUD"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["data"]
        self.assertNotIn("data", payload)
        self.assertEqual(payload["width"], 2)
