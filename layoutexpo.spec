# -*- mode: python ; coding: utf-8 -*-
"""Especificación PyInstaller multiplataforma para LayoutExpo.

Objetivos:
  - macOS Apple Silicon (arm64) e Intel (x86_64) -> dist/LayoutExpo.app
  - Windows 11 x64 -> dist/LayoutExpo/LayoutExpo.exe
"""

from pathlib import Path
import sys
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

SPEC_ROOT = Path(SPECPATH).resolve()
if str(SPEC_ROOT) not in sys.path:
    sys.path.insert(0, str(SPEC_ROOT))

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

added_datas = [
    (str(SPEC_ROOT / "ui"), "ui"),
]
added_datas += collect_data_files("webview")
added_datas += collect_data_files("reportlab")

added_binaries = []
added_binaries += collect_dynamic_libs("webview")

hidden_imports = [
    "core",
    "core.units",
    "core.project",
    "core.geometry",
    "core.homography",
    "core.media",
    "core.pdf_export",
    "core.presets",
    "core.curation",
    "server",
    "server.app",
    "server.events",
    "desktop",
    "desktop.displays",
    "desktop.launcher",
    "flask",
    "werkzeug",
    "PIL",
    "PIL.ImageCms",
    "PIL.ImageOps",
    "reportlab.graphics",
    "reportlab.lib.pagesizes",
    "reportlab.pdfgen.canvas",
]
hidden_imports += collect_submodules("webview")

a = Analysis(
    [str(SPEC_ROOT / "main.py")],
    pathex=[str(SPEC_ROOT)],
    binaries=added_binaries,
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "playwright", "axe_playwright_python"],
    noarchive=False,
)

pyz = PYZ(a.pure)

app_icon_path = str(
    SPEC_ROOT / "assets" / ("LayoutExpo.icns" if IS_MACOS else "LayoutExpo.ico")
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LayoutExpo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=app_icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LayoutExpo",
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="LayoutExpo.app",
        icon=str(SPEC_ROOT / "assets" / "LayoutExpo.icns"),
        bundle_identifier="app.layoutexpo.studio",
        info_plist={
            "CFBundleName": "LayoutExpo",
            "CFBundleDisplayName": "LayoutExpo",
            "CFBundleShortVersionString": "0.2.4",
            "CFBundleVersion": "0.2.4",
            "CFBundleIconFile": "LayoutExpo.icns",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
