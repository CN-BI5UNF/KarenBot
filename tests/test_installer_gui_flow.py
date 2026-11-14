"""Tkinter 安装器的线程/队列/界面状态烟测。

默认测试矩阵没有 DISPLAY，会自动跳过；构建 workflow 用 xvfb-run 执行。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from installer import gui_install, karen_install  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.name != "nt" and not os.environ.get("DISPLAY"),
    reason="GUI flow test needs a display (use xvfb-run)",
)


def _pump(root, predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _make_app(tmp_path: Path, monkeypatch):
    messages: list[tuple[str, tuple]] = []
    monkeypatch.setattr(
        gui_install.messagebox,
        "showinfo",
        lambda *args, **kwargs: messages.append(("info", args)),
    )
    monkeypatch.setattr(
        gui_install.messagebox,
        "showerror",
        lambda *args, **kwargs: messages.append(("error", args)),
    )
    monkeypatch.setattr(
        gui_install.messagebox,
        "showwarning",
        lambda *args, **kwargs: messages.append(("warning", args)),
    )
    monkeypatch.setattr(
        gui_install.messagebox,
        "askyesno",
        lambda *args, **kwargs: True,
    )
    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "gui").mkdir()
    root = tk.Tk()
    root.withdraw()
    app = gui_install.InstallerApp(root)
    app.source_path.set(str(source))
    app.install_dir.set(str(tmp_path / "install"))
    app.download_fonts.set(False)
    app.create_shortcut.set(False)
    if os.name == "nt":
        # Windows 源码安装只允许 WebUI；GUI 需要预构建 GTK4 包。
        app.frontend.set("webui")
    return root, app, messages


def test_gui_reports_success(monkeypatch, tmp_path):
    root, app, messages = _make_app(tmp_path, monkeypatch)

    def fake_install(**kwargs):
        karen_install.log("fake install")
        return kwargs["install_dir"]

    monkeypatch.setattr(karen_install, "install", fake_install)
    app._start_install()
    try:
        assert _pump(root, lambda: app.status.get() == "安装完成")
        assert app._installed_dir == tmp_path / "install"
        assert messages and messages[-1][0] == "info"
    finally:
        root.destroy()


def test_gui_reports_failure(monkeypatch, tmp_path):
    root, app, messages = _make_app(tmp_path, monkeypatch)

    def fake_install(**_kwargs):
        raise karen_install.InstallFailure("boom")

    monkeypatch.setattr(karen_install, "install", fake_install)
    app._start_install()
    try:
        assert _pump(root, lambda: app.status.get() == "安装失败")
        assert messages and messages[-1][0] == "error"
    finally:
        root.destroy()


def test_mirror_dialog_renders_results(monkeypatch, tmp_path):
    root, app, _messages = _make_app(tmp_path, monkeypatch)
    try:
        app._open_mirror_dialog()
        app._show_mirrors(
            [
                {
                    "mirror": "fast",
                    "ok": True,
                    "speed": 2048.0,
                    "latency": 0.1,
                },
                {
                    "mirror": "bad",
                    "ok": False,
                    "error": "timeout",
                    "speed": 0.0,
                    "latency": 999.0,
                },
            ]
        )
        rows = app._mirror_tree.get_children()
        assert len(rows) == 2
        assert app._mirror_tree.item(rows[0], "values")[0] == "fast"
        app._close_mirror_dialog()
        app._open_mirror_dialog()
        assert app._mirror_tree is not None
    finally:
        root.destroy()
