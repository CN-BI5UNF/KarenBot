"""Admin API contracts and server-side destructive confirmation gates."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.destructive_admin import DestructiveAdminError
from webui.api import admin as admin_api


def _request(host=None):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(host=host or SimpleNamespace())),
    )


class FakePersonaService:
    def __init__(self):
        self.calls = []

    async def preview(self, name):
        self.calls.append(("preview", name))
        return {
            "ok": True,
            "action": "persona_cleanup",
            "persona": name,
            "preview_id": "prev_12345678",
            "confirmation_token": "token-1234567890",
            "generation": "a" * 64,
            "confirmation_phrase": f"删除 {name} 的运行数据",
            "expected_bytes": 12,
        }

    async def execute(self, name, **kwargs):
        self.calls.append(("execute", name, kwargs))
        return {
            "job_id": "job_1",
            "action": "persona_cleanup",
            "subject": name,
            "state": "queued",
            "phase": "queued",
        }, True

    async def get_job(self, job_id):
        if job_id == "missing":
            return None
        return {"job_id": job_id, "state": "completed", "phase": "completed"}

    async def list_jobs(self, limit=20):
        return [{"job_id": "job_1", "state": "completed", "phase": "completed"}]

    async def cancel(self, job_id):
        return {"ok": True, "job_id": job_id}


class FakeUninstallService:
    async def preview(self):
        return {
            "ok": True,
            "action": "uninstall",
            "supported": True,
            "preview_id": "prev_uninstall",
            "confirmation_token": "token-1234567890",
            "generation": "b" * 64,
            "confirmation_phrase": "永久卸载 KarenBot",
            "targets": [],
        }

    async def execute(self, **kwargs):
        return {
            "job_id": "job_uninstall",
            "action": "uninstall",
            "state": "queued",
            "phase": "queued",
            "audit_path": "/tmp/audit.json",
        }, True


def _host_with_services():
    host = SimpleNamespace(
        _admin_services=(FakePersonaService(), FakeUninstallService()),
        build_paths=lambda: None,
    )
    return host


@pytest.mark.asyncio
async def test_persona_preview_execute_and_jobs():
    host = _host_with_services()
    request = _request(host)
    preview = await admin_api.persona_cleanup_preview(request, "小堡")
    assert preview["persona"] == "小堡"
    assert "confirmation_token" in preview

    payload = admin_api.PersonaCleanupExecutePayload(
        preview_id="prev_12345678",
        confirmation_token="token-1234567890",
        expected_generation="a" * 64,
        idempotency_key="idem-12345678",
        typed_confirmation="删除 小堡 的运行数据",
        acknowledge_destructive=True,
        create_backup=True,
    )
    response = await admin_api.persona_cleanup_execute(request, "小堡", payload)
    assert response.status_code == 202
    body = json.loads(response.body)
    assert body["job_id"] == "job_1"
    assert body["created"] is True

    job = await admin_api.get_job(request, "job_1")
    assert job["state"] == "completed"
    jobs = await admin_api.list_jobs(request, 20)
    assert jobs["jobs"][0]["job_id"] == "job_1"
    with pytest.raises(HTTPException) as exc:
        await admin_api.get_job(request, "missing")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_uninstall_preview_and_execute():
    request = _request(_host_with_services())
    preview = await admin_api.uninstall_preview(request)
    assert preview["action"] == "uninstall"
    payload = admin_api.UninstallExecutePayload(
        preview_id="prev_uninstall",
        confirmation_token="token-1234567890",
        expected_generation="b" * 64,
        idempotency_key="idem-uninstall",
        typed_confirmation="永久卸载 KarenBot",
        acknowledge_destructive=True,
        create_backup=False,
    )
    response = await admin_api.uninstall_execute(request, payload)
    assert response.status_code == 202
    body = json.loads(response.body)
    assert body["job_id"] == "job_uninstall"
    assert body["audit_path"] == "/tmp/audit.json"


def test_admin_header_and_origin_are_required():
    request = SimpleNamespace(headers={})
    with pytest.raises(HTTPException) as exc:
        admin_api.require_admin_request(request)
    assert exc.value.status_code == 403

    cross = SimpleNamespace(
        headers={
            "x-karen-admin": "1",
            "origin": "https://evil.example",
            "host": "127.0.0.1:8000",
        }
    )
    with pytest.raises(HTTPException) as exc:
        admin_api.require_admin_request(cross)
    assert exc.value.detail["code"] == "origin_mismatch"

    same = SimpleNamespace(
        headers={
            "x-karen-admin": "1",
            "origin": "http://127.0.0.1:8000",
            "host": "127.0.0.1:8000",
            "sec-fetch-site": "same-origin",
        }
    )
    assert admin_api.require_admin_request(same) is None


def test_admin_router_is_registered():
    from webui.api import ALL_ROUTERS

    assert admin_api.router in ALL_ROUTERS


def test_error_mapping_uses_machine_codes():
    exc = DestructiveAdminError("generation_conflict", "changed")
    mapped = admin_api._http_error(exc)
    assert mapped.status_code == 409
    assert mapped.detail["code"] == "generation_conflict"

    expired = admin_api._http_error(
        DestructiveAdminError("preview_expired", "expired")
    )
    assert expired.status_code == 410
