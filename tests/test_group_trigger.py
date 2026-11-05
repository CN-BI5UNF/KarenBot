"""Per-group @-trigger receive windows and the model window tool."""

from __future__ import annotations

import pytest

from app_config.schema import (
    GroupTriggerConfig,
    GroupTriggerRuleConfig,
)
from core.group_trigger import MAX_LLM_GROUPS, GroupTriggerManager
from tests.integration_pipeline.helpers import (
    RecordingPersonaAgent,
    _ai_no_action,
    _drain_pipeline,
    _msg,
)
from tools.base import ToolContext
from tools.control_tools import group_trigger_window
from tools.schemas import GroupTriggerWindowArgs


def _config(*rules: tuple[int, int, int]) -> GroupTriggerConfig:
    return GroupTriggerConfig(
        enabled=True,
        groups=[
            GroupTriggerRuleConfig(
                group_id=group_id,
                max_messages=max_messages,
                window_minutes=window_minutes,
            )
            for group_id, max_messages, window_minutes in rules
        ],
    )


def test_mention_opens_count_window_and_closes_at_limit():
    manager = GroupTriggerManager(_config((5555, 2, 0)))

    blocked = manager.on_inbound(5555, False, now=1000.0)
    assert blocked.allowed is False

    mention = manager.on_inbound(5555, True, now=1001.0)
    assert mention.allowed is True
    assert mention.opened is True
    assert mention.window["remaining_messages"] == 2

    first = manager.on_inbound(5555, False, now=1002.0)
    assert first.allowed is True
    assert first.window["remaining_messages"] == 1
    assert first.window["near_limit"] is True
    assert first.closed is False

    last = manager.on_inbound(5555, False, now=1003.0)
    assert last.allowed is True
    assert last.closed is True
    snapshot = manager.context_snapshot(5555, now=1004.0)
    assert snapshot["active"] is False
    assert snapshot["closed_after"] is True

    after = manager.on_inbound(5555, False, now=1005.0)
    assert after.allowed is False


def test_time_window_and_message_window_whichever_first():
    manager = GroupTriggerManager(_config((5555, 3, 10)))
    manager.on_inbound(5555, True, now=1000.0)

    assert manager.on_inbound(5555, False, now=1001.0).allowed is True
    assert manager.on_inbound(5555, False, now=1002.0).allowed is True
    assert manager.on_inbound(5555, False, now=1003.0).allowed is True
    assert manager.on_inbound(5555, False, now=1004.0).allowed is False

    manager.on_inbound(5555, True, now=2000.0)
    assert manager.on_inbound(5555, False, now=2599.0).allowed is True
    assert manager.on_inbound(5555, False, now=2601.0).allowed is False


def test_unlisted_groups_and_disabled_rules_keep_normal_receive():
    manager = GroupTriggerManager(_config((5555, 1, 0)))
    assert manager.on_inbound(6666, False, now=1000.0).allowed is True

    config = _config((5555, 1, 0))
    config.enabled = False
    manager.configure(config)
    assert manager.on_inbound(5555, False, now=1000.0).allowed is True
    assert manager.snapshots(now=1000.0) == []


def test_llm_window_limit_is_two_groups_and_extend_close_work():
    manager = GroupTriggerManager(_config((1, 0, 0), (2, 0, 0), (3, 0, 0)))
    opened = manager.open_llm_window([1, 2], duration_minutes=5, now=1000.0)
    assert opened["group_ids"] == [1, 2]
    assert manager.llm_owned_group_ids(now=1001.0) == {1, 2}

    with pytest.raises(ValueError, match="最多同时"):
        manager.open_llm_window([3], duration_minutes=5, now=1002.0)

    extended = manager.extend_llm_window([1], duration_minutes=15, now=1003.0)
    assert extended["windows"][0]["remaining_seconds"] == 15 * 60

    closed = manager.close_window([2], now=1004.0)
    assert closed["closed"] == [2]
    third = manager.open_llm_window([3], duration_minutes=5, now=1005.0)
    assert third["active_llm_groups"] == [1, 3]


def test_extend_requires_an_active_window_and_open_is_bounded():
    manager = GroupTriggerManager(_config((1, 1, 0), (2, 0, 0), (3, 0, 0)))
    with pytest.raises(ValueError, match="没有可延长的窗口"):
        manager.extend_llm_window([1], duration_minutes=5, now=1000.0)

    manager.on_inbound(1, True, now=1001.0)
    extended = manager.extend_llm_window([1], duration_minutes=5, now=1002.0)
    assert extended["windows"][0]["llm_owned"] is True
    assert manager.snapshot(1, now=1003.0)["remaining_messages"] is None

    with pytest.raises(ValueError, match="最多操作"):
        manager.apply_tool_action(
            action="open",
            group_ids=[1, 2, 3],
            duration_minutes=5,
            now=1004.0,
        )
    with pytest.raises(ValueError, match="未配置"):
        manager.open_llm_window([99], duration_minutes=5, now=1005.0)


def test_tool_defaults_to_current_group_and_reports_status():
    manager = GroupTriggerManager(_config((5555, 0, 0)))
    args = GroupTriggerWindowArgs(action="open", duration_minutes=7)
    ctx = ToolContext(
        group_trigger_cb=manager.apply_tool_action,
        extras={"current_group_id": 5555},
    )

    import asyncio

    result = asyncio.run(group_trigger_window(args, ctx))
    assert result["ok"] is True
    assert result["result"]["group_ids"] == [5555]
    assert manager.status(now=manager._windows[5555].until - 1)["windows"]

    close = asyncio.run(
        group_trigger_window(
            GroupTriggerWindowArgs(action="close"),
            ctx,
        )
    )
    assert close["ok"] is True
    assert close["result"]["closed"] == [5555]


@pytest.mark.asyncio
async def test_pipeline_filters_plain_messages_until_mention_window(build_pipeline):
    persona_agent = RecordingPersonaAgent()
    pipeline, provider, _, history, _ = await build_pipeline(
        [_ai_no_action(), _ai_no_action(), _ai_no_action()],
        persona_agent=persona_agent,
    )
    pipeline.apply_group_trigger_config(_config((5555, 2, 0)))

    await pipeline.enqueue(_msg(group_id="5555", text="普通消息 1", message_id="gt-1"))
    await _drain_pipeline(pipeline)
    assert provider.calls == []
    manager = pipeline.group_trigger
    assert manager.cached_count(5555) == 1
    assert manager.cached_messages([5555], limit=5)[0]["text"] == "普通消息 1"

    await pipeline.enqueue(_msg(group_id="5555", text="@我 在吗", message_id="gt-2"))
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 1
    task_context = pipeline._build_task_context("现在", "group:5555")
    assert "群聊接收窗口" in task_context

    await pipeline.enqueue(_msg(group_id="5555", text="普通消息 2", message_id="gt-3"))
    await _drain_pipeline(pipeline)
    await pipeline.enqueue(_msg(group_id="5555", text="普通消息 3", message_id="gt-4"))
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 3

    await pipeline.enqueue(_msg(group_id="5555", text="普通消息 4", message_id="gt-5"))
    await _drain_pipeline(pipeline)
    assert len(provider.calls) == 3
    records = await history.records()
    assert not any("普通消息 4" in str(record.get("content") or "") for record in records)

    manager = pipeline.group_trigger
    assert [
        item["text"] for item in manager.cached_messages([5555], limit=10)
    ] == ["普通消息 1", "普通消息 4"]
    assert manager.llm_owned_group_ids() == set()
    assert MAX_LLM_GROUPS == 2


def test_hot_rule_change_resets_only_changed_group_windows():
    manager = GroupTriggerManager(_config((1, 5, 0), (2, 5, 0)))
    manager.on_inbound(1, True, now=1000.0)
    manager.on_inbound(2, True, now=1000.0)

    manager.configure(_config((1, 10, 0), (2, 5, 0)))

    assert manager.snapshot(1, now=1001.0)["active"] is False
    assert manager.snapshot(2, now=1001.0)["active"] is True


def test_expired_llm_windows_release_capacity():
    manager = GroupTriggerManager(_config((1, 0, 0), (2, 0, 0), (3, 0, 0)))
    manager.open_llm_window([1, 2], duration_minutes=1, now=1000.0)

    assert manager.llm_owned_group_ids(now=2000.0) == set()
    reopened = manager.open_llm_window([3], duration_minutes=1, now=2000.0)
    assert reopened["active_llm_groups"] == [3]


def _cache_config(group_id: int, cache_messages: int) -> GroupTriggerConfig:
    return GroupTriggerConfig(
        enabled=True,
        groups=[
            GroupTriggerRuleConfig(
                group_id=group_id,
                cache_messages=cache_messages,
            )
        ],
    )


def _record(manager: GroupTriggerManager, group_id: int, text: str, now: float) -> None:
    allowed = manager.on_inbound(group_id, False, now=now).allowed
    assert allowed is False
    manager.record_filtered(
        group_id,
        message_id=f"m-{text}",
        user_id="42",
        nickname="群友",
        text=text,
        timestamp=now,
    )


def test_filtered_messages_are_cached_and_evicted_at_cap():
    manager = GroupTriggerManager(_cache_config(5555, 2))
    _record(manager, 5555, "第一条", 1000.0)
    _record(manager, 5555, "第二条", 1001.0)
    _record(manager, 5555, "第三条", 1002.0)

    cached = manager.cached_messages([5555], limit=10)
    assert [item["text"] for item in cached] == ["第二条", "第三条"]
    assert manager.cached_count(5555) == 2
    assert manager.snapshot(5555, now=1003.0)["cached_messages"] == 2


def test_cache_zero_disables_storage_and_config_shrink_trims():
    manager = GroupTriggerManager(_cache_config(5555, 2))
    _record(manager, 5555, "一", 1000.0)
    _record(manager, 5555, "二", 1001.0)

    manager.configure(_cache_config(5555, 1))
    assert [item["text"] for item in manager.cached_messages([5555], limit=10)] == ["二"]

    manager.configure(_cache_config(5555, 0))
    assert manager.cached_count(5555) == 0
    allowed = manager.on_inbound(5555, False, now=1002.0).allowed
    assert allowed is False
    assert manager.record_filtered(
        5555,
        message_id="m-三",
        user_id="42",
        nickname="群友",
        text="三",
        timestamp=1002.0,
    ) is False


def test_open_and_status_attach_llm_selected_history_limit():
    manager = GroupTriggerManager(_cache_config(5555, 50))
    for index in range(5):
        _record(manager, 5555, f"消息 {index}", 1000.0 + index)

    opened = manager.open_llm_window(
        [5555],
        duration_minutes=10,
        history_limit=2,
        now=1010.0,
    )
    assert opened["history_limit"] == 2
    assert [item["text"] for item in opened["recent_messages"]] == [
        "消息 3",
        "消息 4",
    ]

    status = manager.status([5555], history_limit=1, now=1011.0)
    assert [item["text"] for item in status["recent_messages"]] == ["消息 4"]
    assert status["rules"][0]["cache_messages"] == 50
    assert status["rules"][0]["cached_messages"] == 5

    no_history = manager.open_llm_window(
        [5555],
        duration_minutes=10,
        history_limit=0,
        now=1012.0,
    )
    assert no_history["recent_messages"] == []


def test_tool_attaches_history_and_reports_count():
    manager = GroupTriggerManager(_cache_config(5555, 50))
    _record(manager, 5555, "被过滤的旧消息", 1000.0)
    args = GroupTriggerWindowArgs(
        action="open",
        duration_minutes=7,
        history_limit=10,
    )
    ctx = ToolContext(
        group_trigger_cb=manager.apply_tool_action,
        extras={"current_group_id": 5555},
    )

    import asyncio

    result = asyncio.run(group_trigger_window(args, ctx))
    assert result["ok"] is True
    assert result["result"]["recent_messages"][0]["text"] == "被过滤的旧消息"
    assert "1 条被过滤消息" in result["brief"]
