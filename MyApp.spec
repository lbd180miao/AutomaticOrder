# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from importlib.metadata import distribution
from pathlib import Path

datas = [('templates', 'templates'), ('static', 'static'), ('staticfiles', 'staticfiles'), ('db.sqlite3', '.'), ('2d_SDK', '2d_SDK'), ('Env.json', '.')]
binaries = []
hiddenimports = ['waitress', 'chg_hik', 'LW_DM_Api', 'LW_DM_Type']
hiddenimports += collect_submodules('AutomaticOrder')
hiddenimports += collect_submodules('apps')
hiddenimports += collect_submodules('rvc_service')
hiddenimports += collect_submodules('whitenoise')
tmp_ret = collect_all('django')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('open3d')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PyRVC')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# PyRVC is a single .pyd with sibling DLLs/GenTL producers, not a package.
# Static dependency analysis misses plugins loaded by the SDK at runtime.
rvc_dist = distribution('PyRVC')
for entry in rvc_dist.files or []:
    if entry.suffix.lower() in {'.dll', '.cti', '.ini', '.xml', '.manifest'}:
        source = Path(rvc_dist.locate_file(entry))
        if not source.is_file():
            raise RuntimeError(f'Missing PyRVC runtime file: {source}')
        datas.append((str(source), str(entry.parent)))
datas.append(('3d_SDK/rvc.json', '3d_SDK'))


a = Analysis(
    ['run.py'],
    pathex=['apps/dm_camera/sdk'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MyApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MyApp',
)
