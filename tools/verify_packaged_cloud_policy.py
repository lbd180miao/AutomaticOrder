"""Verify the frozen 3D policy and PLC regressions without contacting hardware."""
import importlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import django
django.setup()
from PyInstaller.archive.readers import CArchiveReader
from django.test.runner import DiscoverRunner


def signature(code):
    return (code.co_code, code.co_names, code.co_varnames,
            tuple(signature(c) if isinstance(c, types.CodeType) else c for c in code.co_consts))


release = Path(sys.argv[1]).resolve()
archive = CArchiveReader(str(release / 'AGVControl.exe')).open_embedded_archive('PYZ.pyz')
for name in ('apps.vision.rack_cloud_match', 'apps.vision.rack_cloud_service',
             'apps.vision.rack_robot_points', 'apps.devices.plc_position_debug'):
    code = archive.extract(name)
    source = ROOT / (name.replace('.', '/') + '.py')
    assert signature(code) == signature(compile(source.read_text(encoding='utf-8'), code.co_filename, 'exec')), name
    exec(code, importlib.import_module(name).__dict__)
assert (release / 'templates/vision/task_detail.html').read_bytes() == (ROOT / 'templates/vision/task_detail.html').read_bytes()
failed = DiscoverRunner(verbosity=1, interactive=False).run_tests([
    'apps.vision.tests_cloud_match', 'apps.vision.tests_cloud_service',
    'apps.devices.tests_plc_first_group.FirstGroupTests',
    'apps.devices.tests_plc_first_group.LayerResultContractTests',
])
print('Frozen 3D policy matches source; test failures:', failed)
raise SystemExit(bool(failed))
