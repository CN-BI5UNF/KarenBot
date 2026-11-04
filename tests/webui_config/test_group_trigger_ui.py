"""Group @-trigger page contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def test_group_trigger_nav_page_and_api_are_wired():
    app = (JS / "app.js").read_text(encoding="utf-8")
    page = (JS / "pages/group_triggers.js").read_text(encoding="utf-8")
    api = (JS / "api.js").read_text(encoding="utf-8")

    assert "pages/group_triggers.js" in app
    assert "key: 'group_triggers'" in app
    assert "群聊触发" in app
    assert "endpoints.groupTriggers" in page
    assert "endpoints.saveGroupTriggers" in page
    assert "最多连续消息数" in page
    assert "时间窗口" in page
    assert "group_trigger_window" in page
    assert "最多同时覆盖 2 个群" in page
    assert "groupTriggers:" in api
    assert "saveGroupTriggers:" in api
    assert "/api/settings/group-triggers" in api
