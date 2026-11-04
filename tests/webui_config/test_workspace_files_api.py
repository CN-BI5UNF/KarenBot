"""Host workspace file-manager API contracts."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webui.api import ALL_ROUTERS
from webui.api import workspace as workspace_api


def _request(root: Path) -> SimpleNamespace:
    rt = SimpleNamespace(paths=SimpleNamespace(WORKSPACE_DIR=root))
    host = SimpleNamespace(state="running", rt=rt, last_error=None)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))


@pytest.fixture
def workspace(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "hello.txt").write_text("hello", encoding="utf-8")
    (root / "blob.bin").write_bytes(b"bin\x00data")
    (root / "big.txt").write_text("x" * (workspace_api._MAX_PREVIEW_BYTES + 10), encoding="utf-8")
    (root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    nested = root / "incoming"
    nested.mkdir()
    (nested / "note.md").write_text("# note", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "outside-link").symlink_to(outside)
    (root / "inside-link").symlink_to(root / "hello.txt")
    # POSIX 允许控制字符文件名，Windows 会直接 OSError；控制字符过滤逻辑
    # 由下面的 _valid_component 单测在所有平台覆盖。
    if os.name != "nt":
        (root / "bad\x01name").write_text("hidden", encoding="utf-8")
    return root


def test_workspace_path_validator_rejects_control_characters():
    assert workspace_api._valid_component("bad\x01name") is False
    assert workspace_api._valid_component("normal-name.txt") is True


@pytest.mark.asyncio
async def test_workspace_files_lists_host_workspace_and_nested_dirs(workspace):
    root_data = await workspace_api.workspace_files(_request(workspace), "/")
    assert root_data["ok"] is True
    assert root_data["root"] == str(workspace.resolve())
    assert root_data["parent"] is None
    names = {item["name"] for item in root_data["entries"]}
    assert {"hello.txt", "blob.bin", "incoming", "outside-link"} <= names
    assert "bad\x01name" not in names
    assert root_data["count"] >= 4

    nested = await workspace_api.workspace_files(_request(workspace), "/incoming")
    assert nested["path"] == "/incoming"
    assert nested["parent"] == "/"
    assert [item["name"] for item in nested["entries"]] == ["note.md"]

    absolute = await workspace_api.workspace_files(
        _request(workspace), str(workspace / "incoming")
    )
    assert absolute["path"] == "/incoming"


@pytest.mark.asyncio
async def test_workspace_files_rejects_traversal_and_symlink_dirs(workspace):
    for path in ("/../outside.txt", "/incoming/../../outside.txt"):
        with pytest.raises(HTTPException) as error:
            await workspace_api.workspace_files(_request(workspace), path)
        assert error.value.status_code == 400
        assert error.value.detail["code"] in {
            "workspace_path_forbidden",
            "workspace_path_invalid",
        }

    with pytest.raises(HTTPException) as error:
        await workspace_api.workspace_files(
            _request(workspace), "/outside-link"
        )
    assert error.value.detail["code"] == "workspace_symlink_forbidden"


@pytest.mark.asyncio
async def test_workspace_preview_text_binary_and_bounded_read(workspace):
    text = await workspace_api.workspace_file_content(
        _request(workspace), "/incoming/note.md"
    )
    assert text["content"] == "# note"
    assert text["binary"] is False
    assert text["root"] == str(workspace.resolve())

    binary = await workspace_api.workspace_file_content(
        _request(workspace), "/blob.bin"
    )
    assert binary["binary"] is True
    assert binary["content"] == ""

    big = await workspace_api.workspace_file_content(
        _request(workspace), "/big.txt"
    )
    assert big["truncated"] is True
    assert big["preview_bytes"] == workspace_api._MAX_PREVIEW_BYTES
    assert len(big["content"]) == workspace_api._MAX_PREVIEW_BYTES


@pytest.mark.asyncio
async def test_workspace_preview_blocks_symlinks_and_missing_files(workspace):
    for path in ("/outside-link", "/inside-link"):
        with pytest.raises(HTTPException) as error:
            await workspace_api.workspace_file_content(_request(workspace), path)
        assert error.value.detail["code"] == "workspace_symlink_forbidden"

    with pytest.raises(HTTPException) as error:
        await workspace_api.workspace_file_content(
            _request(workspace), "/missing.txt"
        )
    assert error.value.detail["code"] == "workspace_path_not_found"


def test_workspace_router_is_registered():
    prefixes = {getattr(router, "prefix", "") for router in ALL_ROUTERS}
    assert "/api/workspace" in prefixes


@pytest.mark.asyncio
async def test_workspace_raw_image_returns_bytes_and_rejects_non_images(workspace):
    response = await workspace_api.workspace_file_raw(
        _request(workspace), "/pic.png"
    )
    assert response.media_type == "image/png"
    assert response.body.startswith(b"\x89PNG")
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    with pytest.raises(HTTPException) as error:
        await workspace_api.workspace_file_raw(
            _request(workspace), "/hello.txt"
        )
    assert error.value.detail["code"] == "workspace_not_image"

    with pytest.raises(HTTPException) as error:
        await workspace_api.workspace_file_raw(
            _request(workspace), "/outside-link"
        )
    assert error.value.detail["code"] == "workspace_symlink_forbidden"
