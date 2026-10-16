from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from PIL import Image
from django.test import SimpleTestCase, override_settings
from .offline_data_service import OfflineDataPackageService
from .rack_location import RackLocationService


class OfflinePackageLoadingTests(SimpleTestCase):
    def test_details_and_list_do_not_decode_ply_coordinates(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            folder = Path(directory) / 'raw'
            folder.mkdir()
            # Header is sufficient for browsing; invalid payload must fail on load.
            (folder / 'PointCloud.ply').write_bytes(
                b'ply\nformat ascii 1.0\nelement vertex 6\nproperty float x\n'
                b'property float y\nproperty float z\nend_header\ninvalid payload\n')
            Image.new('RGB', (3, 2)).save(folder / 'preview.png')
            service = OfflineDataPackageService(directory)
            with patch.object(service, 'load_raw_package', side_effect=AssertionError('full load')):
                detail = service.package_detail('raw')
                self.assertEqual(detail['pointcloud_shape'], [2, 3, 3])
                self.assertEqual(service.list_packages(include_raw=True)[0]['point_count'], 6)
            self.assertEqual(service.get_raw_preview('raw'), folder / 'preview.png')

    def test_standard_detail_keeps_metadata_without_loading_coordinates(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            folder = Path(directory) / 'saved'
            folder.mkdir()
            np.save(folder / 'pointcloud.npy', np.ones((2, 3, 3)))
            for name in ('hand_eye_matrix.npy', 'robot_pose_matrix.npy'):
                np.save(folder / name, np.eye(4))
            (folder / 'metadata.json').write_text('{"package_name":"saved","point_count":6}')
            (folder / 'roi_config.json').write_text('{"example":1}')
            service = OfflineDataPackageService(directory)
            with patch.object(service, 'load_package', side_effect=AssertionError('full load')):
                detail = service.package_detail('saved')
            self.assertEqual(detail['pointcloud_shape'], [2, 3, 3])
            self.assertEqual(detail['roi_config'], {'example': 1})

    def test_skip_preview_preserves_cloud_and_provenance(self):
        cloud = np.arange(18, dtype=np.float32).reshape(2, 3, 3)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory, override_settings(MEDIA_ROOT=directory):
            service = RackLocationService()
            with patch('apps.vision.rack_location.image_io.pointcloud_to_preview',
                       side_effect=AssertionError('unused preview')):
                token, url, width, height = service._persist_workbench_frame(
                    cloud, capture_metadata={'source': 'offline_package:test'}, generate_preview=False)
            loaded = service._load_workbench_pointcloud(token)
            np.testing.assert_array_equal(loaded, cloud)
            self.assertEqual((url, width, height), ('', 3, 2))
            self.assertEqual(service._frame_metadata(token, loaded)['source'], 'offline_package:test')

