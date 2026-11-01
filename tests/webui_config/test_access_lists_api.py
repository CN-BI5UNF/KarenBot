"""Unified black/white list API and hot application."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_config.schema import BlacklistConfig, WhitelistConfig
from webui.api import settings as settings_api


class FakePipeline:
    def __init__(self) -> None:
        self.whitelist = None
        self.blacklist = None
        self._whitelist_qq_ids = {11}
        self._whitelist_group_ids = {22}
        self._blacklist_qq_ids = {33}
        self._blacklist_group_ids = {44}

    def apply_whitelist(self, cfg):
        self.whitelist = cfg
        self._whitelist_qq_ids = set(cfg.qq_ids)
        self._whitelist_group_ids = set(cfg.group_ids)

    def apply_blacklist(self, cfg):
        self.blacklist = cfg
        self._blacklist_qq_ids = set(cfg.qq_ids) if cfg.enabled else set()
        self._blacklist_group_ids = set(cfg.group_ids) if cfg.enabled else set()


@pytest.fixture
def lists_env():
    adapter = SimpleNamespace(
        whitelist=WhitelistConfig(mode="verify", qq_ids=[1], group_ids=[2]),
        blacklist=BlacklistConfig(enabled=True, qq_ids=[3], group_ids=[4]),
    )
    rt = SimpleNamespace(
        config=SimpleNamespace(adapters={"default": adapter}),
        pipeline=FakePipeline(),
    )
    host = SimpleNamespace(
        rt=rt,
        state="running",
        last_error=None,
        save_config=lambda: None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))
    return request, rt, adapter


@pytest.mark.asyncio
async def test_get_lists_returns_both_sides_and_active_sets(lists_env):
    request, rt, _adapter = lists_env
    result = await settings_api.get_lists(request)

    assert result["whitelist"]["mode"] == "verify"
    assert result["whitelist"]["qq_ids"] == [1]
    assert result["whitelist"]["active_qq_ids"] == [11]
    assert result["blacklist"]["enabled"] is True
    assert result["blacklist"]["active_group_ids"] == [44]
    assert result["hot_applied"] is True


@pytest.mark.asyncio
async def test_put_lists_updates_config_and_uses_hot_apply(lists_env):
    request, rt, adapter = lists_env
    payload = settings_api.ListsPayload(
        whitelist=settings_api.WhitelistPayload(
            mode="whitelist",
            qq_ids=[10001, 10001, -1],
            group_ids=[20002],
        ),
        blacklist=settings_api.BlacklistPayload(
            enabled=False,
            qq_ids=[30003],
            group_ids=[40004],
        ),
    )

    result = await settings_api.put_lists(request, payload)

    assert adapter.whitelist.mode == "whitelist"
    assert adapter.whitelist.qq_ids == [10001]
    assert adapter.whitelist.group_ids == [20002]
    assert adapter.blacklist.enabled is False
    assert adapter.blacklist.qq_ids == [30003]
    assert rt.pipeline.whitelist.qq_ids == [10001]
    assert rt.pipeline.blacklist.group_ids == [40004]
    assert rt.pipeline._blacklist_qq_ids == set()
    assert result["ok"] is True
    assert result["needs_restart"] is False
    assert result["whitelist"]["mode"] == "whitelist"
