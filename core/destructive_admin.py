"""Destructive admin operations: persona runtime cleanup and local uninstall.

The WebUI never supplies arbitrary filesystem paths. Persona targets come from
``AppPaths`` after name validation; uninstall targets are enumerated from known
application paths and revalidated by the external helper.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from core.knowledge import KnowledgeStore
from core.persona_cleanup_state import write_cleanup_marker
from memory.admin_store import AdminConflict, AdminStore, token_fingerprint
from memory.karen_db import KarenDB

logger = logging.getLogger(__name__)

PERSONA_CLEANUP = "persona_cleanup"
UNINSTALL = "uninstall"
PERSONA_PREVIEW_TTL_SECONDS = 300
UNINSTALL_PREVIEW_TTL_SECONDS = 600
PERSONA_BACKUP_PREFIX = "Karen_Persona_Backup_"
UNINSTALL_PHRASE = "永久卸载 KarenBot"
UNINSTALL_BACKUP_PREFIX = "Karen_Uninstall_Backups"
BACKUP_GLOBS = ("Karen_Backup_*.zip", "Karen_Backup_*.zip.json")


class DestructiveAdminError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(slots=True)
class TreeStats:
    path: Path
    exists: bool
    is_symlink: bool
    bytes: int = 0
    files: int = 0
    dirs: int = 0
    symlinks: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "is_symlink": self.is_symlink,
            "bytes": self.bytes,
            "files": self.files,
            "dirs": self.dirs,
            "symlinks": self.symlinks,
            "errors": list(self.errors or []),
        }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persona_phrase(persona: str) -> str:
    return f"删除 {persona} 的运行数据"


def scan_tree(path: Path) -> TreeStats:
    """Walk a tree without following symlinks; errors are reported, not raised."""
    target = Path(path)
    stats = TreeStats(path=target, exists=False, is_symlink=False, errors=[])
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return stats
    except OSError as exc:
        stats.errors.append(f"{type(exc).__name__}: {exc}")
        return stats
    stats.exists = True
    stats.is_symlink = os.path.islink(target)
    if stats.is_symlink:
        return stats
    if not os.path.isdir(target):
        stats.files = 1
        stats.bytes = int(getattr(info, "st_size", 0) or 0)
        return stats

    stack = [target]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            stats.symlinks += 1
                        elif entry.is_dir(follow_symlinks=False):
                            stats.dirs += 1
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stats.files += 1
                            stats.bytes += int(
                                entry.stat(follow_symlinks=False).st_size or 0
                            )
                    except OSError as exc:
                        stats.errors.append(f"{entry.path}: {type(exc).__name__}: {exc}")
        except OSError as exc:
            stats.errors.append(f"{current}: {type(exc).__name__}: {exc}")
    return stats


def _validate_persona_name(persona: str) -> str:
    from webui.persona_admin import PersonaAdminError, validate_persona_name

    try:
        return validate_persona_name(persona)
    except PersonaAdminError as exc:
        raise DestructiveAdminError("invalid_persona", str(exc)) from exc


def _is_direct_child(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().parent == parent.resolve()
    except (OSError, RuntimeError):
        return False


def resolve_persona_targets(paths: Any, persona: str) -> dict[str, Path]:
    name = _validate_persona_name(persona)
    definition = Path(paths.PERSONAS_DIR) / name
    if not (definition / "persona_prompt.py").is_file():
        raise DestructiveAdminError("persona_not_found", f"人格 {name!r} 不存在")
    memory = Path(paths.memory_dir_for(name))
    vector = Path(paths.vector_dir_for(name))
    for label, target, parent in (
        ("memory", memory, Path(paths.MEMORY_DIR)),
        ("vector", vector, Path(paths.VECTOR_DIR)),
    ):
        try:
            if target.is_symlink():
                raise DestructiveAdminError(
                    "unsafe_target",
                    f"{label} 目录是符号链接，拒绝删除",
                )
        except OSError as exc:
            raise DestructiveAdminError(
                "unsafe_target",
                f"无法检查 {label} 目录：{exc}",
            ) from exc
        if not _is_direct_child(target, parent):
            raise DestructiveAdminError(
                "unsafe_target",
                f"{label} 目录不在预期数据根下，拒绝删除",
            )
    return {
        "persona": name,
        "definition": definition,
        "memory": memory,
        "vector": vector,
    }


def _knowledge_counts(paths: Any, persona: str) -> dict[str, Any]:
    path = Path(paths.DATA_DIR) / "knowledge.json"
    store = KnowledgeStore(path)
    private = sum(
        1
        for item in store._entries
        if item.get("persona_id") == persona and not item.get("shared")
    )
    shared = sum(
        1
        for item in store._entries
        if item.get("persona_id") == persona and item.get("shared")
    )
    return {
        "path": str(path),
        "exists": path.exists(),
        "writable": bool(store.writable),
        "total_entries": len(store._entries),
        "private_entries": private,
        "shared_entries": shared,
    }


def _remove_private_knowledge(paths: Any, persona: str) -> int:
    path = Path(paths.DATA_DIR) / "knowledge.json"
    store = KnowledgeStore(path)
    return store.delete_private_persona_entries(persona)


def _ensure_empty_persona_db(paths: Any, persona: str) -> Path:
    target = Path(paths.memory_dir_for(persona)) / f"{persona}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    db = KarenDB(target)
    db.load()
    db.close()
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def _remove_tree_safe(path: Path) -> dict[str, Any]:
    """Atomically rename a tree out of the way, then remove it without following links."""
    target = Path(path)
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return {"status": "missing", "bytes": 0, "files": 0}
    except OSError as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    if os.path.islink(target):
        return {"status": "failed", "error": "root_is_symlink"}
    if not os.path.isdir(target):
        return {"status": "failed", "error": "not_a_directory"}
    stats = scan_tree(target)
    staged = target.with_name(f".{target.name}.delete-{secrets.token_hex(6)}")
    try:
        os.replace(target, staged)
    except OSError as exc:
        return {
            "status": "failed",
            "error": f"rename_failed: {type(exc).__name__}: {exc}",
        }
    errors: list[str] = []
    try:
        _rmtree_no_follow(staged, errors)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
    status = "deleted" if not errors else "partial"
    return {
        "status": status,
        "bytes": stats.bytes,
        "files": stats.files,
        "errors": errors,
        "device": int(getattr(info, "st_dev", 0) or 0),
    }


def _rmtree_no_follow(path: Path, errors: list[str]) -> None:
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                        os.unlink(entry.path)
                    elif entry.is_dir(follow_symlinks=False):
                        _rmtree_no_follow(Path(entry.path), errors)
                except OSError as exc:
                    errors.append(f"{entry.path}: {type(exc).__name__}: {exc}")
        os.rmdir(path)
    except OSError as exc:
        errors.append(f"{path}: {type(exc).__name__}: {exc}")


def _safe_persona_filename(persona: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in "_-一" else "_" for ch in persona
    ).strip("._-")
    return cleaned[:40] or "persona"


def _backup_directory(host: Any) -> Path:
    from core.backup import resolve_backup_directory

    raw = ""
    rt = getattr(host, "rt", None)
    if rt is not None:
        raw = str(getattr(getattr(rt.config, "backup", None), "directory", "") or "")
    else:
        try:
            cfg = host.load_config()
            raw = str(getattr(getattr(cfg, "backup", None), "directory", "") or "")
        except Exception:  # noqa: BLE001
            raw = ""
    return resolve_backup_directory(raw)


def _create_persona_backup(
    paths: Any,
    *,
    persona: str,
    memory: Path,
    vector: Path,
    knowledge_private: list[dict[str, Any]],
    destination: Path,
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = destination / (
        f"{PERSONA_BACKUP_PREFIX}{_safe_persona_filename(persona)}-{stamp}-"
        f"{secrets.token_hex(3)}.zip"
    )
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    files = 0
    bytes_written = 0
    try:
        with zipfile.ZipFile(
            tmp,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1,
        ) as archive:
            for label, root in (("memory", memory), ("vector", vector)):
                if not root.is_dir() or root.is_symlink():
                    continue
                for candidate in sorted(root.rglob("*")):
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    arc = f"{label}/{candidate.relative_to(root).as_posix()}"
                    archive.write(candidate, arc)
                    files += 1
                    try:
                        bytes_written += candidate.stat().st_size
                    except OSError:
                        pass
            manifest = {
                "format": 1,
                "kind": "persona_runtime_cleanup",
                "persona": persona,
                "created_at": _now_iso(),
                "knowledge_private": knowledge_private,
                "files": files,
                "bytes": bytes_written,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
        with zipfile.ZipFile(tmp, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"备份校验失败：{corrupt}")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    digest = _sha256_file(target)
    return {
        "path": str(target),
        "bytes": target.stat().st_size,
        "files": files,
        "sha256": digest,
    }


def _public_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "job_id": job.get("job_id"),
        "preview_id": job.get("preview_id"),
        "action": job.get("action"),
        "subject": job.get("subject"),
        "state": job.get("state"),
        "phase": job.get("phase"),
        "progress": job.get("progress"),
        "result": job.get("result"),
        "error_code": job.get("error_code"),
        "error_message": job.get("error_message"),
        "created_at": _iso_from_epoch(job.get("created_at")),
        "started_at": _iso_from_epoch(job.get("started_at")),
        "finished_at": _iso_from_epoch(job.get("finished_at")),
        "cancel_requested": bool(job.get("cancel_requested")),
    }


def _iso_from_epoch(value: Any) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return datetime.fromtimestamp(number, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _persona_generation(
    targets: dict[str, Path], *, active: bool, mode: str
) -> str:
    return _sha256_json(
        {
            "action": PERSONA_CLEANUP,
            "persona": targets["persona"],
            "memory": str(targets["memory"].resolve()),
            "vector": str(targets["vector"].resolve()),
            "mode": mode,
            "active": active,
        }
    )


class PersonaCleanupService:
    def __init__(
        self,
        host: Any,
        store: AdminStore,
        *,
        on_restarted: Any = None,
    ) -> None:
        self.host = host
        self.store = store
        self._on_restarted = on_restarted
        self._tasks: set[asyncio.Task] = set()
        self._startup_done = False
        self._startup_lock = asyncio.Lock()

    async def startup(self) -> None:
        if self._startup_done:
            return
        async with self._startup_lock:
            if self._startup_done:
                return
            await self.store.startup()
            self._startup_done = True

    async def _initialize(self) -> None:
        await self.startup()

    def _paths(self) -> Any:
        rt = getattr(self.host, "rt", None)
        return rt.paths if rt is not None else self.host.build_paths()

    def _active_persona(self) -> str:
        rt = getattr(self.host, "rt", None)
        if rt is not None:
            return str(getattr(getattr(rt, "persona", None), "name", "") or "")
        try:
            cfg = self.host.load_config()
            return str(getattr(getattr(cfg, "persona", None), "active", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    async def preview(self, persona: str) -> dict[str, Any]:
        await self._initialize()
        paths = self._paths()
        targets = resolve_persona_targets(paths, persona)
        memory_stats = scan_tree(targets["memory"])
        vector_stats = scan_tree(targets["vector"])
        knowledge = _knowledge_counts(paths, targets["persona"])
        if knowledge["exists"] and not knowledge["writable"]:
            raise DestructiveAdminError(
                "knowledge_unreadable",
                "知识库上次读取失败，处于只读状态；请先修复知识库再清理",
            )
        active = self._active_persona()
        is_active = bool(active and active == targets["persona"])
        rt = getattr(self.host, "rt", None)
        mode = "pause_resume" if rt is not None else "offline"
        phrase = _persona_phrase(targets["persona"])
        generation = _persona_generation(
            targets, active=is_active, mode=mode
        )
        now = time.time()
        preview_id = f"prev_{secrets.token_urlsafe(18)}"
        token = secrets.token_urlsafe(32)
        expires_at = now + PERSONA_PREVIEW_TTL_SECONDS
        plan = {
            "persona": targets["persona"],
            "memory": str(targets["memory"]),
            "vector": str(targets["vector"]),
            "active": is_active,
            "mode": mode,
            "phrase": phrase,
            "knowledge": knowledge,
            "memory_stats": memory_stats.as_dict(),
            "vector_stats": vector_stats.as_dict(),
        }
        await self.store.create_plan(
            preview_id=preview_id,
            action=PERSONA_CLEANUP,
            subject=targets["persona"],
            created_at=now,
            expires_at=expires_at,
            generation=generation,
            token_hash=token_fingerprint(token, preview_id=preview_id),
            plan=plan,
        )
        return {
            "ok": True,
            "action": PERSONA_CLEANUP,
            "persona": targets["persona"],
            "active": is_active,
            "runtime_mode": mode,
            "requires_runtime_restart": bool(rt is not None),
            "preview_id": preview_id,
            "confirmation_token": token,
            "confirmation_phrase": phrase,
            "expires_at": _iso_from_epoch(expires_at),
            "generation": generation,
            "memory": memory_stats.as_dict(),
            "vector": vector_stats.as_dict(),
            "knowledge": knowledge,
            "expected_bytes": memory_stats.bytes + vector_stats.bytes,
            "expected_files": memory_stats.files + vector_stats.files,
            "protected": [
                {"key": "persona_definition", "path": str(targets["definition"])},
                {"key": "shared_knowledge"},
                {"key": "shared_slang"},
                {"key": "workspace", "path": str(paths.WORKSPACE_DIR)},
                {"key": "logs", "path": str(paths.LOGS_DIR)},
                {"key": "emoji", "path": str(paths.EMOJI_DIR)},
                {"key": "config_and_secrets", "path": str(paths.DATA_DIR)},
                {"key": "backups"},
                {"key": "other_personas", "path": str(paths.MEMORY_DIR)},
            ],
            "warnings": [
                "执行时会短暂停止 Runtime，删除后自动恢复。",
                "只删除该人格的私有知识；共享知识和群共享黑话保留。",
                "未勾选备份时，删除内容不可恢复。",
            ],
        }

    async def execute(
        self,
        persona: str,
        *,
        preview_id: str,
        confirmation_token: str,
        expected_generation: str,
        idempotency_key: str,
        typed_confirmation: str,
        acknowledge_destructive: bool,
        create_backup: bool,
    ) -> tuple[dict[str, Any], bool]:
        await self._initialize()
        name = _validate_persona_name(persona)
        plan = await self.store.get_plan(preview_id)
        if plan is None:
            raise DestructiveAdminError("preview_not_found", "预览不存在或已过期")
        if plan.get("action") != PERSONA_CLEANUP or plan.get("subject") != name:
            raise DestructiveAdminError("preview_subject_mismatch", "预览目标不匹配")
        if float(plan.get("expires_at") or 0) < time.time():
            raise DestructiveAdminError("preview_expired", "预览已过期，请重新预览")
        if str(plan.get("state")) != "ready":
            raise DestructiveAdminError("preview_already_used", "预览已执行")
        expected_hash = token_fingerprint(confirmation_token, preview_id=preview_id)
        if not secrets.compare_digest(
            str(plan.get("token_hash") or ""), expected_hash
        ):
            raise DestructiveAdminError("confirmation_token_invalid", "确认令牌不正确")
        if str(plan.get("generation") or "") != expected_generation:
            raise DestructiveAdminError("generation_conflict", "目标已变化，请重新预览")
        payload = plan.get("plan") or {}
        if str(payload.get("phrase") or "") != str(typed_confirmation or "").strip():
            raise DestructiveAdminError("confirmation_phrase_mismatch", "确认短语不正确")
        if not acknowledge_destructive:
            raise DestructiveAdminError("acknowledgement_required", "请勾选不可撤销确认")
        if not idempotency_key.strip():
            raise DestructiveAdminError("idempotency_required", "缺少幂等键")

        paths = self._paths()
        current_targets = resolve_persona_targets(paths, name)
        current_mode = "pause_resume" if self.host.rt is not None else "offline"
        current_active = bool(self._active_persona() == name)
        if _persona_generation(
            current_targets, active=current_active, mode=current_mode
        ) != expected_generation:
            raise DestructiveAdminError(
                "generation_conflict", "目标或运行状态已变化，请重新预览"
            )

        job_id = f"adm_{secrets.token_urlsafe(22)}"
        try:
            job, created = await self.store.create_job(
                job_id=job_id,
                preview_id=preview_id,
                idempotency_key=idempotency_key,
                action=PERSONA_CLEANUP,
                subject=name,
            )
        except AdminConflict as exc:
            raise DestructiveAdminError(str(exc), "任务状态冲突") from exc
        if created:
            task = asyncio.create_task(
                self._run_job(job_id, payload, create_backup),
                name=f"persona-cleanup-{job_id}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return _public_job(job) or {}, created

    async def _run_job(
        self,
        job_id: str,
        plan: dict[str, Any],
        create_backup: bool,
    ) -> None:
        paths = self._paths()
        memory = Path(str(plan["memory"]))
        vector = Path(str(plan["vector"]))
        persona = str(plan["persona"])
        active = bool(plan.get("active"))
        was_running = False
        paused = False
        terminal: str | None = None
        runtime_error: str | None = None
        result: dict[str, Any] = {
            "persona": persona,
            "backup": None,
            "memory": None,
            "vector": None,
            "knowledge": None,
            "legacy_usage": None,
            "runtime": {
                "was_running": False,
                "stopped": False,
                "restarted": False,
                "error": None,
            },
            "complete": False,
        }
        try:
            await self.store.update_job(
                job_id,
                state="running",
                phase="preflight",
                started=True,
            )
            was_running = await self.host.pause_for_admin("persona_cleanup")
            paused = True
            result["runtime"]["was_running"] = was_running
            result["runtime"]["stopped"] = was_running

            if await self.store.is_cancel_requested(job_id):
                terminal = "cancelled"
                await self.store.update_job(
                    job_id,
                    state="cancelled",
                    phase="cancelled",
                    result={**result, "cancelled": True},
                    finished=True,
                )
                return

            knowledge_private: list[dict[str, Any]] = []
            if create_backup:
                await self.store.update_job(
                    job_id, state="running", phase="backing_up"
                )
                store = KnowledgeStore(Path(paths.DATA_DIR) / "knowledge.json")
                knowledge_private = [
                    dict(item)
                    for item in store._entries
                    if item.get("persona_id") == persona and not item.get("shared")
                ]
                backup_dir = _backup_directory(self.host)
                backup_info = await asyncio.to_thread(
                    _create_persona_backup,
                    paths,
                    persona=persona,
                    memory=memory,
                    vector=vector,
                    knowledge_private=knowledge_private,
                    destination=backup_dir,
                )
                result["backup"] = backup_info

            if await self.store.is_cancel_requested(job_id):
                terminal = "cancelled"
                await self.store.update_job(
                    job_id,
                    state="cancelled",
                    phase="cancelled",
                    result={**result, "cancelled": True},
                    finished=True,
                )
                return

            await self.store.update_job(
                job_id, state="running", phase="writing_cleanup_marker"
            )
            marker = await asyncio.to_thread(
                write_cleanup_marker, paths, persona
            )
            result["legacy_usage"] = {
                "marker_path": str(marker),
                "suppressed": True,
            }

            await self.store.update_job(
                job_id, state="running", phase="updating_knowledge"
            )
            removed_knowledge = await asyncio.to_thread(
                _remove_private_knowledge, paths, persona
            )
            result["knowledge"] = {
                "removed": removed_knowledge,
                "shared_kept": int(plan.get("knowledge", {}).get("shared_entries") or 0),
            }

            if await self.store.is_cancel_requested(job_id):
                terminal = "cancelled"
                await self.store.update_job(
                    job_id,
                    state="cancelled",
                    phase="cancelled",
                    result={**result, "cancelled": True, "partial": True},
                    finished=True,
                )
                return

            await self.store.update_job(
                job_id, state="running", phase="deleting_memory"
            )
            memory_result = await asyncio.to_thread(_remove_tree_safe, memory)
            result["memory"] = memory_result
            await self.store.update_job(
                job_id, state="running", phase="deleting_vector"
            )
            vector_result = await asyncio.to_thread(_remove_tree_safe, vector)
            result["vector"] = vector_result
            result["bytes_freed"] = int(memory_result.get("bytes") or 0) + int(
                vector_result.get("bytes") or 0
            )
            result["files_deleted"] = int(memory_result.get("files") or 0) + int(
                vector_result.get("files") or 0
            )

            if active:
                await self.store.update_job(
                    job_id, state="running", phase="creating_empty_database"
                )
                if memory_result.get("status") not in {"deleted", "missing"}:
                    result["empty_database"] = False
                    result["empty_database_error"] = "memory 目录未完整删除，拒绝创建空库"
                else:
                    try:
                        await asyncio.to_thread(
                            _ensure_empty_persona_db, paths, persona
                        )
                        result["empty_database"] = True
                    except Exception as exc:  # noqa: BLE001
                        result["empty_database"] = False
                        result["empty_database_error"] = str(exc)[:300]

            ok = (
                memory_result.get("status") in {"deleted", "missing"}
                and vector_result.get("status") in {"deleted", "missing"}
                and result.get("empty_database", True) is not False
            )
            result["complete"] = bool(ok)
        except Exception as exc:  # noqa: BLE001
            logger.exception("人格清理任务失败 job=%s", job_id)
            result["error"] = f"{type(exc).__name__}: {exc}"[:500]
            result["complete"] = False
            terminal = "failed"
            await self.store.update_job(
                job_id,
                state="failed",
                phase="failed",
                result=result,
                error_code="persona_cleanup_failed",
                error_message=str(exc),
                finished=True,
            )
        finally:
            if paused:
                try:
                    restarted = await self.host.resume_after_admin()
                    result["runtime"]["restarted"] = bool(restarted)
                    if was_running and not restarted:
                        runtime_error = self.host.last_error or "Runtime 未能恢复"
                        result["runtime"]["error"] = runtime_error
                    elif restarted and self._on_restarted is not None:
                        try:
                            self._on_restarted()
                        except Exception:  # noqa: BLE001
                            logger.warning("清理后重新挂接事件时间线失败", exc_info=True)
                except Exception as exc:  # noqa: BLE001
                    runtime_error = f"{type(exc).__name__}: {exc}"
                    result["runtime"]["error"] = runtime_error
                    logger.exception("人格清理后恢复 Runtime 失败")
            if terminal is None:
                if result.get("complete") is True and runtime_error is None:
                    await self.store.update_job(
                        job_id,
                        state="completed",
                        phase="completed",
                        result=result,
                        finished=True,
                    )
                else:
                    await self.store.update_job(
                        job_id,
                        state="partial",
                        phase="partial",
                        result=result,
                        error_code="persona_cleanup_partial",
                        error_message=(
                            runtime_error or result.get("error") or "部分删除失败"
                        ),
                        finished=True,
                    )

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        await self._initialize()
        return _public_job(await self.store.get_job(job_id))

    async def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        await self._initialize()
        return [_public_job(job) or {} for job in await self.store.list_jobs(limit)]

    async def cancel(self, job_id: str) -> dict[str, Any]:
        await self._initialize()
        if not await self.store.request_cancel(job_id):
            raise DestructiveAdminError(
                "job_not_cancellable", "任务已经进入删除阶段或已结束"
            )
        return {"ok": True, "job_id": job_id, "message": "已请求取消"}

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


def _host_paths(host: Any) -> Any:
    rt = getattr(host, "rt", None)
    return rt.paths if rt is not None else host.build_paths()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _is_within_lexical(path: Path, parent: Path) -> bool:
    """Containment by absolute path, without resolving symlink targets."""
    try:
        Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(parent)))
        return True
    except (OSError, ValueError):
        return False


def _file_markers(path: Path, markers: tuple[str, ...]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _pid_start_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        fields = raw.rsplit(")", 1)[1].strip().split()
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def detect_launch_mode(*, test_mode: bool = False) -> dict[str, Any]:
    if test_mode:
        return {
            "supported": True,
            "mode": "test",
            "reason": "",
            "manual_steps": "",
        }
    if not sys.platform.startswith("linux"):
        return {
            "supported": False,
            "mode": sys.platform,
            "reason": "当前平台不支持自动卸载源码；请使用系统卸载流程或手动删除。",
            "manual_steps": (
                "1. 停止 KarenBot 服务。\n"
                "2. 手动删除项目目录、数据目录和程序备份。\n"
                "3. 删除启动器/systemd unit（如有）。"
            ),
        }
    try:
        from core.backend_restart import systemd_scope

        scope = systemd_scope()
    except Exception:  # noqa: BLE001
        scope = None
    if scope is not None:
        return {
            "supported": False,
            "mode": f"systemd_{scope}",
            "reason": "当前进程受 systemd 管理，自动卸载可能被服务的重启策略打断；请使用手动流程。",
            "manual_steps": (
                f"1. 执行 systemctl --user disable --now {'karenbot.service' if scope == 'user' else 'karenbot.service'}。\n"
                "2. 手动删除 unit、项目目录、数据目录和程序备份。\n"
                "3. 如为 system 级 unit，请用 root 权限执行。"
            ),
        }
    return {
        "supported": True,
        "mode": "fallback",
        "reason": "",
        "manual_steps": "",
    }


def _backup_library_stats(path: Path) -> dict[str, int]:
    recognized = 0
    recognized_bytes = 0
    ignored = 0
    try:
        entries = list(path.iterdir())
    except OSError:
        return {"recognized_files": 0, "recognized_bytes": 0, "ignored": 0}
    for entry in entries:
        name = entry.name
        is_recognized = (
            (entry.is_file() and (
                name.startswith("Karen_Backup_") and name.endswith(".zip")
                or name.startswith("Karen_Backup_") and name.endswith(".zip.json")
            ))
            or (entry.is_dir() and name.startswith(".backup-work-"))
        )
        if not is_recognized:
            ignored += 1
            continue
        if entry.is_dir():
            stats = scan_tree(entry)
            recognized += stats.files
            recognized_bytes += stats.bytes
        else:
            recognized += 1
            try:
                recognized_bytes += entry.stat().st_size
            except OSError:
                pass
    return {
        "recognized_files": recognized,
        "recognized_bytes": recognized_bytes,
        "ignored": ignored,
    }


def _target_record(
    kind: str,
    path: Path,
    *,
    recognized_globs: tuple[str, ...] = (),
) -> dict[str, Any]:
    target = Path(path)
    stats = scan_tree(target)
    record = {
        "kind": kind,
        "path": str(target),
        "exists": stats.exists,
        "is_symlink": stats.is_symlink,
        "bytes": stats.bytes,
        "files": stats.files,
        "dirs": stats.dirs,
        "symlinks": stats.symlinks,
        "recognized_globs": list(recognized_globs),
    }
    try:
        info = os.lstat(target)
    except OSError:
        info = None
    record["dev"] = int(getattr(info, "st_dev", 0) or 0)
    record["ino"] = int(getattr(info, "st_ino", 0) or 0)
    if kind == "backup_library":
        recognized = _backup_library_stats(target)
        record["bytes"] = recognized["recognized_bytes"]
        record["files"] = recognized["recognized_files"]
        record["ignored"] = recognized["ignored"]
    return record


def _add_candidate(candidates: list[dict[str, Any]], kind: str, path: Path) -> None:
    target = Path(path)
    candidates.append(
        _target_record(
            kind,
            target,
            recognized_globs=BACKUP_GLOBS if kind == "backup_library" else (),
        )
    )


def build_uninstall_plan(
    host: Any,
    *,
    plan_id: str,
    test_mode: bool = False,
    test_root: Path | None = None,
) -> dict[str, Any]:
    """Enumerate only app-known targets. Never accepts a client path."""
    paths = _host_paths(host)
    project = Path(paths.PROJECT_ROOT).resolve()
    root_data = Path(paths.ROOT_DATA_DIR).resolve()
    home = Path.home()
    if test_mode:
        test_root = Path(
            test_root
            or os.environ.get("KAREN_UNINSTALL_TEST_ROOT")
            or project
        ).resolve()
    else:
        test_root = None
    candidates: list[dict[str, Any]] = []

    def _add(kind: str, path: Path) -> None:
        target = Path(path).expanduser()
        if test_mode:
            if not _is_within(target, test_root):
                return
        if not target.exists():
            return
        _add_candidate(candidates, kind, target)

    _add("project_root", project)
    _add("data_root", root_data)
    _add("data_dir", Path(paths.DATA_DIR))

    for kind, known in (
        ("known_data_root", Path(user_data_dir("KarenBot", appauthor=False))),
        ("known_data_root", Path(user_data_dir("Debata_Agent", appauthor=False))),
    ):
        if known.exists() and (
            (known / "instances").is_dir()
            or (known / "root.json").is_file()
            or (known / "instance.json").is_file()
        ):
            _add(kind, known)

    for label, path in (
        ("config_file", Path(paths.CONFIG_FILE)),
        ("secrets_file", Path(paths.SECRETS_FILE)),
        ("secrets_meta", Path(paths.SECRETS_META_FILE)),
        ("rsa_public", Path(paths.RSA_PUBLIC_KEY_FILE)),
        ("rsa_private", Path(paths.RSA_PRIVATE_KEY_FILE)),
    ):
        _add(label, path)

    from core.backup import resolve_backup_directory

    backup_dirs: list[Path] = [resolve_backup_directory(None)]
    try:
        cfg = getattr(host, "rt", None)
        cfg_obj = getattr(cfg, "config", None) if cfg is not None else host.load_config()
        configured = str(
            getattr(getattr(cfg_obj, "backup", None), "directory", "") or ""
        )
        backup_dirs.append(resolve_backup_directory(configured))
    except Exception:  # noqa: BLE001
        pass
    backup_dirs.append(Path.home() / UNINSTALL_BACKUP_PREFIX)
    seen_backup_dirs: set[str] = set()
    for directory in backup_dirs:
        key = str(directory.resolve())
        if key in seen_backup_dirs:
            continue
        seen_backup_dirs.add(key)
        _add("backup_library", directory)

    for launcher in (home / ".local" / "bin" / "karen", home / ".local" / "bin" / "debata"):
        if launcher.is_file() and not launcher.is_symlink() and _file_markers(
            launcher, ("karen", "debata", str(project))
        ):
            _add("launcher", launcher)

    for unit in (
        home / ".config" / "systemd" / "user" / "karenbot.service",
        home / ".config" / "systemd" / "user" / "debata-agent.service",
    ):
        if unit.is_file() and not unit.is_symlink() and _file_markers(
            unit, (str(project), "karenbot", "debata agent")
        ):
            _add("systemd_unit", unit)
            for wants in (
                home / ".config" / "systemd" / "user" / "default.target.wants",
                home / ".config" / "systemd" / "user" / "multi-user.target.wants",
            ):
                link = wants / unit.name
                if link.is_symlink() and _is_within(link, test_root or home):
                    candidates.append(_target_record("systemd_enable_link", link))

    for env_file in (
        home / ".config" / "karenbot.env",
        home / ".config" / "debata-agent.env",
    ):
        if env_file.is_file() and not env_file.is_symlink():
            _add("env_file", env_file)

    # Outer directories cover nested files; do not delete the same data twice.
    candidates.sort(key=lambda item: (len(item["path"]), item["path"]))
    targets: list[dict[str, Any]] = []
    deduped: list[dict[str, Any]] = []
    for item in candidates:
        parent = next(
            (
                kept
                for kept in targets
                if Path(item["path"]) == Path(kept["path"])
                or _is_within_lexical(Path(item["path"]), Path(kept["path"]))
            ),
            None,
        )
        if parent is not None:
            deduped.append({"path": item["path"], "covered_by": parent["path"]})
            continue
        targets.append(item)

    audit_dir = (
        test_root / "audit"
        if test_mode
        else home / ".local" / "state" / "karenbot" / "uninstall"
    )
    backup_dir = (
        test_root / "backup" / plan_id
        if test_mode
        else home / UNINSTALL_BACKUP_PREFIX / plan_id
    )
    launch = detect_launch_mode(test_mode=test_mode)
    forbidden = {
        Path("/"), home, home.parent, Path(tempfile.gettempdir())
    }
    if test_mode:
        forbidden = {Path("/")}

    for item in targets:
        target = Path(item["path"])
        if not target.is_absolute():
            raise DestructiveAdminError("unsafe_target", f"目标不是绝对路径：{target}")
        if ".." in target.parts:
            raise DestructiveAdminError("unsafe_target", f"目标包含 ..：{target}")
        if target in forbidden:
            raise DestructiveAdminError("unsafe_target", f"拒绝删除危险路径：{target}")
        if item.get("is_symlink") and item.get("kind") != "systemd_enable_link":
            raise DestructiveAdminError("unsafe_target", f"目标是符号链接：{target}")
        if _is_within(audit_dir, target):
            raise DestructiveAdminError(
                "unsafe_target",
                f"删除目标会覆盖审计目录：{target}",
            )
        if _is_within(backup_dir, target) and item.get("kind") != "backup_library":
            raise DestructiveAdminError(
                "unsafe_target",
                f"删除目标会覆盖备份目录：{target}",
            )
        if test_mode and not _is_within(target, test_root):
            raise DestructiveAdminError("unsafe_target", f"测试目标越界：{target}")

    if launch["supported"]:
        rt = getattr(host, "rt", None)
        backup_available = bool(
            rt is not None
            and getattr(host, "state", "") == "running"
            and getattr(rt, "secrets", None) is not None
        )
        backup_reason = "" if backup_available else "Runtime 未运行，无法创建完整备份"
        supported = True
        reason = ""
    else:
        backup_available = False
        backup_reason = launch["reason"]
        supported = False
        reason = launch["reason"]

    retained = [
        {"kind": "development_backup", "path": str(home / "Debata_BeiFen")},
        {"kind": "development_backup", "path": str(home / "debata-backups")},
        {"kind": "github_remote", "value": "不访问、不修改 Git 远端"},
        {"kind": "os_keyring", "value": "不删除系统 keyring 条目"},
        {"kind": "napcat_docker", "value": "不删除 NapCat 或 Docker 资源"},
        {"kind": "audit", "path": str(audit_dir)},
        {"kind": "uninstall_backup", "path": str(backup_dir)},
    ]
    for item in targets:
        if item.get("ignored"):
            retained.append({
                "kind": "unrecognized_backup_entry",
                "path": item["path"],
                "ignored_entries": item["ignored"],
            })

    generation = _sha256_json({
        "action": UNINSTALL,
        "launch_mode": launch["mode"],
        "targets": [
            {"kind": item["kind"], "path": item["path"]}
            for item in targets
        ],
    })
    return {
        "plan_id": plan_id,
        "supported": supported,
        "unsupported_reason": reason or None,
        "manual_steps": launch.get("manual_steps", ""),
        "launch": launch,
        "targets": targets,
        "deduped": deduped,
        "retained": retained,
        "project_root": str(project),
        "audit_dir": str(audit_dir),
        "audit_path": str(audit_dir / f"uninstall-{plan_id}.json"),
        "log_path": str(audit_dir / f"uninstall-{plan_id}.log"),
        "backup_dir": str(backup_dir),
        "optional_backup": {
            "available": backup_available,
            "reason": backup_reason,
            "default": False,
            "directory": str(backup_dir),
        },
        "expected_bytes": sum(int(item.get("bytes") or 0) for item in targets),
        "expected_files": sum(int(item.get("files") or 0) for item in targets),
        "generation": generation,
        "forbidden": [str(item) for item in forbidden],
    }


def _source_archive(project_root: Path, target: Path) -> dict[str, Any]:
    excluded_dirs = {
        ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache",
        ".karen-run", ".debata-run",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    files = 0
    try:
        with zipfile.ZipFile(
            tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            for base, dirnames, filenames in os.walk(project_root):
                dirnames[:] = [name for name in dirnames if name not in excluded_dirs]
                for filename in filenames:
                    source = Path(base) / filename
                    if source.is_symlink() or not source.is_file():
                        continue
                    try:
                        relative = source.relative_to(project_root)
                    except ValueError:
                        continue
                    archive.write(source, f"source/{relative.as_posix()}")
                    files += 1
        with zipfile.ZipFile(tmp, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"源码备份校验失败：{corrupt}")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    digest = _sha256_file(target)
    return {
        "path": str(target),
        "bytes": target.stat().st_size,
        "files": files,
        "sha256": digest,
    }


async def _create_uninstall_backup(
    host: Any,
    *,
    plan: dict[str, Any],
    update: Any,
) -> dict[str, Any]:
    rt = getattr(host, "rt", None)
    if rt is None:
        raise DestructiveAdminError("backup_requires_runtime", "Runtime 未运行，无法创建备份")
    from core.backup import TERMINAL_JOB_STATES, BackupCoordinator, BackupService

    paths = rt.paths
    backup_dir = Path(plan["backup_dir"])
    if any(
        _is_within(backup_dir, Path(target["path"]))
        and target.get("kind") != "backup_library"
        for target in plan["targets"]
    ):
        raise DestructiveAdminError("backup_inside_target", "备份目录在删除目标内")
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    coordinator = BackupCoordinator(host.project_root, paths)
    manager = BackupService(
        host.project_root,
        paths,
        backup_dir=backup_dir,
        include_media=True,
        secrets_manager=getattr(rt, "secrets", None),
        coordinator=coordinator,
    )
    job = await manager.start(include_media=True)
    job_id = str(job.get("id") or "")
    while str(job.get("state") or "") not in TERMINAL_JOB_STATES:
        await update(
            phase="backing_up",
            progress={
                "bytes_done": int(job.get("processed_bytes") or 0),
                "bytes_total": int(job.get("total_bytes") or 0),
                "stage": job.get("stage"),
            },
        )
        await asyncio.sleep(0.5)
        next_job = manager.get_job(job_id)
        if not next_job:
            raise DestructiveAdminError("backup_not_verified", "备份任务状态丢失")
        job = next_job
    if str(job.get("state") or "") != "done" or job.get("partial"):
        error = (job.get("error") or {}).get("message") if isinstance(job.get("error"), dict) else job.get("error")
        raise DestructiveAdminError(
            "backup_not_verified",
            f"备份未完整完成：{error or job.get('state')}",
        )
    if str(job.get("validation_status") or "") != "verified":
        raise DestructiveAdminError("backup_not_verified", "备份校验未通过")
    filename = str(job.get("filename") or "")
    if not filename:
        raise DestructiveAdminError("backup_not_verified", "备份没有生成文件")
    zip_path = backup_dir / filename
    if not zip_path.is_file() or zip_path.is_symlink():
        raise DestructiveAdminError("backup_not_verified", "备份文件不存在或不是普通文件")
    source = await asyncio.to_thread(
        _source_archive, Path(host.project_root), backup_dir / "source.zip"
    )
    return {
        "user_backup": {
            "path": str(zip_path),
            "bytes": int(zip_path.stat().st_size),
            "sha256": str(job.get("sha256") or ""),
            "validation_status": job.get("validation_status"),
        },
        "source_archive": source,
        "directory": str(backup_dir),
    }


def _helper_source() -> Path:
    return Path(__file__).resolve().parents[1] / "tools" / "karen_uninstall_helper.py"


def _write_helper_plan(plan: dict[str, Any], path: Path) -> None:
    payload = dict(plan)
    payload.pop("plan_digest", None)
    payload["plan_digest"] = _sha256_json(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


class UninstallService:
    def __init__(
        self,
        host: Any,
        store: AdminStore,
        *,
        exit_callback: Any = None,
        test_mode: bool = False,
        test_root: Path | None = None,
    ) -> None:
        self.host = host
        self.store = store
        self.exit_callback = exit_callback
        self.test_mode = bool(test_mode)
        self.test_root = Path(test_root).resolve() if test_root else None
        self._tasks: set[asyncio.Task] = set()
        self._startup_done = False
        self._startup_lock = asyncio.Lock()

    async def startup(self) -> None:
        if self._startup_done:
            return
        async with self._startup_lock:
            if self._startup_done:
                return
            await self.store.startup()
            self._startup_done = True

    async def preview(self) -> dict[str, Any]:
        await self.startup()
        preview_id = f"prev_{secrets.token_urlsafe(18)}"
        plan = build_uninstall_plan(
            self.host,
            plan_id=preview_id,
            test_mode=self.test_mode,
            test_root=self.test_root,
        )
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + UNINSTALL_PREVIEW_TTL_SECONDS
        plan["phrase"] = UNINSTALL_PHRASE
        await self.store.create_plan(
            preview_id=preview_id,
            action=UNINSTALL,
            subject="local",
            created_at=now,
            expires_at=expires_at,
            generation=plan["generation"],
            token_hash=token_fingerprint(token, preview_id=preview_id),
            plan=plan,
        )
        public = dict(plan)
        public.pop("token", None)
        public.update({
            "ok": True,
            "action": UNINSTALL,
            "preview_id": preview_id,
            "confirmation_token": token,
            "confirmation_phrase": UNINSTALL_PHRASE,
            "expires_at": _iso_from_epoch(expires_at),
            "warnings": [
                "此操作会永久删除本机源码、虚拟环境、数据目录和程序备份。",
                "WebUI 会立即关闭，删除完成后无法再从本页确认。",
                "未勾选备份时，本机不会保留任何数据副本。",
            ],
        })
        return public

    async def execute(
        self,
        *,
        preview_id: str,
        confirmation_token: str,
        expected_generation: str,
        idempotency_key: str,
        typed_confirmation: str,
        acknowledge_destructive: bool,
        create_backup: bool,
    ) -> tuple[dict[str, Any], bool]:
        await self.startup()
        record = await self.store.get_plan(preview_id)
        if record is None:
            raise DestructiveAdminError("preview_not_found", "预览不存在或已过期")
        if record.get("action") != UNINSTALL or record.get("subject") != "local":
            raise DestructiveAdminError("preview_subject_mismatch", "预览目标不匹配")
        if float(record.get("expires_at") or 0) < time.time():
            raise DestructiveAdminError("preview_expired", "预览已过期")
        if str(record.get("state")) != "ready":
            raise DestructiveAdminError("preview_already_used", "预览已执行")
        expected_hash = token_fingerprint(confirmation_token, preview_id=preview_id)
        if not secrets.compare_digest(str(record.get("token_hash") or ""), expected_hash):
            raise DestructiveAdminError("confirmation_token_invalid", "确认令牌不正确")
        plan = record.get("plan") or {}
        if str(record.get("generation") or "") != expected_generation:
            raise DestructiveAdminError("generation_conflict", "目标已变化，请重新预览")
        if str(plan.get("phrase") or "") != str(typed_confirmation or "").strip():
            raise DestructiveAdminError("confirmation_phrase_mismatch", "确认短语不正确")
        if not acknowledge_destructive:
            raise DestructiveAdminError("acknowledgement_required", "请勾选不可撤销确认")
        if not plan.get("supported"):
            raise DestructiveAdminError(
                "unsupported_platform",
                plan.get("unsupported_reason") or "当前环境不支持自动卸载",
            )
        current = build_uninstall_plan(
            self.host,
            plan_id=str(plan.get("plan_id") or preview_id),
            test_mode=self.test_mode,
            test_root=self.test_root,
        )
        if current.get("generation") != expected_generation:
            raise DestructiveAdminError("generation_conflict", "目标已变化，请重新预览")
        if create_backup and not current.get("optional_backup", {}).get("available"):
            raise DestructiveAdminError(
                "backup_requires_runtime",
                current.get("optional_backup", {}).get("reason") or "无法创建备份",
            )
        job_id = f"adm_{secrets.token_urlsafe(22)}"
        try:
            job, created = await self.store.create_job(
                job_id=job_id,
                preview_id=preview_id,
                idempotency_key=idempotency_key,
                action=UNINSTALL,
                subject="local",
            )
        except AdminConflict as exc:
            raise DestructiveAdminError(str(exc), "任务状态冲突") from exc
        if created:
            task = asyncio.create_task(
                self._run_job(job_id, plan, create_backup),
                name=f"uninstall-{job_id}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return _public_job(job) or {}, created

    async def _update(self, job_id: str, **kwargs: Any) -> None:
        await self.store.update_job(job_id, **kwargs)

    async def _run_job(
        self,
        job_id: str,
        plan: dict[str, Any],
        create_backup: bool,
    ) -> None:
        result: dict[str, Any] = {
            "plan_id": plan.get("plan_id"),
            "backup": None,
            "helper_pid": None,
            "audit_path": plan.get("audit_path"),
            "log_path": plan.get("log_path"),
            "scheduled": False,
        }
        temp_dir: Path | None = None
        guard_held = False
        scheduled = False
        try:
            await self._update(
                job_id, state="running", phase="preflight", started=True
            )
            self.host.begin_admin_operation("uninstall")
            guard_held = True
            if create_backup:
                await self._update(job_id, state="running", phase="backing_up")
                result["backup"] = await _create_uninstall_backup(
                    self.host,
                    plan=plan,
                    update=lambda **kwargs: self._update(job_id, state="running", **kwargs),
                )
            if await self.store.is_cancel_requested(job_id):
                await self._update(
                    job_id,
                    state="cancelled",
                    phase="cancelled",
                    result={**result, "cancelled": True},
                    finished=True,
                )
                return
            if self.exit_callback is None:
                raise DestructiveAdminError(
                    "unsupported_launch_mode", "缺少后端退出回调，拒绝启动卸载助手"
                )
            helper = _helper_source()
            if not helper.is_file():
                raise DestructiveAdminError("unsupported_launch_mode", "卸载助手文件缺失")
            helper_digest = hashlib.sha256(helper.read_bytes()).hexdigest()
            temp_dir = Path(
                tempfile.mkdtemp(
                    prefix="karen-uninstall-",
                    dir=str(self.test_root) if self.test_mode and self.test_root else None,
                )
            )
            staged_helper = temp_dir / "karen_uninstall_helper.py"
            shutil.copy2(helper, staged_helper)
            try:
                os.chmod(staged_helper, 0o700)
            except OSError:
                pass
            audit_dir = Path(plan["audit_dir"])
            audit_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(audit_dir, 0o700)
            except OSError:
                pass
            helper_plan = {
                "format": 1,
                "operation": UNINSTALL,
                "plan_id": plan.get("plan_id"),
                "created_at": _now_iso(),
                "valid_until": time.time() + 3600,
                "operator_uid": os.geteuid() if hasattr(os, "geteuid") else 0,
                "test_mode": self.test_mode,
                "test_root": str(self.test_root) if self.test_mode and self.test_root else "",
                "helper_sha256": helper_digest,
                "backend": {
                    "pid": os.getpid(),
                    "pid_start_ticks": _pid_start_ticks(os.getpid()),
                    "project_root": plan.get("project_root"),
                },
                "service_mode": "test" if self.test_mode else "fallback",
                "targets": plan.get("targets") or [],
                "backup": result.get("backup"),
                "audit": {
                    "result_path": plan.get("audit_path"),
                    "log_path": plan.get("log_path"),
                },
                "keep_paths": [
                    str(plan.get("backup_dir")),
                ] if result.get("backup") else [],
                "forbidden": plan.get("forbidden") or [],
            }
            plan_path = temp_dir / "plan.json"
            await asyncio.to_thread(_write_helper_plan, helper_plan, plan_path)
            spawn_log = temp_dir / "spawn.log"
            with open(spawn_log, "ab") as output:
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        str(staged_helper),
                        "--plan",
                        str(plan_path),
                        "--log",
                        str(plan.get("log_path")),
                    ],
                    cwd="/" if not self.test_mode else str(temp_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
            result["helper_pid"] = proc.pid
            result["scheduled"] = True
            scheduled = True
            await self._update(
                job_id,
                state="scheduled",
                phase="scheduled",
                result=result,
            )
            # Give the HTTP response a chance to reach the browser before exit.
            await asyncio.sleep(1.0)
            try:
                self.exit_callback()
            except Exception:  # noqa: BLE001
                logger.exception("卸载助手已启动，但请求后端退出失败 job=%s", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("卸载任务准备失败 job=%s", job_id)
            result["error"] = f"{type(exc).__name__}: {exc}"[:500]
            if temp_dir is not None:
                result["helper_temp_dir"] = str(temp_dir)
            if not scheduled:
                await self._update(
                    job_id,
                    state="failed",
                    phase="failed",
                    result=result,
                    error_code="uninstall_failed",
                    error_message=str(exc),
                    finished=True,
                )
        finally:
            if guard_held and not scheduled:
                self.host.end_admin_operation()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        await self.startup()
        return _public_job(await self.store.get_job(job_id))

    async def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        await self.startup()
        return [_public_job(job) or {} for job in await self.store.list_jobs(limit)]

    async def cancel(self, job_id: str) -> dict[str, Any]:
        await self.startup()
        if not await self.store.request_cancel(job_id):
            raise DestructiveAdminError("job_not_cancellable", "任务已经调度或已结束")
        return {"ok": True, "job_id": job_id, "message": "已请求取消"}

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


__all__ = [
    "DestructiveAdminError",
    "PERSONA_CLEANUP",
    "PERSONA_PREVIEW_TTL_SECONDS",
    "PersonaCleanupService",
    "UNINSTALL",
    "UNINSTALL_PHRASE",
    "UninstallService",
    "TreeStats",
    "build_uninstall_plan",
    "detect_launch_mode",
    "scan_tree",
    "resolve_persona_targets",
]
