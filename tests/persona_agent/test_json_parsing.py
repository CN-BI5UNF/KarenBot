"""Persona updater JSON recovery from prose, fences, and reasoning output."""

from __future__ import annotations

from types import SimpleNamespace

from agents.persona.helpers import _parse_json_object
from agents.persona_agent import _parse_completion_json


def test_parse_json_object_handles_fences_and_leading_prose():
    assert _parse_json_object('说明 {"mood": 60} 以上') == {"mood": 60}
    assert _parse_json_object('```json\n{"mood_delta": -2}\n```') == {
        "mood_delta": -2
    }


def test_parse_json_object_skips_invalid_braces_before_real_object():
    text = '先想一个集合 {不是 JSON}，结果：\n{"mood": 70, "latest_monologue": "平静"}'
    assert _parse_json_object(text) == {
        "mood": 70,
        "latest_monologue": "平静",
    }


def test_parse_json_object_recovers_trailing_commas_outside_strings():
    text = '{"mood": 55, "effects": [{"name": "余韵", "intensity": 30},],}'
    assert _parse_json_object(text) == {
        "mood": 55,
        "effects": [{"name": "余韵", "intensity": 30}],
    }


def test_parse_json_object_does_not_rewrite_commas_inside_strings():
    text = '{"latest_monologue": "a,} b",}'
    assert _parse_json_object(text) == {"latest_monologue": "a,} b"}


def test_parse_completion_json_falls_back_to_reasoning_content():
    result = SimpleNamespace(content="", reasoning_content='{"mood": 42}')
    parsed, content_len, reasoning_len = _parse_completion_json(result)
    assert parsed == {"mood": 42}
    assert content_len == 0
    assert reasoning_len == len(result.reasoning_content)
