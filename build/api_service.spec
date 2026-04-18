# -*- mode: python ; coding: utf-8 -*-
"""API服务打包配置"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 获取项目根目录（spec文件在 build/ 下，使用当前工作目录）
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))

a = Analysis(
    [os.path.join(project_root, 'api_service_enhanced', 'service_main.py')],
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
        'fastapi',
        'uvicorn',
        'pydantic',
        'playwright',
        'playwright.sync_api',
        'aiohttp',
        'aiohttp.client',
        'aiohttp.client_reqrep',
        'aiohttp.connector',
        'aiohttp.cookiejar',
        'aiohttp.helpers',
        'aiohttp.http',
        'aiohttp.http_websocket',
        'aiohttp.http_parser',
        'aiohttp.locks',
        'aiohttp.streams',
        'aiohttp.tracing',
        'aiohttp.web',
        'aiohttp.web_app',
        'aiohttp.web_exceptions',
        'aiohttp.web_fileresponse',
        'aiohttp.web_log',
        'aiohttp.web_middlewares',
        'aiohttp.web_protocol',
        'aiohttp.web_request',
        'aiohttp.web_response',
        'aiohttp.web_routedef',
        'aiohttp.web_runner',
        'aiohttp.web_server',
        'aiohttp.web_urldispatcher',
        'aiohttp.web_ws',
        'aiofiles',
        'aiofiles.os',
        'aiofiles.threadpool',
        'requests',
        'psutil',
        'shared.models',
        'shared.progress_state',
        'shared.config_schema',
        'downloader',
        'api_service_enhanced',
        'api_service_enhanced.routes',
        'api_service_enhanced.routes.scrape',
        'api_service_enhanced.routes.status',
        'api_service_enhanced.routes.config',
        'api_service_enhanced.routes.stop',
        'api_service_enhanced.task_manager',
        'api_service_enhanced.chrome_manager',
        'api_service_enhanced.progress_tracker',
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
    name='api_service',
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
