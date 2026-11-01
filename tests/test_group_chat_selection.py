"""Temporary group-only receive selection."""

from __future__ import annotations

import pytest

from core.group_chat_selection import (
    MAX_SELECTION_MINUTES,
    GroupChatSelection,
    build_group_chat_selection,
)
from tests.integration_pipeline.helpers import (
    RecordingPersonaAgent,
    _ai_no_action,
    _drain_pipeline,
    _msg,
)


def test_group_selection_pause_allows_mentions_but_not_plain_messages():
    selection = build_group_chat_selection(
        mode="pause",
        duration_minutes=30,
        reason="专注",
        now=1000.0,
    )

    assert selection.is_active(1001.0) is True
    assert selection.allows(5555, False, now=1001.0) is False
    assert selection.allows(5555, True, now=1001.0) is True
    assert selection.is_active(2801.0) is False
    assert selection.allows(5555, False, now=2801.0) is True


def test_group_selection_selected_keeps_only_listed_groups_and_all_mentions():
    selection = build_group_chat_selection(
        mode="selected",
        group_ids=[111, 222, 222, -1],
        duration_minutes=MAX_SELECTION_MINUTES,
        reason="只看两个群",
        now=1000.0,
    )

    assert selection.group_ids == (111, 222)
    assert selection.allows(111, False, now=1001.0) is True
    assert selection.allows(333, False, now=1001.0) is False
    assert selection.allows(333, True, now=1001.0) is True


def test_group_selection_validation_and_all_mode():
    assert build_group_chat_selection(mode="all", now=1000.0).mode == "all"
    with pytest.raises(ValueError, match="至少需要一个"):
        build_group_chat_selection(mode="selected", group_ids=[], now=1000.0)
    with pytest.raises(ValueError, match="1-1440"):
        build_group_chat_selection(mode="pause", duration_minutes=0, now=1000.0)
    with pytest.raises(ValueError):
        build_group_chat_selection(mode="unknown", now=1000.0)

    inactive = GroupChatSelection(mode="pause", until=999.0)
    assert inactive.snapshot(now=1000.0)["active"] is False
    assert inactive.allows(123, False, now=1000.0) is True


@pytest.mark.asyncio
async def test_pipeline_pause_drops_plain_group_but_keeps_mentions(build_pipeline):
    persona_agent = RecordingPersonaAgent()
    pipeline, provider, _, history, _ = await build_pipeline(
        [_ai_no_action(), _ai_no_action()],
        persona_agent=persona_agent,
    )
    pipeline.apply_group_chat_selection(
        mode="pause",
        duration_minutes=30,
        reason="暂时安静",
    )

    await pipeline.enqueue(
        _msg(group_id="5555", text="普通群聊", message_id="sel-1")
    )
    await _drain_pipeline(pipeline)
    assert provider.calls == []
    records = await history.records()
    assert not any("普通群聊" in str(record.get("content") or "") for record in records)

    await pipeline.enqueue(
        _msg(group_id="5555", text="@我 在吗", message_id="sel-2")
    )
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_pipeline_selected_groups_and_private_is_unaffected(build_pipeline):
    persona_agent = RecordingPersonaAgent()
    pipeline, provider, _, _, _ = await build_pipeline(
        [_ai_no_action(), _ai_no_action(), _ai_no_action()],
        persona_agent=persona_agent,
    )
    pipeline.apply_group_chat_selection(
        mode="selected",
        group_ids=[111],
        duration_minutes=30,
        reason="只看这个群",
    )

    await pipeline.enqueue(
        _msg(group_id="222", text="其他群普通消息", message_id="sel-3")
    )
    await _drain_pipeline(pipeline)
    assert provider.calls == []

    await pipeline.enqueue(
        _msg(group_id="111", text="目标群消息", message_id="sel-4")
    )
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 1

    await pipeline.enqueue(
        _msg(user_id="123", text="私聊不受影响", message_id="sel-5")
    )
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_chat_selection_tool_updates_pipeline_policy(build_pipeline):
    from tools import ToolContext
    from tools.control_tools import chat_selection
    from tools.schemas import ChatSelectionArgs

    pipeline, _, _, _, _ = await build_pipeline(
        [_ai_no_action()],
        persona_agent=RecordingPersonaAgent(),
    )
    ctx = ToolContext(chat_selection_cb=pipeline.apply_group_chat_selection)

    result = await chat_selection(
        ChatSelectionArgs(
            mode="selected",
            group_ids=[111],
            duration_minutes=15,
            reason="测试",
        ),
        ctx,
    )

    assert result["ok"] is True
    assert result["status"] == "updated"
    assert pipeline.group_chat_selection.mode == "selected"
    assert pipeline.group_chat_selection.group_ids == (111,)
    assert pipeline.group_chat_selection.allows(222, False) is False
    assert pipeline.group_chat_selection.allows(222, True) is True

    cleared = await chat_selection(ChatSelectionArgs(mode="all"), ctx)
    assert cleared["ok"] is True
    assert pipeline.group_chat_selection.is_active() is False


@pytest.mark.asyncio
async def test_chat_selection_tool_requires_callback():
    from tools import ToolContext
    from tools.control_tools import chat_selection
    from tools.schemas import ChatSelectionArgs

    result = await chat_selection(
        ChatSelectionArgs(mode="pause", duration_minutes=5, reason="test"),
        ToolContext(),
    )
    assert result["ok"] is False
    assert result["status"] == "unavailable"
