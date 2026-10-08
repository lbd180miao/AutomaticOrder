import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase
from PIL import Image

from .offline_data_service import OfflineDataPackageError, OfflineDataPackageService


class Offline2DPreviewTests(SimpleTestCase):
    def test_camera_image_wins_over_depth_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            service = OfflineDataPackageService(directory)
            package = Path(directory) / 'capture'
            package.mkdir()
            for name in ('depth_preview.png', 'preview.png', 'IMAGE2D.PNG'):
                Image.new('RGB', (4, 3)).save(package / name)
            self.assertEqual(service.get_raw_preview('capture').name, 'IMAGE2D.PNG')
            self.assertEqual(service.get_2d_image('capture').name, 'IMAGE2D.PNG')

    def test_depth_only_package_reports_missing_camera_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = OfflineDataPackageService(directory)
            package = Path(directory) / 'capture'
            package.mkdir()
            Image.new('RGB', (4, 3)).save(package / 'preview.png')
            with self.assertRaisesMessage(OfflineDataPackageError, '2D'):
                service.get_2d_image('capture')

    def test_raw_load_keeps_cloud_but_selects_2d_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            service = OfflineDataPackageService(directory)
            package = Path(directory) / 'capture'
            package.mkdir()
            Image.new('RGB', (4, 3)).save(package / 'image2d.png')
            cloud = np.ones((3, 4, 3), dtype=np.float32)
            data = dict(pointcloud=cloud, metadata={}, roi_config={}, result=None)
            with patch.object(service, 'load_raw_package', return_value=data), patch(
                'apps.vision.rack_location.RackLocationService._persist_workbench_frame',
                return_value=('cloud.npy', '/depth.png', 4, 3),
            ) as persist:
                result = service.create_workbench_copy_from_raw('capture')
            self.assertIs(persist.call_args.args[0], cloud)
            self.assertEqual(result['pointcloud_token'], 'cloud.npy')
            self.assertIn('raw-preview/?image=2d', result['preview_image_url'])
