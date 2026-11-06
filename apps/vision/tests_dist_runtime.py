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

from .rack_location import RackLocationService
from .models import RackLocationRecipe

ROOT = Path(__file__).resolve().parents[2]


class DistRuntimeTests(SimpleTestCase):
    def test_numpy_algorithm_does_not_import_open3d(self):
        result = subprocess.run([sys.executable, '-c',
            'import sys; import apps.vision.rack_cloud_match; assert "open3d" not in sys.modules'],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


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


    def test_pointcloud_loader_rejects_escape(self):
        with override_settings(MEDIA_ROOT=ROOT / 'media'):
            with self.assertRaisesRegex(ValueError, '路径不在'):
                RackLocationService._load_workbench_pointcloud(None, '../outside.npy')
