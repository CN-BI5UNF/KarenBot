"""安装器 GUI 的技术约束与构建入口契约。

安装器刻意使用 Tkinter：不引入 WebView/Tauri/Electron，也不依赖被安装的
GTK4 运行时。这里用静态契约锁住这个决定，并确保 GitHub Actions 构建入口
不会在后续改动中丢失。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer"


def test_gui_uses_tkinter_not_webview():
    source = (INSTALLER / "gui_install.py").read_text(encoding="utf-8")
    lowered = source.casefold()
    assert "import tkinter as tk" in source
    assert "from tkinter import" in source
    assert "webview" not in lowered
    assert "webview2" not in lowered
    assert "tauri" not in lowered
    assert "electron" not in lowered
    # 安装器不得依赖 GTK4；它安装的应用才依赖 GTK4。
    assert "import gi" not in source


def test_gui_wires_core_sinks_and_cancel():
    source = (INSTALLER / "gui_install.py").read_text(encoding="utf-8")
    assert "set_log_sink" in source
    assert "set_progress_sink" in source
    assert "InstallCancelled" in source
    assert "cancel_event" in source
    assert "--smoke-test" in source
    assert "--check" in source


def test_gui_has_windows_compatibility_hooks():
    source = (INSTALLER / "gui_install.py").read_text(encoding="utf-8")
    assert "SetProcessDpiAwareness" in source
    assert "Microsoft YaHei UI" in source
    assert "os.startfile" in source or "startfile" in source
    assert "self_delete_installer" in source


def test_pyinstaller_spec_bundles_mirrors():
    spec = (INSTALLER / "KarenBot-Installer.spec").read_text(encoding="utf-8")
    assert "mirrors.json" in spec
    assert 'hiddenimports=["karen_install"]' in spec
    assert 'console=not sys.platform.startswith("win")' in spec


def test_github_actions_builds_installer_on_free_runners():
    workflow = (ROOT / ".github/workflows/build-installer.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch" in workflow
    assert "windows-latest" in workflow
    assert "ubuntu-24.04" in workflow
    assert "PyInstaller" in workflow
    assert "installer-v*" in workflow
    assert "installer-windows-x64" in workflow
    assert "installer-linux-x64" in workflow
    # macOS runner 对公开仓库也按 10 倍分钟计费；当前不需要。
    assert "macos" not in workflow.casefold()


def test_architecture_document_records_tkinter_decision():
    document = (INSTALLER / "gui-architecture.md").read_text(encoding="utf-8")
    assert "Tkinter" in document
    assert "WebView2" in document
    assert "不采用" in document or "不推荐" in document or "放弃" in document
