# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\30982\\gacha-analyzer\\config.yaml', '.'), ('C:\\Users\\30982\\gacha-analyzer\\ui\\resources', 'ui/resources'), ('C:\\Users\\30982\\gacha-analyzer\\data\\game_data', 'data/game_data'), ('C:\\Users\\30982\\gacha-analyzer\\fetchers\\hypergryph\\arknights_proxy.py', 'fetchers/hypergryph')]
binaries = []
hiddenimports = ['PySide6', 'matplotlib', 'sqlite3', 'yaml', 'openpyxl', 'requests']
tmp_ret = collect_all('matplotlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\30982\\gacha-analyzer\\main.py'],
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
    a.binaries,
    a.datas,
    [],
    name='穷观阵',
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
    icon=['C:\\Users\\30982\\gacha-analyzer\\icon.ico'],
)
