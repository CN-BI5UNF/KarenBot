"""Uninstall preview/execute orchestration without touching the live tree."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app_config.paths import AppPaths
from core.destructive_admin import (
    DestructiveAdminError,
    UninstallService,
    _create_uninstall_backup,
    _source_archive,
)
from memory.admin_store import AdminStore


class FakeHost:
    def __init__(self, paths):
        self.paths = paths
        self.project_root = paths.PROJECT_ROOT
        self.state = "running"
        self.last_error = ""
        self.config = SimpleNamespace(
            backup=SimpleNamespace(directory=str(paths.PROJECT_ROOT.parent / "backups"))
        )
        self.rt = SimpleNamespace(
            paths=paths,
            config=self.config,
            secrets=object(),
            project_root=paths.PROJECT_ROOT,
            persona=SimpleNamespace(name="小堡"),
        )
        self._admin = False

    def build_paths(self):
        return self.paths

    def load_config(self):
        return self.config

    def admin_operation_active(self):
        return self._admin

    def begin_admin_operation(self, operation):
        if self._admin:
            raise RuntimeError("already running")
        self._admin = True

    def end_admin_operation(self):
        self._admin = False


def _paths(tmp_path):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    data.mkdir()
    paths = AppPaths(project_root=project, data_root=data)
    paths.ensure_data_dirs()
    (paths.PERSONAS_DIR / "小堡").mkdir(parents=True)
    (paths.PERSONAS_DIR / "小堡" / "persona_prompt.py").write_text("x", encoding="utf-8")
    (data / "config.yaml").write_text("version: 2\n", encoding="utf-8")
    return paths


async def _wait(service, job_id, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        job = await service.get_job(job_id)
        if job and job.get("state") in {
            "scheduled", "failed", "cancelled", "completed",
        }:
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("uninstall job did not reach a terminal/scheduled state")


@pytest.mark.asyncio
async def test_uninstall_preview_and_schedule_without_running_helper(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    host = FakeHost(paths)
    exits = []
    service = UninstallService(
        host,
        AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3"),
        exit_callback=lambda: exits.append(True),
        test_mode=True,
        test_root=tmp_path,
    )
    preview = await service.preview()
    assert preview["supported"] is True
    assert preview["confirmation_phrase"] == "永久卸载 KarenBot"
    assert preview["optional_backup"]["available"] is True

    calls = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            self.pid = 4242
            calls.append((command, kwargs))

    monkeypatch.setattr("core.destructive_admin.subprocess.Popen", FakePopen)
    job, created = await service.execute(
        preview_id=preview["preview_id"],
        confirmation_token=preview["confirmation_token"],
        expected_generation=preview["generation"],
        idempotency_key="uninstall-idem-1",
        typed_confirmation="永久卸载 KarenBot",
        acknowledge_destructive=True,
        create_backup=False,
    )
    assert created is True
    state = await _wait(service, job["job_id"])
    assert state["state"] == "scheduled"
    assert calls and calls[0][0][0] == __import__("sys").executable
    assert calls[0][1]["start_new_session"] is True
    await asyncio.sleep(1.1)
    assert exits == [True]


@pytest.mark.asyncio
async def test_official_backup_collects_user_and_source_archives(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    host = FakeHost(paths)
    backup_dir = tmp_path / "backup" / "plan"
    plan = {
        "backup_dir": str(backup_dir),
        "targets": [
            {"kind": "project_root", "path": str(paths.PROJECT_ROOT)},
            {"kind": "data_root", "path": str(paths.ROOT_DATA_DIR)},
        ],
    }
    created = backup_dir / "Karen_Backup_test.zip"

    class FakeManager:
        def __init__(self, *args, **kwargs):
            backup_dir.mkdir(parents=True, exist_ok=True)
            created.write_bytes(b"user-backup")

        async def start(self, **_kwargs):
            return {"id": "backup-1", "state": "queued"}

        def get_job(self, _job_id):
            import hashlib
            return {
                "state": "done",
                "partial": False,
                "validation_status": "verified",
                "filename": created.name,
                "sha256": hashlib.sha256(created.read_bytes()).hexdigest(),
                "processed_bytes": created.stat().st_size,
                "total_bytes": created.stat().st_size,
            }

    monkeypatch.setattr("core.backup.BackupService", FakeManager)
    monkeypatch.setattr("core.backup.BackupCoordinator", lambda *args, **kwargs: object())
    updates = []

    async def update(**kwargs):
        updates.append(kwargs)

    info = await _create_uninstall_backup(host, plan=plan, update=update)
    assert info["user_backup"]["path"].endswith("Karen_Backup_test.zip")
    assert info["source_archive"]["sha256"]
    assert (backup_dir / "source.zip").is_file()


def test_source_archive_includes_working_tree_but_not_venv(tmp_path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "main.py").write_text("print('x')", encoding="utf-8")
    (project / "untracked.txt").write_text("keep", encoding="utf-8")
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").write_text("bad", encoding="utf-8")
    target = tmp_path / "backup" / "source.zip"
    info = _source_archive(project, target)
    assert info["sha256"] and target.is_file()
    import zipfile
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
    assert "source/pkg/main.py" in names
    assert "source/untracked.txt" in names
    assert not any(".venv" in name for name in names)


@pytest.mark.asyncio
async def test_uninstall_wrong_phrase_does_not_create_job(tmp_path):
    paths = _paths(tmp_path)
    service = UninstallService(
        FakeHost(paths),
        AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3"),
        exit_callback=lambda: None,
        test_mode=True,
        test_root=tmp_path,
    )
    preview = await service.preview()
    with pytest.raises(DestructiveAdminError, match="确认短语"):
        await service.execute(
            preview_id=preview["preview_id"],
            confirmation_token=preview["confirmation_token"],
            expected_generation=preview["generation"],
            idempotency_key="uninstall-wrong-1",
            typed_confirmation="no",
            acknowledge_destructive=True,
            create_backup=False,
        )
    assert await service.list_jobs() == []


@pytest.mark.asyncio
async def test_uninstall_backup_failure_aborts_before_helper(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    host = FakeHost(paths)
    service = UninstallService(
        host,
        AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3"),
        exit_callback=lambda: None,
        test_mode=True,
        test_root=tmp_path,
    )
    preview = await service.preview()
    calls = []
    monkeypatch.setattr(
        "core.destructive_admin.subprocess.Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    async def boom(*args, **kwargs):
        raise DestructiveAdminError("backup_not_verified", "disk full")

    monkeypatch.setattr("core.destructive_admin._create_uninstall_backup", boom)
    job, _ = await service.execute(
        preview_id=preview["preview_id"],
        confirmation_token=preview["confirmation_token"],
        expected_generation=preview["generation"],
        idempotency_key="uninstall-backup-fail-1",
        typed_confirmation="永久卸载 KarenBot",
        acknowledge_destructive=True,
        create_backup=True,
    )
    state = await _wait(service, job["job_id"])
    assert state["state"] == "failed"
    assert calls == []
    await asyncio.sleep(0.05)
    assert host.admin_operation_active() is False
    assert host.rt is not None
