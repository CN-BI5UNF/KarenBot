"""Admin wake-up API for the persona mind page."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webui.api import mind as mind_api


class FakePersonaAgent:
    def __init__(self, current_action: str = "sleeping") -> None:
        self._snapshot = SimpleNamespace(
            current_action=current_action,
            energy=10.0,
            satiety=50.0,
            mood=50.0,
            social_need=50.0,
            action_until=None,
        )
        self.wake_calls: list[str] = []

    def get_state_snapshot(self):
        return self._snapshot

    def on_wakeup(self, reason: str):
        self.wake_calls.append(reason)
        self._snapshot = SimpleNamespace(
            **{
                **vars(self._snapshot),
                "current_action": "awake",
                "action_until": None,
            }
        )
        return self._snapshot


class FakePipeline:
    def __init__(self, reply: str = "唔……我醒了。", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def run_admin_wake_turn(self, *, admin_message: str = "", reason: str = ""):
        self.calls.append((admin_message, reason))
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.reply


def _env(
    *,
    current_action: str = "sleeping",
    pipeline=None,
    agent=None,
):
    agent = agent or FakePersonaAgent(current_action)
    pipeline = pipeline if pipeline is not None else FakePipeline()
    rt = SimpleNamespace(
        config=SimpleNamespace(
            persona_management=SimpleNamespace(enabled=True),
        ),
        persona_agent=agent,
        pipeline=pipeline,
    )
    host = SimpleNamespace(rt=rt, state="running", last_error=None)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(host=host)),
    )
    return request, agent, pipeline, rt


@pytest.mark.asyncio
async def test_wake_sleeping_persona_calls_on_wakeup_and_returns_dialogue():
    request, agent, pipeline, _ = _env()

    result = await mind_api.wake(
        request,
        mind_api.WakePayload(message="醒醒，有事找你", reason="admin_webui"),
    )

    assert result["ok"] is True
    assert result["reply"] == "唔……我醒了。"
    assert result["reply_error"] == ""
    assert result["state"]["current_action"] == "awake"
    assert agent.wake_calls == ["admin_webui"]
    assert pipeline.calls == [("醒醒，有事找你", "admin_webui")]


@pytest.mark.asyncio
async def test_wake_rejects_non_sleeping_persona():
    request, agent, pipeline, _ = _env(current_action="eating")

    with pytest.raises(HTTPException) as exc_info:
        await mind_api.wake(request, mind_api.WakePayload(message="起来"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["reason"] == "not_sleeping"
    assert agent.wake_calls == []
    assert pipeline.calls == []


@pytest.mark.asyncio
async def test_wake_keeps_awake_state_when_dialogue_generation_fails():
    request, agent, pipeline, _ = _env(pipeline=FakePipeline(fail=True))

    result = await mind_api.wake(request, mind_api.WakePayload())

    assert result["ok"] is True
    assert result["reply"] == ""
    assert result["reply_error"] == "wake_dialogue_failed"
    assert result["state"]["current_action"] == "awake"
    assert agent.wake_calls == ["admin_webui"]


@pytest.mark.asyncio
async def test_wake_reports_unavailable_pipeline_dialogue():
    request, _, _, _ = _env(pipeline=SimpleNamespace())

    result = await mind_api.wake(request, mind_api.WakePayload())

    assert result["ok"] is True
    assert result["reply_error"] == "wake_dialogue_unavailable"
