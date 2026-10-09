# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('templates', 'templates'), ('static', 'static'), ('apps/devices', 'apps/devices'), ('apps/core', 'apps/core')]
hiddenimports = ['waitress', 'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'django.db.backends.sqlite3', 'msvcrt', 'snap7.client', 'snap7.common', 'snap7.util', 'apps.devices.plc_db100', 'apps.devices.adapters.plc', 'apps.devices.adapters.simulated', 'apps.devices.adapters.base', 'apps.devices.services', 'apps.devices.models', 'apps.core.barcode_validator', 'apps.core.constants', 'zeep', 'requests']
datas += collect_data_files('snap7')
hiddenimports += collect_submodules('whitenoise')
hiddenimports += collect_submodules('django.contrib')
hiddenimports += collect_submodules('snap7')
hiddenimports += collect_submodules('apps.devices')
hiddenimports += collect_submodules('apps.core')


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'cv2', 'opencv', 'open3d', 'PIL', 'Pillow', 'plyfile', 'matplotlib', 'apps.vision', 'apps.dm_camera', 'apps.rvc_camera'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutomaticOrderPLC',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutomaticOrderPLC',
)
