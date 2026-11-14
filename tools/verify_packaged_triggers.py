"""Run PLC regressions against code extracted from a built EXE, without hardware."""
import os
import sys
import types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
from PyInstaller.archive.readers import CArchiveReader
from django.test.runner import DiscoverRunner
import importlib
archive = CArchiveReader(str(Path(sys.argv[1]) / 'AGVControl.exe'))
pyz = archive.open_embedded_archive('PYZ.pyz')

def signature(code):
    return (code.co_code, code.co_names, code.co_varnames,
            tuple(signature(c) if isinstance(c, types.CodeType) else c for c in code.co_consts))

for name in ('apps.devices.plc_db100', 'apps.devices.adapters.plc',
             'apps.workflow.plc_inputs', 'apps.workflow.station_service',
             'apps.workflow.listener', 'apps.devices.plc_foam_debug',
             'apps.devices.plc_position_debug', 'apps.core.barcode_validator',
             'apps.devices.views', 'deployment'):
    code = pyz.extract(name)
    source_path = ROOT / (name.replace('.', '/') + '.py')
    source = compile(source_path.read_text(encoding='utf-8'), code.co_filename, 'exec')
    assert signature(code) == signature(source), f'Packaged module differs: {name}'
    module = importlib.import_module(name)
    exec(code, module.__dict__)
failed = DiscoverRunner(verbosity=1, interactive=False).run_tests([
    'apps.workflow.tests_dual_rack', 'apps.devices.tests_plc_first_group.FirstGroupTests',
    'apps.devices.tests_plc_first_group.NewDBContractTests', 'apps.workflow.tests_listener'])
print('Packaged modules match source; regression failures:', failed)
raise SystemExit(bool(failed))
