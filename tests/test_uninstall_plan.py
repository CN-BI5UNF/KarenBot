"""Uninstall target enumeration and safety gates."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app_config.paths import AppPaths
from core.destructive_admin import build_uninstall_plan, detect_launch_mode


class FakeHost:
    def __init__(self, paths, *, running=True):
        self.project_root = paths.PROJECT_ROOT
        self.paths = paths
        self.state = "running" if running else "stopped"
        self.config = SimpleNamespace(
            backup=SimpleNamespace(directory=str(paths.PROJECT_ROOT.parent / "backups"))
        )
        self.rt = (
            SimpleNamespace(
                paths=paths,
                config=self.config,
                secrets=object(),
                project_root=paths.PROJECT_ROOT,
                persona=SimpleNamespace(name="小堡"),
            )
            if running else None
        )

    def build_paths(self):
        return self.paths

    def load_config(self):
        return self.config


def _paths(tmp_path):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    data.mkdir()
    paths = AppPaths(project_root=project, data_root=data)
    paths.ensure_data_dirs()
    (paths.PERSONAS_DIR / "小堡").mkdir(parents=True)
    (paths.PERSONAS_DIR / "小堡" / "persona_prompt.py").write_text("x", encoding="utf-8")
    (paths.MEMORY_DIR / "小堡").mkdir(parents=True)
    (paths.MEMORY_DIR / "小堡" / "小堡.db").write_bytes(b"data")
    (data / "config.yaml").write_text("version: 2\n", encoding="utf-8")
    (data / "secrets.enc").write_bytes(b"secret")
    return paths, project, data


def test_uninstall_plan_enumerates_project_and_data_without_dev_backups(tmp_path):
    paths, project, data = _paths(tmp_path)
    host = FakeHost(paths)
    plan = build_uninstall_plan(
        host, plan_id="preview-1", test_mode=True, test_root=tmp_path
    )
    assert plan["supported"] is True
    paths_in_plan = {item["path"] for item in plan["targets"]}
    assert str(project.resolve()) in paths_in_plan
    assert str(data.resolve()) in paths_in_plan
    assert not any("/Debata_BeiFen" in item["path"] for item in plan["targets"])
    retained = {item.get("path") for item in plan["retained"]}
    assert str(Path.home() / "Debata_BeiFen") in retained
    assert str(Path.home() / "debata-backups") in retained
    assert plan["optional_backup"]["available"] is True
    assert len(plan["generation"]) == 64
    assert plan["audit_path"].startswith(str(tmp_path))
    assert plan["backup_dir"].startswith(str(tmp_path))


def test_uninstall_plan_is_deterministic_and_contains_metrics(tmp_path):
    paths, _project, _data = _paths(tmp_path)
    host = FakeHost(paths)
    first = build_uninstall_plan(
        host, plan_id="preview-1", test_mode=True, test_root=tmp_path
    )
    second = build_uninstall_plan(
        host, plan_id="preview-1", test_mode=True, test_root=tmp_path
    )
    assert first["generation"] == second["generation"]
    assert first["expected_bytes"] >= 5
    assert first["expected_files"] >= 1
    assert all("dev" in item and "ino" in item for item in first["targets"])


def test_launch_mode_test_mode_is_supported():
    assert detect_launch_mode(test_mode=True)["supported"] is True
