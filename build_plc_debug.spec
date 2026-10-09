# -*- mode: python ; coding: utf-8 -*-
"""
PLC调试模块打包配置
用于打包包含完整PLC调试功能的可执行程序
"""

block_cipher = None

# 需要收集的所有包
hiddenimports = [
    'waitress',
    'whitenoise',
    'whitenoise.middleware',
    'django',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.core.management',
    'django.db.backends.sqlite3',
    'msvcrt',
    # PLC相关
    'snap7',
    'snap7.client',
    'snap7.common',
    'snap7.util',
    # apps模块
    'apps',
    'apps.devices',
    'apps.devices.plc_db100',
    'apps.devices.plc_position_debug',
    'apps.devices.plc_foam_debug',
    'apps.devices.adapters.plc',
    'apps.devices.adapters.simulated',
    'apps.devices.adapters.base',
    'apps.devices.services',
    'apps.devices.models',
    'apps.core',
    'apps.core.barcode_validator',
    'apps.core.constants',
    'apps.vision',
    'apps.vision.models',
    'apps.vision.services',
    'apps.vision.rack_location',
    'apps.vision.rack_3d.services',
    'apps.vision.algorithms.foam_inspector',
    'apps.vision.recipe_utils',
    'apps.production',
    'apps.production.models',
    'apps.production.services',
    'apps.mes',
    'apps.workflow',
    'apps.coordinates',
    'apps.alarms',
    # 科学计算库
    'numpy',
    'scipy',
    'cv2',
    'PIL',
    'open3d',
    'plyfile',
    'zeep',
    'requests',
]

# 需要打包的数据文件
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('staticfiles', 'staticfiles'),
    ('apps', 'apps'),  # 包含所有Python文件以支持动态导入
]

# 可选的SDK和配置文件（如果存在）
import os
if os.path.exists('2d_SDK'):
    datas.append(('2d_SDK', '2d_SDK'))
if os.path.exists('3d_SDK'):
    datas.append(('3d_SDK', '3d_SDK'))
if os.path.exists('media'):
    datas.append(('media', 'media'))

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutomaticOrderPLC',
)
