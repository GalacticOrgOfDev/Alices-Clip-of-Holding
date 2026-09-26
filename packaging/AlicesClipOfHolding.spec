# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Alice's Clip of Holding (Windows onefile)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

pystray_data = collect_all("pystray")
hidden = [
    "win32timezone",
    "win32clipboard",
    "win32api",
    "win32gui",
    "win32con",
    "win32process",
    "win32event",
    "pythoncom",
    "pywintypes",
    "win32com",
    "win32com.client",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageGrab",
    "pystray",
    "alices_clip",
    "alices_clip.__main__",
]
hidden += collect_submodules("win32com")
hidden += collect_submodules("pystray")

a = Analysis(
    ["run_alice.py"],
    pathex=["..", "../src"],
    binaries=pystray_data[1],
    datas=pystray_data[0],
    hiddenimports=hidden,
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
    name="AlicesClipOfHolding",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
