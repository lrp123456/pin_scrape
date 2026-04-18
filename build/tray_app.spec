# -*- mode: python ; coding: utf-8 -*-
"""托盘应用打包配置"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 获取项目根目录（spec文件在 build/ 下，使用当前工作目录）
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))

a = Analysis(
    [os.path.join(project_root, 'tray_app', 'tray_main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, 'tray_app', 'assets'), 'tray_app/assets'),
        (os.path.join(project_root, 'shared'), 'shared'),
    ] + collect_data_files('pystray'),
    hiddenimports=[
        'pystray',
        'pystray._icon',
        'pystray._util.win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'psutil',
        'requests',
        'shared.models',
        'shared.progress_state',
        'shared.config_schema',
        'tray_app',
        'tray_app.tray_icon',
        'tray_app.process_manager',
        'tray_app.config_manager',
        'tray_app.console_gui',
        'tray_app.first_run_setup',
        'tray_app.config_gui',
    ] + collect_submodules('pystray'),
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='tray_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
