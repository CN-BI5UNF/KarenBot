"""Static contracts for the destructive admin UI."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


def test_persona_cleanup_button_and_warning_modal_contract():
    personas = _read("pages/personas.js")
    destructive = _read("destructive_admin.js")
    assert "openPersonaCleanup" in personas
    assert "清理运行数据" in personas
    assert "删除人格定义" in personas
    assert "openPersonaCleanup" in destructive
    assert "确认清理" in destructive
    assert "输入确认短语" in destructive
    assert "我明白此操作不可撤销" in destructive
    assert "create_backup" in destructive


def test_uninstall_page_and_api_contract():
    page = _read("pages/storage.js")
    destructive = _read("destructive_admin.js")
    api = _read("api.js")
    app = _read("app.js")
    settings = _read("pages/settings.js")
    assert "存储与数据" in page
    assert "检查影响并卸载" in page
    assert "永久卸载 KarenBot" in destructive
    assert "acknowledge_destructive" in destructive
    assert "可选" in destructive or "备份" in destructive
    assert "adminPersonaCleanupPreview" in api
    assert "adminPersonaCleanupExecute" in api
    assert "adminUninstallPreview" in api
    assert "adminUninstallExecute" in api
    assert "X-Karen-Admin" in api
    assert "ROUTE_ALIASES = { data_admin: 'storage' }" in app
    assert "title: '存储与数据'" in app
    assert "navigate('storage')" in settings
