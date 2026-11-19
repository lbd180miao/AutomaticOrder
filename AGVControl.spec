# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from importlib.metadata import distribution
from pathlib import Path
bundle_visual_data = False

datas = [('templates', 'templates'), ('static', 'static'), ('staticfiles', 'staticfiles'), ('build/distributed_seed/db.sqlite3', '.'), ('Env.json', '.')]
# Never bundle SDK capture samples or point clouds. Only camera parameter files.
datas += [('apps/vision/algorithms/rivet_vendor/assets/head_patterns.npz', 'apps/vision/algorithms/rivet_vendor/assets')]
datas += [(str(p), '2d_SDK') for p in Path('2d_SDK').glob('*.mfs')]
datas += [(str(Path('mes_gateway_project') / name), 'mes_gateway_project')
          for name in ('web.html', 'app.css')]
binaries = []
hiddenimports = ['waitress', 'chg_hik', 'LW_DM_Api', 'LW_DM_Type']
hiddenimports += collect_submodules('AutomaticOrder')
hiddenimports += collect_submodules('apps')
hiddenimports += collect_submodules('rvc_service')
hiddenimports += collect_submodules('mes_gateway_project')
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
if not bundle_visual_data:
    import sys
    sys.path.insert(0, str(Path('tools').resolve()))
    from packaging_resources import is_visual_data, is_ui_asset
    a.datas = [entry for entry in a.datas if not is_visual_data(entry[0]) or is_ui_asset(entry[0])]
    a.binaries = [entry for entry in a.binaries if not is_visual_data(entry[0]) or is_ui_asset(entry[0])]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AGVControl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='AGVControl',
)
