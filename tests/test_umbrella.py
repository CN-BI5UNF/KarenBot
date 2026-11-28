"""Umbrella layout and assembly tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.assemble import assemble, check
from scripts.verify_modules import COMPONENT_ORDER, load_lock, verify


def test_lock_matches_submodules():
    lock = load_lock()
    assert lock["schema"] == 1
    assert lock["release"] == "v2.1.3-alpha"
    for component in COMPONENT_ORDER:
        entry = lock["components"][component]
        assert entry["tag"] == "v2.1.3-alpha"
        assert len(entry["commit"]) == 40
    verify("v2.1.3-alpha")


def test_assemble_check():
    lock = check()
    assert lock["release"] == "v2.1.3-alpha"


def test_assemble_gui_tree(tmp_path: Path):
    output = tmp_path / "app"
    assemble("gui", output)
    assert (output / "main.py").is_file()
    assert (output / "backend" / "__init__.py").is_file()
    assert (output / "gui" / "__init__.py").is_file()
    assert (output / "personas" / "__init__.py").is_file()
    assert not (output / "webui").exists()
    manifest = json.loads((output / "modules.json").read_text(encoding="utf-8"))
    assert manifest["frontend"] == "gui"
    assert manifest["distribution"]["tag"] == "v2.1.3-alpha"
    assert manifest["components"]["backend"]["version"] == "2.1.3-alpha"
    assert manifest["components"]["gui"]["version"] == "2.1.3-alpha"
    assert "webui" not in manifest["components"]


def test_assemble_webui_tree(tmp_path: Path):
    output = tmp_path / "app"
    assemble("webui", output)
    assert (output / "webui" / "__init__.py").is_file()
    assert not (output / "gui").exists()
    manifest = json.loads((output / "modules.json").read_text(encoding="utf-8"))
    assert manifest["frontend"] == "webui"
    assert "gui" not in manifest["components"]
