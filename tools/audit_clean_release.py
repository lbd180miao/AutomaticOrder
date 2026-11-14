"""Verify clean deployment files and preserved recipe/calibration tables."""
import json
import sqlite3
import sys
from pathlib import Path
from packaging_resources import is_visual_data, UI_ASSET_PATHS

root = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve()
history = ('vision_visiontask', 'vision_visionimage', 'vision_racklocationresult',
           'vision_foaminspectionresult', 'vision_racklayermeasurement')
with sqlite3.connect(root / 'db.sqlite3') as source:
    tables = [row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
              if any(word in row[0] for word in ('recipe', 'calibration', 'measurementprofile'))]
    expected = {table: source.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in tables}
report = {}
for role in (('AGVControl',) if '--agv-only' in sys.argv else ('AGVControl', 'ExternalControl')):
    folder = release / role
    manifest = json.loads((folder / 'resource-manifest.json').read_text(encoding='utf-8'))
    allowed = {entry['path'] for entry in manifest['files']}
    assert UI_ASSET_PATHS <= allowed, 'UI icon manifest is incomplete'
    for relative in UI_ASSET_PATHS:
        target = folder / relative
        assert target.is_file(), relative
        assert target.read_bytes() == (root / 'static/devices/icons' / target.name).read_bytes(), relative
    files = [p for p in folder.rglob('*') if p.is_file()]
    unexpected = [str(p.relative_to(folder)) for p in files
                  if is_visual_data(p) and p.relative_to(folder).as_posix() not in allowed]
    assert not unexpected, unexpected
    with sqlite3.connect(folder / 'db.sqlite3') as db:
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in history}
        assert not any(counts.values()), counts
        for table, rows in expected.items():
            assert db.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() == rows, table
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    report[role] = dict(bytes=sum(p.stat().st_size for p in files), visual_history=counts,
                        template_assets=len(allowed - UI_ASSET_PATHS), ui_icons=len(UI_ASSET_PATHS), preserved_tables=tables)
(release / 'clean-release-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
