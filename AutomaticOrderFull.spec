# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

# Rebuild collected assets on every build; never ship stale PLC button scripts.
from pathlib import Path
import subprocess
import sys
import os
# PyInstaller hooks import Django models; build-time discovery must not launch hardware.
os.environ["RVC_CAMERA_AUTO_START"] = "false"
subprocess.run([sys.executable, str(Path(SPECPATH) / 'manage.py'), 'collectstatic', '--noinput'],
               cwd=SPECPATH, check=True)

datas = [('templates', 'templates'), ('static', 'static'), ('staticfiles', 'staticfiles'), ('2d_SDK', '2d_SDK'), ('3d_SDK', '3d_SDK'), ('media', 'media'), ('db.sqlite3', '.'), ('Env.json', '.'), ('rvc_service/rvc.json', 'rvc_service')]
binaries = []
hiddenimports = ['waitress', 'PyRVC', 'chg_hik']
hiddenimports += collect_submodules('AutomaticOrder')
hiddenimports += collect_submodules('apps')
hiddenimports += collect_submodules('rvc_service')
hiddenimports += collect_submodules('whitenoise')
tmp_ret = collect_all('django')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('zeep')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('snap7')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('open3d')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run.py'],
    pathex=[],
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
    name='AutomaticOrderFull',
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
    name='AutomaticOrderFull',
)
