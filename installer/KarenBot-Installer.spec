# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：Tkinter 安装器单文件。

Windows 使用 windowed 子系统（无黑框）；Linux 保留 console，方便
`--check` / `--smoke-test` 和终端启动时看到错误。
"""

import sys
from pathlib import Path

INSTALLER_DIR = Path(SPECPATH).resolve()

a = Analysis(
    [str(INSTALLER_DIR / "gui_install.py")],
    pathex=[str(INSTALLER_DIR)],
    binaries=[],
    datas=[(str(INSTALLER_DIR / "mirrors.json"), ".")],
    hiddenimports=["karen_install"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KarenBot-Installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=not sys.platform.startswith("win"),
)
