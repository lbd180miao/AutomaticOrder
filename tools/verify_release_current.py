"""Verify current runtime code and continuous detection templates in both EXEs."""
import json
import sys
import types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve()


def signature(code):
    return (code.co_code, code.co_names, code.co_varnames,
            tuple(signature(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


report = {}
for role in ('AGVControl', 'ExternalControl'):
    folder = release / role
    archive = CArchiveReader(str(folder / (role + '.exe'))).open_embedded_archive('PYZ.pyz')
    modules = ('apps.vision.foam_live', 'apps.vision.foam_ng_log', 'apps.vision.algorithms.foam_stream',
               'apps.workflow.station_service', 'apps.workflow.plc_inputs', 'apps.devices.views',
               'apps.devices.inspection_events', 'apps.devices.plc_position_debug', 'deployment')
    for module in modules:
        code = archive.extract(module)
        source = ROOT / (module.replace('.', '/') + '.py')
        assert signature(code) == signature(compile(source.read_text(encoding='utf-8'), code.co_filename, 'exec')), module
    for relative in ('static/devices/foam_live_status.js', 'static/vision/js/foam_stream.js',
                     'templates/devices/latest_inspections.html', 'templates/devices/status.html'):
        assert (folder / relative).read_bytes() == (ROOT / relative).read_bytes(), relative
    profile = folder / 'media/vision/foam_stream_templates/pic2/profile.json'
    for view in json.loads(profile.read_text(encoding='utf-8'))['views']:
        assert (profile.parent / view['image']).is_file(), view['image']
    assert not (folder / 'foam_ng.sqlite3').exists(), 'Development NG history must not ship'
    report[role] = {'current_modules_verified': list(modules), 'templates_verified': True}
(release / 'current-runtime-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('PASS: both executables contain current continuous detection, NG logging and PLC runtime code.')
