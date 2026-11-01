"""Persona appearance upload/list/file/delete API contracts."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import UploadFile

from webui.api import personas as personas_api


def _png_bytes(color=(30, 80, 180)) -> bytes:
    image = Image.new("RGB", (16, 12), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(data: bytes, filename: str = "appearance.png") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


@pytest.fixture
def persona_rt(tmp_path: Path):
    persona = tmp_path / "personas" / "alice"
    persona.mkdir(parents=True)
    (persona / "persona_prompt.py").write_text(
        'PERSONA_PROMPT = "hi"\n', encoding="utf-8"
    )
    paths = SimpleNamespace(PERSONAS_DIR=tmp_path / "personas")
    rt = SimpleNamespace(
        paths=paths,
        config=SimpleNamespace(persona=SimpleNamespace(active="alice")),
    )
    host = SimpleNamespace(rt=rt, state="running", last_error=None)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(host=host)))
    return request, rt


@pytest.mark.asyncio
async def test_persona_appearance_gallery_upload_cover_file_and_delete(persona_rt):
    request, rt = persona_rt

    listed = await personas_api.list_personas(request)
    assert listed["personas"][0]["appearance"] is None
    assert listed["personas"][0]["appearance_count"] == 0

    first = await personas_api.upload_persona_appearance(
        request, "alice", _upload(_png_bytes())
    )
    second = await personas_api.upload_persona_appearance(
        request, "alice", _upload(_png_bytes((180, 40, 40)), "second.png")
    )
    assert first["ok"] is True
    assert first["appearance"]["mime"] == "image/png"
    assert first["appearance"]["width"] == 16
    assert "path" not in first["appearance"]
    first_id = first["appearance"]["id"]
    second_id = second["appearance"]["id"]
    assert first_id != second_id

    listed = await personas_api.list_personas(request)
    assert listed["personas"][0]["appearance_count"] == 2
    assert listed["personas"][0]["appearance"]["id"] == first_id

    metadata = await personas_api.get_persona_appearance(request, "alice")
    assert metadata["appearance"]["id"] == first_id
    assert len(metadata["images"]) == 2
    assert metadata["images"][0]["cover"] is True
    response = await personas_api.get_persona_appearance_file(
        request, "alice", image_id=second_id
    )
    assert Path(response.path).is_file()
    assert response.media_type == "image/png"

    cover = await personas_api.set_persona_appearance_cover(
        request, "alice", second_id
    )
    assert cover["appearance"]["id"] == second_id
    assert cover["appearance"]["cover"] is True

    deleted = await personas_api.delete_persona_appearance_image(
        request, "alice", first_id
    )
    assert deleted["deleted"] is True
    assert deleted["deleted_count"] == 1
    assert deleted["cover"]["id"] == second_id

    deleted = await personas_api.delete_persona_appearance(request, "alice")
    assert deleted["deleted"] is True
    assert deleted["deleted_count"] == 1
    assert (rt.paths.PERSONAS_DIR / "alice" / "appearance").exists() is False


@pytest.mark.asyncio
async def test_persona_appearance_rejects_invalid_image_and_missing_persona(persona_rt):
    request, _rt = persona_rt
    with pytest.raises(HTTPException) as error:
        await personas_api.upload_persona_appearance(
            request, "alice", _upload(b"not an image")
        )
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        await personas_api.get_persona_appearance(request, "missing")
    assert error.value.status_code == 400
