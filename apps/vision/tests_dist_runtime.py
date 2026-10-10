"""Regression checks for source/frozen runtime and missing depth data."""
import importlib.util
import os
from pathlib import Path
import runpy
import sys
import tempfile
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase, override_settings

from .rack_location import RackLocationService, _measure_layer_spacing_line
from .rack_spatial_service import reference_axes_from_record
from .models import RackLocationRecipe

ROOT = Path(__file__).resolve().parents[2]


class DistRuntimeTests(SimpleTestCase):
    def test_numpy_algorithm_does_not_import_open3d(self):
        result = subprocess.run([sys.executable, '-c',
            'import sys; import apps.vision.rack_positioning_algorithm; assert "open3d" not in sys.modules'],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_workbench_returns_timings_and_explicit_robot_failure(self):
        yy, xx = np.mgrid[:30, :30]
        cloud = np.zeros((30, 90, 3), dtype=float)
        cloud[:, :30] = np.stack([xx, yy, np.full_like(xx, 1000)], axis=2)
        cloud[:, 30:60] = np.stack([np.full_like(xx, 40), yy, 1000 + xx], axis=2)
        cloud[:, 60:] = np.stack([xx, yy, np.full_like(xx, 1100)], axis=2)
        rois = {key: {'x': i * 30, 'y': 0, 'w': 30, 'h': 30}
                for i, key in enumerate(('plane1', 'plane2', 'plane3'))}
        recipe = RackLocationRecipe(pk=99, recipe_name='test', local_template_std={})
        service = RackLocationService()
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory), \
                patch.object(service, '_load_workbench_pointcloud', return_value=cloud), \
                patch.object(service, '_recipe_transform_context', return_value={}):
            result = service._calculate_local_template_workbench(token='test.npy',
                roi_config={'local_template_rois': rois}, recipe=recipe, layer_no=1, save_record=False)
            self.assertTrue((Path(directory) / result['result_image_path']).is_file())
            self.assertTrue(result['result_image_path'].endswith('.jpg'))
        self.assertGreater(result['timings']['total_ms'], 0)
        self.assertEqual(result['robot_groups'], {})
        self.assertIn('旧标准缺少来源点云记录', result['robot_conversion_error'])

    def test_frozen_data_is_outside_bundle_and_cwd(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', str(ROOT / 'deployment' / 'app.exe')):
            config = runpy.run_path(str(ROOT / 'AutomaticOrder' / 'settings.py'))
        self.assertEqual(config['MEDIA_ROOT'], ROOT / 'deployment' / 'media')
        self.assertEqual(config['DATABASES']['default']['NAME'], ROOT / 'deployment' / 'db.sqlite3')

    def test_explicit_data_directory(self):
        with patch.dict(os.environ, {'AUTOMATIC_ORDER_DATA_DIR': str(ROOT / 'persistent')}, clear=True):
            config = runpy.run_path(str(ROOT / 'AutomaticOrder' / 'settings.py'))
        self.assertEqual(config['MEDIA_ROOT'], ROOT / 'persistent' / 'media')

    def test_camera_dispatch_does_not_initialize_django(self):
        spec = importlib.util.spec_from_file_location('runtime_entry', ROOT / 'run.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        camera = SimpleNamespace(main=lambda argv: argv)
        with patch.dict(sys.modules, {'rvc_service.__main__': camera}), patch('django.setup') as setup:
            self.assertEqual(entry.main(['--rvc-service', '--port', '8123']), ['--port', '8123'])
            setup.assert_not_called()
        self.assertEqual(entry.positive_threads('8'), 8)
        with self.assertRaises(Exception):
            entry.positive_threads('0')

    def test_server_receives_requested_threads(self):
        spec = importlib.util.spec_from_file_location('runtime_entry', ROOT / 'run.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch('django.setup'), patch('django.core.wsgi.get_wsgi_application', return_value='wsgi'), \
                patch('waitress.serve') as serve:
            entry.main(['--threads', '12', '--port', '8120'])
        serve.assert_called_once_with('wsgi', host='127.0.0.1', port=8120, threads=12)

    def test_missing_standard_identifies_record(self):
        service = SimpleNamespace(_load_workbench_pointcloud=lambda token: (_ for _ in ()).throw(ValueError('missing')))
        with self.assertRaisesRegex(ValueError, '标准记录 #337'):
            reference_axes_from_record(service, SimpleNamespace(pk=8),
                                       SimpleNamespace(recipe_id=8, pk=337, raw_data_path='missing.npy'))

    def test_pointcloud_loader_rejects_escape(self):
        with override_settings(MEDIA_ROOT=ROOT / 'media'):
            with self.assertRaisesRegex(ValueError, '路径不在'):
                RackLocationService._load_workbench_pointcloud(None, '../outside.npy')

    def test_valid_spacing_keeps_depth_surface(self):
        yy, xx = np.mgrid[:60, :100]
        cloud = np.stack([xx, yy, np.full_like(xx, 1000)], axis=2).astype(float)
        distance, detail = _measure_layer_spacing_line(cloud, {'x1': 20, 'y1': 30, 'x2': 70, 'y2': 30})
        self.assertAlmostEqual(distance, 50)
        self.assertGreaterEqual(detail['endpoints'][1]['sample_count'], 8)

    def test_missing_depth_is_not_turned_into_fake_spacing(self):
        yy, xx = np.mgrid[:60, :100]
        cloud = np.stack([xx, yy, np.full_like(xx, 1000)], axis=2).astype(float)
        cloud[:, 55:, 2] = 0  # Nonzero X/Y must not make missing Z valid.
        with self.assertRaisesRegex(ValueError, '端点2.*仅0点'):
            _measure_layer_spacing_line(cloud, {'x1': 20, 'y1': 30, 'x2': 70, 'y2': 30})

    def test_unorganized_cloud_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'H×W×3'):
            _measure_layer_spacing_line(np.ones((100, 3)), {})
