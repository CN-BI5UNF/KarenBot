"""Agent tool-schema profile: core tools plus ToolSearch lazy loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from features.coding_agent.state import AgentSessionState
from tests.integration_pipeline.helpers import _make_root_config
from tools import ToolContext, build_default_registry
from tools.toolsets import AGENT_CORE_TOOL_NAMES, ToolsetSession


def _registry(profile: str = "agent"):
    cfg = _make_root_config()
    cfg.behavior.tool_schema_profile = profile
    return build_default_registry(cfg)


def _names(schemas: list[dict]) -> set[str]:
    return {schema["function"]["name"] for schema in schemas}


def _context(tmp_path: Path, session: ToolsetSession) -> ToolContext:
    return ToolContext(
        conversation_id="private:1",
        workspace_dir=tmp_path,
        extras={
            "toolset_session": session,
            "agent_session": AgentSessionState(),
            "agent_container_mode": "off",
        },
    )


def test_agent_profile_only_exposes_core_tools_initially(tmp_path):
    reg = _registry()
    session = ToolsetSession()

    assert _names(reg.get_agent_schemas(session)) == set(AGENT_CORE_TOOL_NAMES)
    assert "agent_todo" not in _names(reg.get_agent_schemas(session))
    assert "list_toolsets" not in reg.names()
    assert "load_toolset" not in reg.names()
    assert reg.get_agent_schemas(session) is reg.get_agent_schemas(session)


@pytest.mark.asyncio
async def test_unloaded_tool_returns_need_tool_search_then_loads(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    ctx = _context(tmp_path, session)
    executor = reg.get_executor(ctx)
    (tmp_path / "note.txt").write_text("hello\n", encoding="utf-8")

    denied = await executor("agent_todo", {"todos": []})
    assert denied["ok"] is False
    assert denied["status"] == "need_tool_search"
    assert "agent_todo" in denied["next"]

    loaded = await executor("tool_search", {"select": ["agent_todo"]})
    assert loaded["ok"] is True
    assert loaded["added_tools"] == ["agent_todo"]
    assert "agent_todo" in _names(reg.get_agent_schemas(session))

    result = await executor(
        "agent_todo", {"todos": [{"content": "检查", "status": "pending"}]}
    )
    assert result["ok"] is True
    assert result["todos"][0]["content"] == "检查"


@pytest.mark.asyncio
async def test_query_discovery_does_not_load_tools(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    executor = reg.get_executor(_context(tmp_path, session))

    result = await executor("tool_search", {"query": "web"})
    assert result["ok"] is True
    assert result["status"] == "discovered"
    assert any(item["name"] == "web_search" for item in result["candidates"])
    assert session.loaded_tool_ids() == []
    assert "web_search" not in _names(reg.get_agent_schemas(session))


@pytest.mark.asyncio
async def test_agent_sessions_are_isolated(tmp_path):
    reg = _registry()
    first = ToolsetSession()
    second = ToolsetSession()
    first_executor = reg.get_executor(_context(tmp_path, first))
    second_executor = reg.get_executor(_context(tmp_path, second))

    await first_executor("tool_search", {"select": ["agent_todo"]})

    assert "agent_todo" in _names(reg.get_agent_schemas(first))
    assert "agent_todo" not in _names(reg.get_agent_schemas(second))
    denied = await second_executor("agent_todo", {"todos": []})
    assert denied["status"] == "need_tool_search"


@pytest.mark.asyncio
async def test_plan_mode_blocks_writes_until_plan_is_submitted(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    ctx = _context(tmp_path, session)
    executor = reg.get_executor(ctx)

    await executor(
        "tool_search",
        {"select": ["agent_enter_plan", "agent_exit_plan"]},
    )
    entered = await executor("agent_enter_plan", {})
    assert entered["status"] == "plan_mode"

    blocked = await executor(
        "agent_write",
        {"path": "x.txt", "content": "x", "target": "host"},
    )
    assert blocked["ok"] is False
    assert blocked["code"] == "agent_plan_mode_denied"

    submitted = await executor("agent_exit_plan", {"plan": "# Plan\nDo it."})
    assert submitted["ok"] is True
    assert submitted["plan"] == "# Plan\nDo it."
    written = await executor(
        "agent_write",
        {"path": "x.txt", "content": "x", "target": "host"},
    )
    assert written["ok"] is True


@pytest.mark.asyncio
async def test_agent_notebook_edit_roundtrip(tmp_path):
    import json

    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "# Title\n"},
            {
                "cell_type": "code",
                "metadata": {},
                "source": "print(1)\n",
                "execution_count": None,
                "outputs": [],
                "id": "cell-1",
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(
        json.dumps(notebook), encoding="utf-8"
    )
    reg = _registry()
    session = ToolsetSession()
    executor = reg.get_executor(_context(tmp_path, session))
    await executor("tool_search", {"select": ["agent_notebook_edit"]})

    inserted = await executor(
        "agent_notebook_edit",
        {
            "path": "analysis.ipynb",
            "edit_mode": "insert",
            "cell_index": 0,
            "cell_type": "markdown",
            "new_source": "inserted\n",
            "target": "host",
        },
    )
    assert inserted["ok"] is True
    assert inserted["cell_index"] == 1

    replaced = await executor(
        "agent_notebook_edit",
        {
            "path": "analysis.ipynb",
            "edit_mode": "replace",
            "cell_id": "cell-1",
            "new_source": "print(2)\n",
            "target": "host",
        },
    )
    assert replaced["ok"] is True
    assert replaced["cell_index"] == 2

    deleted = await executor(
        "agent_notebook_edit",
        {
            "path": "analysis.ipynb",
            "edit_mode": "delete",
            "cell_index": 1,
            "target": "host",
        },
    )
    assert deleted["ok"] is True
    updated = json.loads((tmp_path / "analysis.ipynb").read_text(encoding="utf-8"))
    assert len(updated["cells"]) == 2
    assert updated["cells"][1]["source"] == "print(2)\n"


@pytest.mark.asyncio
async def test_agent_spawn_uses_real_subagent_callback(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    calls: list[dict] = []

    async def fake_task(payload):
        calls.append(payload)
        return {
            "ok": True,
            "status": "completed",
            "task_id": "agent-test",
            "result_file": "agent_tasks/agent-test/agent-spawn.md",
            "content": "子 Agent 结果",
        }

    ctx = _context(tmp_path, session)
    ctx.agent_task_cb = fake_task
    executor = reg.get_executor(ctx)
    await executor("tool_search", {"select": ["agent_spawn"]})

    result = await executor(
        "agent_spawn",
        {
            "prompt": "检查代码",
            "context": "只读",
            "max_loops": 4,
            "target": "host",
        },
    )
    assert result["ok"] is True
    assert result["task_id"] == "agent-test"
    assert calls == [
        {
            "prompt": "检查代码",
            "sources": [{"type": "inline_text", "value": "只读"}],
            "output_format": "markdown",
            "output_name": "agent-spawn.md",
            "max_loops": 4,
            "coding_target": "host",
        }
    ]


@pytest.mark.asyncio
async def test_agent_spawn_rejects_modes_without_spawn(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    ctx = _context(tmp_path, session)
    ctx.container = object()
    ctx.extras["agent_container_mode"] = "pi"
    ctx.agent_task_cb = _unreachable_task
    executor = reg.get_executor(ctx)
    await executor("tool_search", {"select": ["agent_spawn"]})

    result = await executor(
        "agent_spawn",
        {"prompt": "检查代码", "target": "container"},
    )
    assert result["ok"] is False
    assert result["code"] == "agent_mode_unsupported"


async def _unreachable_task(payload):
    raise AssertionError(f"callback should not run: {payload}")


@pytest.mark.asyncio
async def test_compact_profile_keeps_coding_state_across_turns(tmp_path):
    reg = _registry("compact")
    session = ToolsetSession()
    ctx = _context(tmp_path, session)
    executor = reg.get_executor(ctx)

    unlocked = await executor("tool_search", {"tool_name": "agent_todo"})
    assert unlocked["ok"] is True
    assert "load_toolset" not in unlocked.get("next", "")
    updated = await executor(
        "agent_todo",
        {"todos": [{"content": "检查", "status": "completed"}]},
    )
    assert updated["ok"] is True

    unlocked_plan = await executor("tool_search", {"tool_name": "agent_enter_plan"})
    assert unlocked_plan["ok"] is True
    entered = await executor("agent_enter_plan", {})
    assert entered["status"] == "plan_mode"


def test_agent_and_routed_profiles_accept_tool_schema_config():
    from app_config.schema import BehaviorConfig

    assert BehaviorConfig(tool_schema_profile="agent").tool_schema_profile == "agent"


@pytest.mark.asyncio
async def test_custom_tools_require_container_pi_or_dsh(tmp_path):
    reg = _registry()
    session = ToolsetSession()
    ctx = _context(tmp_path, session)
    executor = reg.get_executor(ctx)
    await executor(
        "tool_search",
        {"select": ["agent_tool_create", "agent_tool_list", "agent_tool_run"]},
    )

    host = await executor(
        "agent_tool_create",
        {"name": "demo", "code": "print(1)\n", "target": "host"},
    )
    assert host["ok"] is False
    assert host["code"] == "agent_custom_tools_host_unsupported"

    container = await executor(
        "agent_tool_create",
        {"name": "demo", "code": "print(1)\n", "target": "container"},
    )
    assert container["ok"] is False
    assert container["code"] == "agent_container_unavailable"

    ctx.container = object()
    ctx.extras["agent_container_mode"] = "claude_code"
    unsupported = await executor("agent_tool_list", {"target": "container"})
    assert unsupported["ok"] is False
    assert unsupported["code"] == "agent_custom_tools_unsupported"
