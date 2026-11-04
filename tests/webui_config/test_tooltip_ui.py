"""WebUI tooltip contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_tooltip_layer_is_wired_and_accessible():
    tooltip = _read("webui/static/js/tooltip.js")
    app = _read("webui/static/js/app.js")
    css = _read("webui/static/app.css")
    index = _read("webui/static/index.html")

    assert "data-tooltip" in tooltip
    assert "MutationObserver" in tooltip
    assert "aria-label" in tooltip
    assert "pointerover" in tooltip
    assert "focusin" in tooltip
    assert "Escape" in tooltip
    assert "app-tooltip" in tooltip

    assert "import { initTooltips } from './tooltip.js';" in app
    assert "initTooltips();" in app

    assert ".app-tooltip" in css
    assert "position: fixed" in css
    assert "z-index: 120" in css
    assert "var(--bg-card)" in css
    assert "pointer-events: none" in css

    assert "app.css?v=" in index
    assert "app.js?v=" in index


def test_nav_and_file_manager_hints_are_descriptive():
    app = _read("webui/static/js/app.js")
    files = _read("webui/static/js/container_files.js")

    assert "hint:" in app
    assert "运行状态、用量与快捷操作" in app
    assert "Docker、两个工作区与只读文件管理" in app
    assert "${item.title} · ${item.hint}" in app

    assert "刷新当前目录（绕过 15 秒缓存）" in files
    assert "回到本机工作区根目录" in files
    assert "回到容器 /workspace 根目录" in files
    assert "title: `打开 ${target}`" in files
