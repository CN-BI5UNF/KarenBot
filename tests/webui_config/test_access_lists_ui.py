"""Merged black/white list page contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def test_nav_and_page_merge_whitelist_and_blacklist():
    app = (JS / "app.js").read_text(encoding="utf-8")
    page = (JS / "pages/blacklist.js").read_text(encoding="utf-8")
    api = (JS / "api.js").read_text(encoding="utf-8")

    assert "title: '黑白名单'" in app
    assert "黑白名单" in page
    assert "白名单 QQ 号" in page
    assert "白名单群号" in page
    assert "拉黑的 QQ 号" in page
    assert "拉黑的群" in page
    assert "endpoints.accessLists" in page
    assert "endpoints.saveAccessLists" in page
    assert "accessLists:" in api
    assert "saveAccessLists:" in api
    assert "/api/settings/lists" in api


def test_whitelist_fields_were_removed_from_settings_spec():
    from webui.settings_spec import field_map

    fields = field_map()
    assert "adapters.default.whitelist.mode" not in fields
    assert "adapters.default.whitelist.qq_ids" not in fields
    assert "adapters.default.whitelist.group_ids" not in fields
