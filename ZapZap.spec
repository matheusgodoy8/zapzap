# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('zapzap.features.settings.pages')


a = Analysis(
    ['zapzap/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('zapzap/po', 'zapzap/po'), ('zapzap/assets', 'zapzap/assets'), ('zapzap/features/browser/web/scripts', 'zapzap/features/browser/web/scripts')],
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
    name='ZapZap',
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
    icon=['share/icons/com.rtosta.zapzap.ico'],
)
