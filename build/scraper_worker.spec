# -*- mode: python ; coding: utf-8 -*-
"""爬虫工作进程打包配置"""

import os
import sys

block_cipher = None

# 获取项目根目录（spec文件在 build/ 下，使用当前工作目录）
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, 'scraper.py'), '.'),
        (os.path.join(project_root, 'chrome_launcher.py'), '.'),
        (os.path.join(project_root, 'downloader.py'), '.'),
        (os.path.join(project_root, 'output.py'), '.'),
        (os.path.join(project_root, 'shared'), 'shared'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'aiohttp',
        'aiofiles',
        'requests',
        'shared.models',
        'shared.progress_state',
        'shared.config_schema',
    ],
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
    name='scraper_worker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
