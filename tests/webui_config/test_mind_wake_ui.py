"""Persona mind page wake-up controls contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def test_mind_page_wake_controls_and_api_are_wired():
    page = (JS / "pages/mind.js").read_text(encoding="utf-8")
    api = (JS / "api.js").read_text(encoding="utf-8")

    assert "endpoints.wakePersona" in page
    assert "wakePersona:" in api
    assert "/api/mind/wake" in api
    assert "唤醒" in page
    assert "叫醒留言" in page
    assert "reply_error" in page
    assert "只显示在人格后台" in page
    assert "sleeping" in page
    assert "collapsing" in page
