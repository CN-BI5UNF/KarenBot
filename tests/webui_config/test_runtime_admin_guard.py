"""RuntimeHost admin lock and system API exclusion during destructive work."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webui.api import system as system_api
from webui.runtime_host import STATE_RUNNING, RuntimeHost


@pytest.mark.asyncio
async def test_pause_resume_admin_blocks_nested_start_and_restores(tmp_path):
    host = RuntimeHost(project_root=tmp_path)
    host.state = STATE_RUNNING
    host.rt = SimpleNamespace(shutdown=_async_noop)
    stopped = []
    started = []

    async def fake_stop():
        stopped.append(True)
        host.rt = None
        host.state = "stopped"

    async def fake_start(*, bypass_admin_guard=False):
        started.append(bypass_admin_guard)
        return True

    host.stop = fake_stop  # type: ignore[method-assign]
    host.start = fake_start  # type: ignore[method-assign]
    was_running = await host.pause_for_admin("persona_cleanup")
    assert was_running is True
    assert stopped == [True]
    assert host.admin_operation_active() is True
    assert await host.resume_after_admin() is True
    assert started == [True]
    assert host.admin_operation_active() is False


@pytest.mark.asyncio
async def test_start_is_rejected_while_admin_lock_is_held(tmp_path):
    host = RuntimeHost(project_root=tmp_path)
    host.begin_admin_operation("uninstall")
    ok = await host.start()
    assert ok is False
    assert "危险操作进行中" in host.last_error
    host.end_admin_operation()


@pytest.mark.asyncio
async def test_system_endpoints_refuse_admin_operations(monkeypatch):
    class FakeHost:
        def admin_operation_active(self):
            return True

        async def restart(self):
            raise AssertionError("must not restart")

        async def stop(self):
            raise AssertionError("must not stop")

        async def start(self):
            raise AssertionError("must not start")

        def request_stop(self):
            raise AssertionError("must not quit")

    host = FakeHost()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(host=host, hub=None, server=None))
    )
    for endpoint in (
        system_api.restart_runtime,
        system_api.stop_runtime,
        system_api.start_runtime,
        system_api.quit_app,
    ):
        with pytest.raises(HTTPException) as exc:
            await endpoint(request)
        assert exc.value.status_code == 409

    monkeypatch.setattr(system_api, "backend_restart_supported", lambda: True)
    with pytest.raises(HTTPException) as exc:
        await system_api.restart_backend(request)
    assert exc.value.status_code == 409


async def _async_noop():
    return None
