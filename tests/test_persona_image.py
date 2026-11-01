"""Persona appearance gallery storage, cover selection and safety boundaries."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app_config.paths import AppPaths
from core.persona_image import (
    PERSONA_IMAGE_PREFIX,
    PersonaImageError,
    PersonaImageStore,
    format_persona_image_ref,
    parse_persona_image_ref,
)


def _png_bytes(color=(20, 120, 200)) -> bytes:
    image = Image.new("RGB", (32, 24), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (40, 20), (200, 40, 80))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def persona_paths(tmp_path: Path):
    paths = AppPaths(project_root=tmp_path)
    persona = paths.PERSONAS_DIR / "alice"
    persona.mkdir(parents=True)
    (persona / "persona_prompt.py").write_text(
        'PERSONA_PROMPT = "hi"\n', encoding="utf-8"
    )
    return paths


@pytest.mark.asyncio
async def test_gallery_upload_cover_resolve_and_delete(persona_paths):
    store = PersonaImageStore(persona_paths)

    first = await store.save("alice", _png_bytes())
    second = await store.save("alice", _jpeg_bytes())

    assert first["id"].startswith("a_")
    assert first["mime"] == "image/png"
    assert (first["width"], first["height"]) == (32, 24)
    assert "path" not in first
    images = store.list_images("alice")
    assert [item["id"] for item in images] == [first["id"], second["id"]]
    assert images[0]["cover"] is True
    assert store.get("alice")["id"] == first["id"]
    assert store.resolve("alice").is_file()
    assert store.resolve("alice", second["id"]).is_file()

    selected = store.set_cover("alice", second["id"])
    assert selected["id"] == second["id"]
    assert selected["cover"] is True
    assert store.get("alice")["id"] == second["id"]

    result = store.delete("alice", first["id"])
    assert result["deleted"] is True
    assert result["deleted_count"] == 1
    assert [item["id"] for item in store.list_images("alice")] == [second["id"]]

    result = store.delete("alice")
    assert result["deleted"] is True
    assert store.list_images("alice") == []
    assert store.get("alice") is None
    assert (persona_paths.PERSONAS_DIR / "alice" / "appearance").exists() is False


@pytest.mark.asyncio
async def test_deleting_cover_promotes_remaining_image(persona_paths):
    store = PersonaImageStore(persona_paths)
    first = await store.save("alice", _png_bytes())
    second = await store.save("alice", _jpeg_bytes())
    assert store.get("alice")["id"] == first["id"]

    result = store.delete("alice", first["id"])

    assert result["cover"]["id"] == second["id"]
    assert store.get("alice")["cover"] is True


@pytest.mark.asyncio
async def test_legacy_single_image_remains_readable(persona_paths):
    directory = persona_paths.PERSONAS_DIR / "alice" / "appearance"
    directory.mkdir()
    (directory / "image.png").write_bytes(_png_bytes())

    store = PersonaImageStore(persona_paths)
    info = store.get("alice")

    assert info is not None
    assert info["id"] == "legacy"
    assert info["cover"] is True
    assert store.resolve("alice").name == "image.png"


@pytest.mark.asyncio
async def test_duplicate_persona_copies_gallery(persona_paths):
    from webui.persona_admin import duplicate_persona

    store = PersonaImageStore(persona_paths)
    await store.save("alice", _png_bytes())
    await store.save("alice", _jpeg_bytes())

    duplicate_persona(persona_paths, "alice", "alice_copy")

    copied = PersonaImageStore(persona_paths).list_images("alice_copy")
    assert len(copied) == 2
    assert sum(1 for item in copied if item["cover"]) == 1


def test_persona_image_reference_round_trip():
    ref = format_persona_image_ref("小堡", "a_0123456789abcdef")
    assert ref == f"{PERSONA_IMAGE_PREFIX}小堡:a_0123456789abcdef"
    assert parse_persona_image_ref(ref) == ("小堡", "a_0123456789abcdef")
    assert parse_persona_image_ref("persona-image:小堡") == ("小堡", None)
    assert parse_persona_image_ref("workspace/a.png") is None
    with pytest.raises(PersonaImageError):
        parse_persona_image_ref("persona-image:小堡:not-an-id")


@pytest.mark.asyncio
async def test_rejects_invalid_images_and_unsafe_names(persona_paths):
    store = PersonaImageStore(persona_paths)
    with pytest.raises(PersonaImageError, match="图片"):
        await store.save("alice", b"not an image")
    with pytest.raises(PersonaImageError):
        await store.save("../alice", _png_bytes())
    with pytest.raises(PersonaImageError):
        store.get("missing")


@pytest.mark.asyncio
async def test_rejects_symlinked_appearance_directory(persona_paths, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    persona = persona_paths.PERSONAS_DIR / "alice"
    link = persona / "appearance"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")
    store = PersonaImageStore(persona_paths)
    with pytest.raises(PersonaImageError, match="符号链接"):
        await store.save("alice", _png_bytes())


@pytest.mark.asyncio
async def test_rejects_symlink_inside_gallery(persona_paths, tmp_path):
    store = PersonaImageStore(persona_paths)
    info = await store.save("alice", _png_bytes())
    directory = persona_paths.PERSONAS_DIR / "alice" / "appearance"
    target = directory / "linked.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    with pytest.raises(PersonaImageError, match="符号链接"):
        store.list_images("alice")
    assert info["id"]
