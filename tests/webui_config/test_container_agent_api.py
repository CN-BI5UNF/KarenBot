"""Container Agent mode install/activate API and WebUI contracts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from features.container import ContainerError
from tests.integration_pipeline.helpers import _make_root_config
from webui.api import container as container_api

ROOT = Path(__file__).resolve().parents[2]


def _key(path: str) -> str:
    text = str(path or "").strip()
    if text.startswith("/workspace/"):
        text = text[len("/workspace/") :]
    elif text == "/workspace":
        text = ""
    return text.lstrip("/")


class FakeAgentService:
    def __init__(self, *, data_root: Path | None = None) -> None:
        self.files: dict[str, str] = {}
        self.execs: list[str] = []
        self.copied: list[tuple[str, str, bool]] = []
        self.running = True
        self.state_calls = 0
        self.paths = (
            SimpleNamespace(data_root=data_root) if data_root is not None else None
        )

    async def container_state(self) -> str:
        self.state_calls += 1
        return "running" if self.running else "exited"

    async def read_file(self, path: str) -> dict:
        key = _key(path)
        if key not in self.files:
            raise ContainerError("读取容器文件失败", code="container_file_read_failed")
        return {"ok": True, "path": path, "content": self.files[key]}

    async def ensure_running(self) -> None:
        return None

    async def exec(self, command: str, *, timeout_seconds=None) -> dict:
        self.execs.append(command)
        if command.startswith("rm -rf "):
            prefix = _key(command.split()[2])
            self.files = {
                key: value
                for key, value in self.files.items()
                if key != prefix and not key.startswith(prefix + "/")
            }
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    async def copy_host_file(
        self,
        host_path,
        container_path: str,
        *,
        executable: bool = False,
    ) -> dict:
        self.copied.append((str(host_path), container_path, executable))
        return {"ok": True, "path": container_path, "bytes": 1}

    async def agent_helper(self, action, payload, *, timeout_seconds=60.0) -> dict:
        if action == "write":
            self.files[_key(payload["path"])] = str(payload.get("content") or "")
            return {"ok": True, "status": "done", "path": payload["path"]}
        return {"ok": False, "status": "failed", "error": action}


class FakeHost:
    def __init__(self, service: FakeAgentService, config) -> None:
        self.state = "running"
        self.last_error = ""
        self.rt = SimpleNamespace(container=service, config=config)
        self.saved = 0

    def save_config(self) -> None:
        self.saved += 1


def _request(host: FakeHost) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))


def _config():
    cfg = _make_root_config()
    cfg.features.container.enabled = True
    cfg.features.container.agent.active_mode = "off"
    return cfg


@pytest.mark.asyncio
async def test_status_lists_all_modes_without_container_start():
    service = FakeAgentService()
    host = FakeHost(service, _config())

    data = await container_api.container_agents(_request(host))

    assert service.state_calls == 1
    assert data["active"] == "off"
    assert {item["id"] for item in data["agents"]} == {"pi", "dsh", "claude_code"}
    assert all(item["installed"] is False for item in data["agents"])
    assert data["host"]["mode"] == "claude_code"
    assert data["host"]["execution_mode"] == "sandbox"
    assert data["host_runtime"]["sandbox_network"] is True


@pytest.mark.asyncio
async def test_install_activate_uninstall_flow():
    service = FakeAgentService()
    cfg = _config()
    host = FakeHost(service, cfg)

    installed = await container_api.container_agent_install(
        _request(host), "dsh"
    )
    assert installed["ok"] is True
    assert installed["mode"] == "dsh"
    assert ".karen-agents/dsh/manifest.json" in service.files
    status = {item["id"]: item for item in installed["status"]["agents"]}
    assert status["dsh"]["installed"] is True
    assert status["dsh"]["active"] is False

    activated = await container_api.container_agent_activate(
        _request(host), "dsh"
    )
    assert activated["ok"] is True
    assert cfg.features.container.agent.active_mode == "dsh"
    assert host.saved == 1
    status = {item["id"]: item for item in activated["status"]["agents"]}
    assert status["dsh"]["active"] is True

    with pytest.raises(HTTPException) as error:
        await container_api.container_agent_uninstall(_request(host), "dsh")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "agent_mode_active"

    deactivated = await container_api.container_agent_deactivate(_request(host))
    assert deactivated["active"] == "off"
    assert cfg.features.container.agent.active_mode == "off"

    removed = await container_api.container_agent_uninstall(_request(host), "dsh")
    assert removed["removed"] is True
    assert ".karen-agents/dsh/manifest.json" not in service.files
    status = {item["id"]: item for item in removed["status"]["agents"]}
    assert status["dsh"]["installed"] is False


@pytest.mark.asyncio
async def test_activate_requires_install_and_rejects_unknown_modes():
    service = FakeAgentService()
    host = FakeHost(service, _config())

    with pytest.raises(HTTPException) as missing:
        await container_api.container_agent_activate(_request(host), "pi")
    assert missing.value.status_code == 409
    assert missing.value.detail["code"] == "agent_mode_not_installed"

    with pytest.raises(HTTPException) as unknown:
        await container_api.container_agent_install(_request(host), "other")
    assert unknown.value.status_code == 400


@pytest.mark.asyncio
async def test_install_state_survives_stopped_container_and_rebuild(tmp_path):
    service = FakeAgentService(data_root=tmp_path)
    host = FakeHost(service, _config())

    await container_api.container_agent_install(_request(host), "pi")
    marker = tmp_path / "container_agents.json"
    assert marker.is_file()
    assert "pi" in json.loads(marker.read_text(encoding="utf-8"))

    service.running = False
    stopped = await container_api.container_agents(_request(host))
    status = {item["id"]: item for item in stopped["agents"]}
    assert status["pi"]["installed"] is True
    assert status["pi"]["version"]

    # A rebuilt container no longer has the manifest; the running probe must
    # discard the stale host marker instead of reporting a false install.
    service.running = True
    service.files.clear()
    rebuilt = await container_api.container_agents(_request(host))
    status = {item["id"]: item for item in rebuilt["agents"]}
    assert status["pi"]["installed"] is False
    assert "pi" not in json.loads(marker.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_host_execution_settings_are_validated_and_saved():
    service = FakeAgentService()
    cfg = _config()
    host = FakeHost(service, cfg)

    result = await container_api.container_agent_host(
        _request(host),
        container_api.AgentHostConfigPayload(
            execution_mode="host",
            sandbox_network=False,
        ),
    )
    assert result["ok"] is True
    assert cfg.features.container.agent.host_execution == "host"
    assert cfg.features.container.agent.sandbox_network is False
    assert result["status"]["host"]["execution_mode"] == "host"
    assert result["status"]["host"]["sandbox_network"] is False


def test_agent_card_and_api_contract_are_wired_in_webui():
    api_js = (ROOT / "webui/static/js/api.js").read_text(encoding="utf-8")
    page_js = (ROOT / "webui/static/js/pages/container.js").read_text(
        encoding="utf-8"
    )
    for endpoint in (
        "containerAgents",
        "installContainerAgent",
        "activateContainerAgent",
        "deactivateContainerAgent",
        "deleteContainerAgent",
        "saveContainerAgentHost",
    ):
        assert endpoint in api_js
    assert "/api/container/agents" in api_js
    assert "Agent 模式" in page_js
    assert "不启动" in page_js
    assert "仅向 KarenBot 的 LLM" in page_js
    assert "沙箱联网" in page_js
    assert "直接控制整台电脑" in page_js
