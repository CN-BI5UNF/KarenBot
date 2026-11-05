"""Wakeup turn integration pipeline tests."""

from __future__ import annotations

import json

import pytest

from providers.base import CompletionResult, ToolCall
from tests.integration_pipeline.helpers import (
    RecordingPersonaAgent,
    _ai_no_action,
    _ai_send_private,
    _ai_tool_search,
)


@pytest.mark.asyncio

async def test_wakeup_turn_uses_user_event_and_denies_long_running_tools(build_pipeline):

    pipeline, provider, adapter, _, _ = await build_pipeline([_ai_no_action()])

    await pipeline.run_wakeup_turn(

        "30 秒到了，请发送消息。",

        target={"target_type": "private", "target_id": 123},

        mode="wakeup",

    )

    assert len(provider.calls) == 1

    names = {

        schema["function"]["name"]

        for schema in provider.calls[0]["tools"]

    }

    assert "schedule_wakeup" in names

    assert "start_agent_task" in names

    assert "summarize_chat_history" in names

    assert "summarize_conversation" in names

    messages = provider.calls[0]["messages"]

    assert messages[-1]["role"] == "user"

    assert "[系统事件 · 非用户消息]" in messages[-1]["content"]

    assert "定时唤醒已到" in messages[-1]["content"]

@pytest.mark.asyncio

async def test_wakeup_turn_denies_long_running_tool_execution(build_pipeline):

    start_args = {

        "prompt": "整理资料",

        "sources": [{"type": "inline_text", "value": "资料"}],

        "output_format": "markdown",

    }

    pipeline, provider, _, _, _ = await build_pipeline(

        [

            _ai_tool_search("start_agent_task"),

            CompletionResult(

                tool_calls=[

                    ToolCall(

                        id="tc-start-denied",

                        name="start_agent_task",

                        arguments=json.dumps(start_args),

                    )

                ],

                finish_reason="tool_calls",

            ),

            _ai_no_action(),

        ]

    )

    await pipeline.run_wakeup_turn(

        "30 秒到了，请处理提醒。",

        target={"target_type": "private", "target_id": 123},

        mode="wakeup",

    )

    assert len(provider.calls) == 3

    third_messages = provider.calls[2]["messages"]

    denied_records = [

        json.loads(str(message.get("content") or "{}"))

        for message in third_messages

        if message.get("role") == "tool"

        and "tc-start-denied" == message.get("tool_call_id")

    ]

    assert denied_records

    assert denied_records[-1]["status"] == "denied"

@pytest.mark.asyncio
async def test_admin_wake_turn_returns_webui_reply_and_records_system_note(
    build_pipeline,
):
    persona_agent = RecordingPersonaAgent()
    pipeline, provider, adapter, history, _ = await build_pipeline(
        [CompletionResult(content="唔……我醒了，怎么了？", finish_reason="stop")],
        persona_agent=persona_agent,
    )

    reply = await pipeline.run_admin_wake_turn(
        admin_message="醒醒，有事找你",
        reason="admin_webui",
    )

    assert reply == "唔……我醒了，怎么了？"
    assert adapter.sent == []
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert messages[-1]["role"] == "user"
    assert "管理员在 WebUI 点击了“唤醒”" in messages[-1]["content"]
    assert "醒醒，有事找你" in messages[-1]["content"]
    records = await history.records()
    assert any(
        record.get("role") == "system"
        and "管理员从 WebUI 将你唤醒" in str(record.get("content") or "")
        for record in records
    )


@pytest.mark.asyncio
async def test_admin_wake_turn_denies_outbound_qq_tools(build_pipeline):
    persona_agent = RecordingPersonaAgent()
    pipeline, _, adapter, _, _ = await build_pipeline(
        [
            _ai_send_private(target_qq="123", content="不应发出的消息"),
            CompletionResult(content="我醒了。", finish_reason="stop"),
        ],
        persona_agent=persona_agent,
    )

    reply = await pipeline.run_admin_wake_turn(admin_message="醒醒")

    assert reply == "我醒了。"
    assert adapter.sent == []


@pytest.mark.asyncio
async def test_admin_wake_turn_uses_fallback_when_model_does_not_reply(
    build_pipeline,
):
    persona_agent = RecordingPersonaAgent()
    pipeline, _, adapter, _, _ = await build_pipeline(
        [_ai_no_action()],
        persona_agent=persona_agent,
    )

    reply = await pipeline.run_admin_wake_turn()

    assert reply == "唔……我醒了。怎么了？"
    assert adapter.sent == []
