"""Routed tool schema profile in the real pipeline loop."""

from __future__ import annotations

import pytest

from tests.integration_pipeline.helpers import (
    RecordingPersonaAgent,
    _ai_load_toolset,
    _ai_no_action,
    _drain_pipeline,
    _msg,
)


def _tool_names(call: dict) -> set[str]:
    return {
        item["function"]["name"]
        for item in (call.get("tools") or [])
        if isinstance(item, dict)
    }


@pytest.mark.asyncio
async def test_routed_pipeline_adds_loaded_toolset_on_next_model_request(build_pipeline):
    pipeline, provider, _, _, _ = await build_pipeline(
        [_ai_load_toolset("workspace"), _ai_no_action(), _ai_no_action()],
        persona_agent=RecordingPersonaAgent(),
        tool_schema_profile="routed",
    )

    await pipeline.enqueue(_msg(user_id="123", text="先加载文件工具", message_id="route-1"))
    await _drain_pipeline(pipeline)

    assert len(provider.calls) == 2
    first_tools = _tool_names(provider.calls[0])
    second_tools = _tool_names(provider.calls[1])
    assert "load_toolset" in first_tools
    assert "read_file" not in first_tools
    assert "read_file" in second_tools
    assert "write_file" in second_tools

    # Loaded toolset is per conversation and survives into the next turn.
    await pipeline.enqueue(_msg(user_id="123", text="继续", message_id="route-2"))
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 3
    assert "read_file" in _tool_names(provider.calls[2])


@pytest.mark.asyncio
async def test_routed_toolsets_are_isolated_by_conversation(build_pipeline):
    pipeline, provider, _, _, _ = await build_pipeline(
        [_ai_load_toolset("workspace"), _ai_no_action(), _ai_no_action()],
        persona_agent=RecordingPersonaAgent(),
        tool_schema_profile="routed",
    )

    await pipeline.enqueue(
        _msg(group_id="111", text="加载文件工具", message_id="route-g1")
    )
    await _drain_pipeline(pipeline)
    assert "read_file" in _tool_names(provider.calls[1])

    await pipeline.enqueue(
        _msg(group_id="222", text="另一个群", message_id="route-g2")
    )
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 3
    assert "read_file" not in _tool_names(provider.calls[2])


@pytest.mark.asyncio
async def test_default_compact_profile_still_exposes_all_stub_tools(build_pipeline):
    pipeline, provider, _, _, _ = await build_pipeline(
        [_ai_no_action()],
        persona_agent=RecordingPersonaAgent(),
        tool_schema_profile="compact",
    )

    await pipeline.enqueue(_msg(user_id="123", text="普通消息", message_id="route-c1"))
    await _drain_pipeline(pipeline)

    tools = _tool_names(provider.calls[0])
    assert "load_toolset" not in tools
    assert "read_file" in tools  # compact profile exposes a stub entry
    assert pipeline._tool_routing_enabled() is False
