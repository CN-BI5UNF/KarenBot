"""Host workspace is merged into the container page file manager."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "webui/static/js"


def test_workspace_browser_is_merged_into_container_file_manager():
    app = (JS / "app.js").read_text(encoding="utf-8")
    browser = (JS / "container_files.js").read_text(encoding="utf-8")
    api = (JS / "api.js").read_text(encoding="utf-8")
    container_page = (JS / "pages/container.js").read_text(encoding="utf-8")

    assert "pages/workspace.js" not in app
    assert "key: 'workspace'" not in app
    assert "本机工作区" in browser
    assert "容器工作区" in browser
    assert "容器根目录" not in browser
    assert "AppPaths.WORKSPACE_DIR" in browser
    assert "endpoints.workspaceFiles" in browser
    assert "endpoints.containerFiles" in browser
    assert "endpoints.workspaceFileRawUrl" in browser
    assert "endpoints.containerFileRawUrl" in browser
    assert "workspaceFiles:" in api
    assert "workspaceFileContent:" in api
    assert "workspaceFileRawUrl:" in api
    assert "containerFileRawUrl:" in api
    assert "/api/workspace/files" in api
    assert "不是本机" in browser or "两个互相独立" in browser
    assert "文件管理" in container_page
