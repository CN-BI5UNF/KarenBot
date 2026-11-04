"""Container file-manager API contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from features.container import ContainerError
from webui.api import container as container_api


def _request(service) -> SimpleNamespace:
    host = SimpleNamespace(state="running", rt=SimpleNamespace(container=service))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))


class FakeService:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def browse_files(self, path):
        self.paths.append(path)
        return {
            "ok": True,
            "path": path,
            "parent": None if path == "/" else (path.rsplit("/", 1)[0] or "/"),
            "entries": [],
            "count": 0,
        }

    async def preview_file(self, path):
        self.paths.append(path)
        return {"ok": True, "path": path, "content": "hello", "binary": False}

    async def read_image(self, path):
        self.paths.append(path)
        return {"data": b"\x89PNG\r\n\x1a\nrest", "path": path}


@pytest.mark.asyncio
async def test_files_endpoint_delegates_path_and_returns_structured_result():
    service = FakeService()
    data = await container_api.container_files(_request(service), "/workspace")
    assert data["ok"] is True
    assert data["parent"] == "/"
    assert service.paths == ["/workspace"]
    preview = await container_api.container_file_content(
        _request(service), "/workspace/a.txt"
    )
    assert preview["content"] == "hello"
    assert service.paths[-1] == "/workspace/a.txt"


@pytest.mark.asyncio
async def test_files_endpoint_maps_container_errors():
    class FailingService(FakeService):
        async def browse_files(self, path):
            raise ContainerError(
                "不是目录", code="container_not_directory"
            )

    with pytest.raises(HTTPException) as error:
        await container_api.container_files(_request(FailingService()), "/workspace/x")
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "container_not_directory"
    assert "不是目录" in error.value.detail["message"]


@pytest.mark.asyncio
async def test_files_endpoint_rejects_paths_outside_container_workspace():
    service = FakeService()
    with pytest.raises(HTTPException) as error:
        await container_api.container_files(_request(service), "/etc")
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "container_path_forbidden"
    assert service.paths == []


@pytest.mark.asyncio
async def test_file_raw_endpoint_returns_image_bytes():
    service = FakeService()
    response = await container_api.container_file_raw(
        _request(service), "/workspace/pic.png"
    )
    assert response.media_type == "image/png"
    assert response.body.startswith(b"\x89PNG")
    assert service.paths == ["/workspace/pic.png"]
