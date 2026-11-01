"""Persona appearance UI and API client contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def test_personas_page_offers_read_only_appearance_upload():
    page = (JS / "pages/personas.js").read_text(encoding="utf-8")
    api = (JS / "api.js").read_text(encoding="utf-8")
    css = (ROOT / "webui/static/app.css").read_text(encoding="utf-8")

    assert "角色形象" in page
    assert "openAppearance" in page
    assert "personaAppearanceUrl" in page
    assert "uploadPersonaAppearance" in page
    assert "setPersonaAppearanceCover" in page
    assert "deletePersonaAppearanceImage" in page
    assert "deletePersonaAppearance" in page
    assert "multiple: true" in page
    assert "设为预览" in page
    assert "只读知识条目" in page
    assert "persona-thumb" in page and ".persona-thumb" in css
    assert "personaAppearanceUrl:" in api
    assert "/appearance/file" in api
    assert "image_id" in api
    assert "/cover" in api
    assert "uploadPersonaAppearance:" in api
    assert "setPersonaAppearanceCover:" in api
    assert "deletePersonaAppearanceImage:" in api
