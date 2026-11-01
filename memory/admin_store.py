"""Persisted previews and jobs for destructive admin operations.

Only operational metadata is stored here: scope summaries, hashed confirmation
tokens, job phase/progress and sanitized results. Chat bodies, secrets and token
plaintext never enter this database.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import orjson

ADMIN_SCHEMA_VERSION = 1
TERMINAL_JOB_STATES = {"completed", "partial", "failed", "cancelled", "interrupted"}
ACTIVE_JOB_STATES = {"queued", "running", "cancelling", "scheduled"}


class AdminStoreError(RuntimeError):
    """Recoverable admin-store error."""


class AdminConflict(AdminStoreError):
    """A preview/job state does not permit the requested transition."""


class AdminStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._ready = False
        self._init_lock = threading.Lock()
        self._startup_done = False
        self._startup_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._ensure_schema_sync)

    async def startup(self) -> None:
        """Initialize once per process and mark abandoned jobs interrupted."""
        if self._startup_done:
            return
        async with self._startup_lock:
            if self._startup_done:
                return
            await self.initialize()
            try:
                await self.mark_interrupted()
            except Exception:  # noqa: BLE001
                pass
            self._startup_done = True

    async def create_plan(
        self,
        *,
        preview_id: str,
        action: str,
        subject: str,
        created_at: float,
        expires_at: float,
        generation: str,
        token_hash: str,
        plan: dict[str, Any],
    ) -> None:
        await asyncio.to_thread(
            self._create_plan_sync,
            preview_id,
            action,
            subject,
            created_at,
            expires_at,
            generation,
            token_hash,
            plan,
        )

    def _create_plan_sync(
        self,
        preview_id: str,
        action: str,
        subject: str,
        created_at: float,
        expires_at: float,
        generation: str,
        token_hash: str,
        plan: dict[str, Any],
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO admin_plans (
                        preview_id, action, subject, created_at, expires_at,
                        generation, token_hash, plan_json, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready')
                    """,
                    (
                        preview_id,
                        action,
                        subject,
                        float(created_at),
                        float(expires_at),
                        generation,
                        token_hash,
                        _dumps(plan),
                    ),
                )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    async def get_plan(self, preview_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_plan_sync, preview_id)

    def _get_plan_sync(self, preview_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM admin_plans WHERE preview_id = ?",
                (str(preview_id),),
            ).fetchone()
        return _row_dict(row) if row is not None else None

    async def create_job(
        self,
        *,
        job_id: str,
        preview_id: str,
        idempotency_key: str,
        action: str,
        subject: str,
    ) -> tuple[dict[str, Any], bool]:
        return await asyncio.to_thread(
            self._create_job_sync,
            job_id,
            preview_id,
            idempotency_key,
            action,
            subject,
        )

    def _create_job_sync(
        self,
        job_id: str,
        preview_id: str,
        idempotency_key: str,
        action: str,
        subject: str,
    ) -> tuple[dict[str, Any], bool]:
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT * FROM admin_jobs WHERE idempotency_key = ?",
                    (str(idempotency_key),),
                ).fetchone()
                if existing is not None:
                    if (
                        str(existing["preview_id"]) != preview_id
                        or str(existing["action"]) != action
                        or str(existing["subject"]) != subject
                    ):
                        raise AdminConflict("idempotency_conflict")
                    conn.commit()
                    return _row_dict(existing), False

                plan = conn.execute(
                    "SELECT * FROM admin_plans WHERE preview_id = ?",
                    (preview_id,),
                ).fetchone()
                if plan is None:
                    raise AdminConflict("preview_not_found")
                if str(plan["action"]) != action or str(plan["subject"]) != subject:
                    raise AdminConflict("preview_subject_mismatch")
                if str(plan["state"]) != "ready":
                    raise AdminConflict("preview_already_used")
                if float(plan["expires_at"] or 0) < now:
                    conn.execute(
                        "UPDATE admin_plans SET state = 'expired' WHERE preview_id = ?",
                        (preview_id,),
                    )
                    conn.commit()
                    raise AdminConflict("preview_expired")

                active = conn.execute(
                    """
                    SELECT job_id FROM admin_jobs
                    WHERE state IN ('queued', 'running', 'cancelling', 'scheduled')
                    LIMIT 1
                    """
                ).fetchone()
                if active is not None:
                    raise AdminConflict("operation_in_progress")

                conn.execute(
                    """
                    INSERT INTO admin_jobs (
                        job_id, preview_id, idempotency_key, action, subject,
                        state, phase, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', ?)
                    """,
                    (job_id, preview_id, idempotency_key, action, subject, now),
                )
                conn.execute(
                    """
                    UPDATE admin_plans
                    SET state = 'executing', job_id = ?
                    WHERE preview_id = ? AND state = 'ready'
                    """,
                    (job_id, preview_id),
                )
                job = conn.execute(
                    "SELECT * FROM admin_jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return _row_dict(job), True

    async def update_job(
        self,
        job_id: str,
        *,
        state: str,
        phase: str | None = None,
        progress: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        await asyncio.to_thread(
            self._update_job_sync,
            job_id,
            state,
            phase,
            progress,
            result,
            error_code,
            error_message,
            started,
            finished,
        )

    def _update_job_sync(
        self,
        job_id: str,
        state: str,
        phase: str | None,
        progress: dict[str, Any] | None,
        result: dict[str, Any] | None,
        error_code: str | None,
        error_message: str | None,
        started: bool,
        finished: bool,
    ) -> None:
        now = time.time()
        fields = ["state = ?"]
        values: list[Any] = [str(state)]
        if phase is not None:
            fields.append("phase = ?")
            values.append(str(phase))
        if progress is not None:
            fields.append("progress_json = ?")
            values.append(_dumps(progress))
        if result is not None:
            fields.append("result_json = ?")
            values.append(_dumps(result))
        if error_code is not None:
            fields.append("error_code = ?")
            values.append(str(error_code))
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(str(error_message)[:500])
        if started:
            fields.append("started_at = ?")
            values.append(now)
        if finished:
            fields.append("finished_at = ?")
            values.append(now)
        values.append(job_id)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    f"UPDATE admin_jobs SET {', '.join(fields)} WHERE job_id = ?",
                    values,
                )
                if state in TERMINAL_JOB_STATES:
                    conn.execute(
                        "UPDATE admin_plans SET state = 'finished' WHERE job_id = ?",
                        (job_id,),
                    )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM admin_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        return _row_dict(row) if row is not None else None

    async def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_jobs_sync, max(1, min(100, int(limit))))

    def _list_jobs_sync(self, limit: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM admin_jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_dict(row) for row in rows]

    async def active_job(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._active_job_sync)

    def _active_job_sync(self) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT * FROM admin_jobs
                WHERE state IN ('queued', 'running', 'cancelling', 'scheduled')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        return _row_dict(row) if row is not None else None

    async def request_cancel(self, job_id: str) -> bool:
        return await asyncio.to_thread(self._request_cancel_sync, job_id)

    def _request_cancel_sync(self, job_id: str) -> bool:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE admin_jobs
                    SET cancel_requested = 1, state = 'cancelling'
                    WHERE job_id = ? AND state IN ('queued', 'running')
                    """,
                    (str(job_id),),
                )
                changed = int(cursor.rowcount or 0) > 0
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return changed

    async def is_cancel_requested(self, job_id: str) -> bool:
        job = await self.get_job(job_id)
        return bool(job and job.get("cancel_requested"))

    async def mark_interrupted(self) -> int:
        return await asyncio.to_thread(self._mark_interrupted_sync)

    def _mark_interrupted_sync(self) -> int:
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE admin_jobs
                    SET state = 'interrupted', finished_at = ?,
                        error_code = 'process_restarted',
                        error_message = '危险操作在进程重启时中断'
                    WHERE state IN ('queued', 'running', 'cancelling', 'scheduled')
                    """,
                    (now,),
                )
                affected = int(cursor.rowcount or 0)
                conn.execute(
                    "UPDATE admin_plans SET state = 'finished' WHERE job_id IN "
                    "(SELECT job_id FROM admin_jobs WHERE state = 'interrupted')"
                )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return affected

    async def prune(self, *, older_than_seconds: float = 7 * 86400) -> int:
        return await asyncio.to_thread(self._prune_sync, float(older_than_seconds))

    def _prune_sync(self, older_than_seconds: float) -> int:
        cutoff = time.time() - max(3600.0, older_than_seconds)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    DELETE FROM admin_jobs
                    WHERE finished_at IS NOT NULL AND finished_at < ?
                    """,
                    (cutoff,),
                )
                removed = int(cursor.rowcount or 0)
                conn.execute(
                    """
                    DELETE FROM admin_plans
                    WHERE created_at < ? AND state != 'executing'
                    """,
                    (cutoff,),
                )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return removed

    def _connect(self) -> sqlite3.Connection:
        if not self._ready:
            self._ensure_schema_sync()
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema_sync(self) -> None:
        if self._ready:
            return
        with self._init_lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=30)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_plans (
                        preview_id TEXT PRIMARY KEY,
                        action TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        generation TEXT NOT NULL,
                        token_hash TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        job_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_jobs (
                        job_id TEXT PRIMARY KEY,
                        preview_id TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        action TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        state TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        progress_json TEXT,
                        result_json TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        created_at REAL NOT NULL,
                        started_at REAL,
                        finished_at REAL,
                        cancel_requested INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_admin_jobs_created "
                    "ON admin_jobs(created_at DESC)"
                )
                conn.execute(f"PRAGMA user_version = {ADMIN_SCHEMA_VERSION}")
                conn.commit()
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._ready = True


def _dumps(value: Any) -> str:
    return orjson.dumps(value).decode("utf-8")


def _loads(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return orjson.loads(value)
    except (orjson.JSONDecodeError, TypeError):
        return default


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    plan_json = data.pop("plan_json", None)
    data["plan"] = _loads(plan_json, None) if plan_json else None
    progress_json = data.pop("progress_json", None)
    data["progress"] = _loads(progress_json, None) if progress_json else None
    result_json = data.pop("result_json", None)
    data["result"] = _loads(result_json, None) if result_json else None
    data["token_hash"] = data.get("token_hash", "")
    data["cancel_requested"] = bool(data.get("cancel_requested", False))
    return data


def token_fingerprint(token: str, *, preview_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(preview_id.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(token.encode("utf-8"))
    return digest.hexdigest()


__all__ = [
    "ACTIVE_JOB_STATES",
    "ADMIN_SCHEMA_VERSION",
    "TERMINAL_JOB_STATES",
    "AdminConflict",
    "AdminStore",
    "AdminStoreError",
    "token_fingerprint",
]
