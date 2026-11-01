"""Persona runtime cleanup: scope, confirmation, backup and marker."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app_config.paths import AppPaths
from core.destructive_admin import (
    DestructiveAdminError,
    PersonaCleanupService,
    resolve_persona_targets,
)
from core.knowledge import KnowledgeStore
from core.persona_cleanup_state import legacy_usage_import_suppressed
from memory.admin_store import AdminStore


class FakeHost:
    def __init__(self, paths, *, active: str = "小堡", running: bool = True):
        self.paths = paths
        self.project_root = paths.PROJECT_ROOT
        self.config = SimpleNamespace(
            backup=SimpleNamespace(directory=str(paths.PROJECT_ROOT / "backups"))
        )
        self.rt = (
            SimpleNamespace(
                paths=paths,
                persona=SimpleNamespace(name=active),
                config=self.config,
            )
            if running
            else None
        )
        self.state = "running" if running else "stopped"
        self.last_error = ""
        self.paused = 0
        self.resumed = 0
        self._admin = False

    def build_paths(self):
        return self.paths

    def load_config(self):
        return SimpleNamespace(
            persona=SimpleNamespace(active="小堡"),
            backup=SimpleNamespace(directory=str(self.paths.PROJECT_ROOT / "backups")),
        )

    def admin_operation_active(self):
        return self._admin

    async def pause_for_admin(self, operation):
        self._admin = True
        self.paused += 1
        was_running = self.rt is not None
        self.rt = None
        self.state = "stopped"
        return was_running

    async def resume_after_admin(self):
        self.resumed += 1
        self._admin = False
        return True


def _paths(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    paths.ensure_data_dirs()
    return paths


def _seed_persona(paths, name="小堡"):
    persona_dir = paths.PERSONAS_DIR / name
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / "persona_prompt.py").write_text("PERSONA_PROMPT = 'x'\n", encoding="utf-8")
    memory = paths.memory_dir_for(name)
    vector = paths.vector_dir_for(name)
    memory.mkdir(parents=True)
    vector.mkdir(parents=True)
    (memory / f"{name}.db").write_bytes(b"persona-db")
    (memory / "history.jsonl").write_text("legacy", encoding="utf-8")
    (vector / "rag_memory.sqlite3").write_bytes(b"vector")
    return memory, vector


def _seed_knowledge(paths):
    store = KnowledgeStore(paths.DATA_DIR / "knowledge.json")
    store.add_manual(
        persona_id="小堡",
        kind="note",
        title="私有资料",
        content="secret",
        shared=False,
    )
    store.add_manual(
        persona_id="小堡",
        kind="note",
        title="共享资料",
        content="shared",
        shared=True,
    )
    store.add_manual(
        persona_id="deepseek",
        kind="note",
        title="别人的资料",
        content="other",
        shared=False,
    )


async def _wait_job(service, job_id, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        job = await service.get_job(job_id)
        if job and job.get("state") in {
            "completed",
            "partial",
            "failed",
            "cancelled",
            "interrupted",
        }:
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("cleanup job did not finish")


@pytest.mark.asyncio
async def test_active_persona_cleanup_keeps_definition_shared_data_and_resumes(tmp_path):
    paths = _paths(tmp_path)
    memory, vector = _seed_persona(paths)
    _seed_knowledge(paths)
    slang = paths.DATA_DIR / "slang.json"
    slang.write_text("[]", encoding="utf-8")
    workspace = paths.WORKSPACE_DIR / "keep.txt"
    workspace.write_text("keep", encoding="utf-8")
    host = FakeHost(paths, active="小堡", running=True)
    store = AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3")
    restarted = []
    service = PersonaCleanupService(host, store, on_restarted=lambda: restarted.append(True))
    await service.startup()

    preview = await service.preview("小堡")
    assert preview["active"] is True
    assert preview["runtime_mode"] == "pause_resume"
    assert preview["knowledge"]["private_entries"] == 1
    assert preview["knowledge"]["shared_entries"] == 1

    job, created = await service.execute(
        "小堡",
        preview_id=preview["preview_id"],
        confirmation_token=preview["confirmation_token"],
        expected_generation=preview["generation"],
        idempotency_key="cleanup-idem-1",
        typed_confirmation=preview["confirmation_phrase"],
        acknowledge_destructive=True,
        create_backup=False,
    )
    assert created is True
    result = await _wait_job(service, job["job_id"])
    assert result["state"] == "completed"
    assert not (memory / "history.jsonl").exists()
    assert not vector.exists()
    assert (paths.PERSONAS_DIR / "小堡" / "persona_prompt.py").is_file()
    assert (paths.memory_dir_for("小堡") / "小堡.db").is_file()
    assert slang.read_text(encoding="utf-8") == "[]"
    assert workspace.read_text(encoding="utf-8") == "keep"
    assert host.paused == 1
    assert host.resumed == 1
    assert restarted
    assert legacy_usage_import_suppressed(paths, "小堡") is True

    knowledge = KnowledgeStore(paths.DATA_DIR / "knowledge.json")
    remaining = {(item["persona_id"], item["title"], item["shared"]) for item in knowledge._entries}
    assert remaining == {
        ("小堡", "共享资料", True),
        ("deepseek", "别人的资料", False),
    }


@pytest.mark.asyncio
async def test_optional_backup_is_created_before_delete(tmp_path):
    paths = _paths(tmp_path)
    _seed_persona(paths)
    host = FakeHost(paths, active="小堡", running=True)
    service = PersonaCleanupService(
        host, AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3")
    )
    await service.startup()
    preview = await service.preview("小堡")
    job, _ = await service.execute(
        "小堡",
        preview_id=preview["preview_id"],
        confirmation_token=preview["confirmation_token"],
        expected_generation=preview["generation"],
        idempotency_key="cleanup-backup-1",
        typed_confirmation=preview["confirmation_phrase"],
        acknowledge_destructive=True,
        create_backup=True,
    )
    result = await _wait_job(service, job["job_id"])
    assert result["state"] == "completed"
    backup = result["result"]["backup"]
    from pathlib import Path

    assert Path(backup["path"]).is_file()
    assert backup["sha256"]
    profile = json.loads(
        __import__("zipfile").ZipFile(backup["path"]).read("manifest.json")
    )
    assert profile["persona"] == "小堡"


@pytest.mark.asyncio
async def test_wrong_phrase_does_not_create_job_or_delete(tmp_path):
    paths = _paths(tmp_path)
    memory, vector = _seed_persona(paths)
    host = FakeHost(paths)
    service = PersonaCleanupService(
        host, AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3")
    )
    await service.startup()
    preview = await service.preview("小堡")
    with pytest.raises(DestructiveAdminError, match="确认短语"):
        await service.execute(
            "小堡",
            preview_id=preview["preview_id"],
            confirmation_token=preview["confirmation_token"],
            expected_generation=preview["generation"],
            idempotency_key="cleanup-wrong-1",
            typed_confirmation="错误",
            acknowledge_destructive=True,
            create_backup=False,
        )
    assert memory.exists()
    assert vector.exists()


@pytest.mark.asyncio
async def test_backup_failure_keeps_data_and_resumes_runtime(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    memory, vector = _seed_persona(paths)
    host = FakeHost(paths)
    service = PersonaCleanupService(
        host, AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3")
    )
    await service.startup()
    preview = await service.preview("小堡")

    def boom(*args, **kwargs):
        raise OSError("backup disk full")

    monkeypatch.setattr("core.destructive_admin._create_persona_backup", boom)
    job, _ = await service.execute(
        "小堡",
        preview_id=preview["preview_id"],
        confirmation_token=preview["confirmation_token"],
        expected_generation=preview["generation"],
        idempotency_key="cleanup-backup-fail-1",
        typed_confirmation=preview["confirmation_phrase"],
        acknowledge_destructive=True,
        create_backup=True,
    )
    result = await _wait_job(service, job["job_id"])
    assert result["state"] == "failed"
    assert memory.exists()
    assert vector.exists()
    await asyncio.sleep(0.05)
    assert host.resumed == 1


def test_persona_targets_reject_traversal_and_symlink(tmp_path):
    paths = _paths(tmp_path)
    _seed_persona(paths)
    with pytest.raises(DestructiveAdminError, match="人格名"):
        resolve_persona_targets(paths, "../outside")
    memory = paths.memory_dir_for("小堡")
    import shutil

    shutil.rmtree(memory)
    memory.symlink_to(paths.WORKSPACE_DIR)
    with pytest.raises(DestructiveAdminError, match="符号链接"):
        resolve_persona_targets(paths, "小堡")
