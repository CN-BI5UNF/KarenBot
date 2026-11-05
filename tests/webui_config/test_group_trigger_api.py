"""Group @-trigger settings API and hot application."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_config.schema import GroupTriggerConfig, GroupTriggerRuleConfig
from core.group_trigger import GroupTriggerManager
from tests.integration_pipeline.helpers import _make_root_config
from webui.api import settings as settings_api


class FakePipeline:
    def __init__(self, manager: GroupTriggerManager) -> None:
        self.group_trigger = manager
        self.applied = None

    def apply_group_trigger_config(self, cfg):
        self.applied = cfg
        self.group_trigger.configure(cfg)


@pytest.fixture
def trigger_env():
    cfg = _make_root_config()
    cfg.features.group_trigger = GroupTriggerConfig(
        enabled=True,
        groups=[
            GroupTriggerRuleConfig(
                group_id=123,
                max_messages=5,
                window_minutes=10,
                cache_messages=25,
            )
        ],
    )
    pipeline = FakePipeline(GroupTriggerManager(cfg.features.group_trigger))
    rt = SimpleNamespace(config=cfg, pipeline=pipeline)
    saves = []
    host = SimpleNamespace(
        rt=rt,
        state="running",
        last_error=None,
        save_config=lambda: saves.append(True),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))
    return request, rt, pipeline, saves


@pytest.mark.asyncio
async def test_get_group_triggers_returns_rules_and_windows(trigger_env):
    request, rt, pipeline, _ = trigger_env
    pipeline.group_trigger.open_llm_window([123], duration_minutes=10)
    result = await settings_api.get_group_triggers(request)

    assert result["ok"] is True
    assert result["enabled"] is True
    assert result["groups"] == [
        {
            "group_id": 123,
            "max_messages": 5,
            "window_minutes": 10,
            "cache_messages": 25,
        }
    ]
    assert result["active_llm_groups"] == [123]
    assert result["active_windows"][0]["group_id"] == 123
    assert result["max_llm_groups"] == 2
    assert result["hot_applied"] is True


@pytest.mark.asyncio
async def test_put_group_triggers_saves_and_hot_applies(trigger_env):
    request, rt, pipeline, saves = trigger_env
    payload = GroupTriggerConfig(
        enabled=True,
        groups=[
            GroupTriggerRuleConfig(group_id=456, max_messages=0, window_minutes=30),
            GroupTriggerRuleConfig(group_id=789, max_messages=12, window_minutes=0),
        ],
    )

    result = await settings_api.put_group_triggers(request, payload)

    assert saves == [True]
    assert pipeline.applied is not None
    assert [rule.group_id for rule in rt.config.features.group_trigger.groups] == [
        456,
        789,
    ]
    assert result["needs_restart"] is False
    assert result["groups"] == [
        {
            "group_id": 456,
            "max_messages": 0,
            "window_minutes": 30,
            "cache_messages": 50,
        },
        {
            "group_id": 789,
            "max_messages": 12,
            "window_minutes": 0,
            "cache_messages": 50,
        },
    ]
    assert result["hot_applied"] is True
    assert "message" in result


@pytest.mark.asyncio
async def test_put_group_triggers_disabled_clears_runtime_windows(trigger_env):
    request, rt, pipeline, _ = trigger_env
    pipeline.group_trigger.open_llm_window([123], duration_minutes=10)
    payload = GroupTriggerConfig(enabled=False, groups=[])

    result = await settings_api.put_group_triggers(request, payload)

    assert rt.config.features.group_trigger.enabled is False
    assert result["active_windows"] == []
    assert result["enabled"] is False
