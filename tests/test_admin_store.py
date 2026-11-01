"""Persisted previews/jobs for destructive admin operations."""

from __future__ import annotations

import time

import pytest

from memory.admin_store import (
    AdminConflict,
    AdminStore,
    token_fingerprint,
)


def _plan(**overrides):
    now = time.time()
    data = {
        "preview_id": "prev_test_12345678",
        "action": "persona_cleanup",
        "subject": "小堡",
        "created_at": now,
        "expires_at": now + 300,
        "generation": "a" * 64,
        "token_hash": token_fingerprint("token-value-123", preview_id="prev_test_12345678"),
        "plan": {"persona": "小堡", "targets": ["memory", "vector"]},
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_create_plan_and_job_requires_ready_plan(tmp_path):
    store = AdminStore(tmp_path / "admin.sqlite3")
    await store.initialize()
    await store.create_plan(**_plan())
    plan = await store.get_plan("prev_test_12345678")
    assert plan is not None
    assert plan["plan"]["persona"] == "小堡"
    assert plan["state"] == "ready"

    job, created = await store.create_job(
        job_id="job_1",
        preview_id="prev_test_12345678",
        idempotency_key="idem_1",
        action="persona_cleanup",
        subject="小堡",
    )
    assert created is True
    assert job["state"] == "queued"
    plan = await store.get_plan("prev_test_12345678")
    assert plan["state"] == "executing"
    assert plan["job_id"] == "job_1"

    same, created_again = await store.create_job(
        job_id="job_2",
        preview_id="prev_test_12345678",
        idempotency_key="idem_1",
        action="persona_cleanup",
        subject="小堡",
    )
    assert created_again is False
    assert same["job_id"] == "job_1"

    with pytest.raises(AdminConflict, match="idempotency_conflict"):
        await store.create_job(
            job_id="job_3",
            preview_id="prev_test_12345678",
            idempotency_key="idem_1",
            action="persona_cleanup",
            subject="other",
        )


@pytest.mark.asyncio
async def test_active_job_blocks_second_job_and_cancel_interrupt(tmp_path):
    first = _plan()
    second = _plan(
        preview_id="prev_other_12345678",
        subject="deepseek",
        token_hash=token_fingerprint(
            "other-token-123", preview_id="prev_other_12345678"
        ),
    )
    store = AdminStore(tmp_path / "admin.sqlite3")
    await store.initialize()
    await store.create_plan(**first)
    await store.create_plan(**second)
    await store.create_job(
        job_id="job_1",
        preview_id=first["preview_id"],
        idempotency_key="idem_1",
        action=first["action"],
        subject=first["subject"],
    )
    with pytest.raises(AdminConflict, match="operation_in_progress"):
        await store.create_job(
            job_id="job_2",
            preview_id=second["preview_id"],
            idempotency_key="idem_2",
            action=second["action"],
            subject=second["subject"],
        )

    assert await store.active_job() is not None
    assert await store.request_cancel("job_1") is True
    assert await store.is_cancel_requested("job_1") is True
    await store.update_job(
        "job_1",
        state="running",
        phase="deleting_memory",
        progress={"bytes_done": 10},
    )
    job = await store.get_job("job_1")
    assert job["phase"] == "deleting_memory"
    assert job["progress"]["bytes_done"] == 10

    await store.update_job(
        "job_1",
        state="completed",
        phase="completed",
        result={"ok": True},
        finished=True,
    )
    assert await store.active_job() is None
    assert (await store.get_job("job_1"))["result"]["ok"] is True


@pytest.mark.asyncio
async def test_expired_preview_and_interrupted_marking(tmp_path):
    store = AdminStore(tmp_path / "admin.sqlite3")
    await store.initialize()
    await store.create_plan(**_plan(expires_at=time.time() - 1))
    with pytest.raises(AdminConflict, match="preview_expired"):
        await store.create_job(
            job_id="job_exp",
            preview_id="prev_test_12345678",
            idempotency_key="idem_exp",
            action="persona_cleanup",
            subject="小堡",
        )

    await store.create_plan(**_plan(preview_id="prev_live_12345678"))
    await store.create_job(
        job_id="job_live",
        preview_id="prev_live_12345678",
        idempotency_key="idem_live",
        action="persona_cleanup",
        subject="小堡",
    )
    assert await store.mark_interrupted() == 1
    job = await store.get_job("job_live")
    assert job["state"] == "interrupted"
    assert job["error_code"] == "process_restarted"


@pytest.mark.asyncio
async def test_startup_marks_abandoned_jobs_only_once(tmp_path):
    store = AdminStore(tmp_path / "admin.sqlite3")
    await store.startup()
    await store.create_plan(**_plan())
    await store.create_job(
        job_id="job_startup",
        preview_id="prev_test_12345678",
        idempotency_key="idem_startup",
        action="persona_cleanup",
        subject="小堡",
    )
    await store.startup()
    job = await store.get_job("job_startup")
    assert job["state"] == "queued"


def test_token_fingerprint_is_stable_and_preview_scoped():
    a = token_fingerprint("token", preview_id="p1")
    b = token_fingerprint("token", preview_id="p1")
    c = token_fingerprint("token", preview_id="p2")
    assert a == b
    assert a != c
    assert "token" not in a
