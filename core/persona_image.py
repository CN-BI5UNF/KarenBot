"""Per-persona character appearance images.

Appearance images are admin-managed, stored beside the persona definition, and
never exposed through a write tool to the LLM.  The knowledge layer presents
every image as a read-only virtual entry; ``describe_image`` and the send tools
can resolve ``persona-image:<persona>[:<image_id>]`` references.

Storage layout:

    personas/<persona>/appearance/
        manifest.json              # cover_id + ordered image entries
        a_<16 hex>.jpg|png|gif

Legacy single-image directories (``image.jpg`` / ``image.png`` / ``image.gif``)
remain readable.  The next mutation folds them into the manifest without
rewriting the existing file.

Keeping images inside the persona directory means persona export, duplicate and
import naturally include them.  Persona runtime cleanup deliberately does not
touch the persona definition, so appearances are retained there too.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from agents.persona_loader import validate_persona_name
from features.vision.image_assets import ImageAssetError, prepare_image_data_url
from utils.image_contracts import MAX_IMAGE_BYTES, ImageLimits

logger = logging.getLogger(__name__)

APPEARANCE_DIR = "appearance"
MANIFEST_NAME = "manifest.json"
LEGACY_IMAGE_STEM = "image"
LEGACY_IMAGE_ID = "legacy"
PERSONA_IMAGE_PREFIX = "persona-image:"
IMAGE_ID_RE = re.compile(r"^a_[0-9a-f]{16}$")
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif"})
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
}


class PersonaImageError(ValueError):
    """Safe user-facing error. Messages contain no host paths or secrets."""


def _iso_mtime(path: Path) -> str:
    try:
        value = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def _valid_image_id(value: Any) -> str:
    image_id = str(value or "").strip()
    if image_id == LEGACY_IMAGE_ID or IMAGE_ID_RE.fullmatch(image_id):
        return image_id
    raise PersonaImageError("无效的角色形象编号")


def format_persona_image_ref(name: str, image_id: str | None = None) -> str:
    """Build the stable reference handed to the model."""
    persona = str(name or "").strip()
    if not persona:
        raise PersonaImageError("人格名为空")
    suffix = f":{_valid_image_id(image_id)}" if image_id else ""
    return f"{PERSONA_IMAGE_PREFIX}{persona}{suffix}"


def parse_persona_image_ref(value: str) -> tuple[str, str | None] | None:
    """Parse ``persona-image:<persona>[:<image_id>]``; None for other refs."""
    text = str(value or "").strip()
    if not text.lower().startswith(PERSONA_IMAGE_PREFIX):
        return None
    rest = text[len(PERSONA_IMAGE_PREFIX):].strip()
    if not rest:
        raise PersonaImageError("角色形象引用为空")
    parts = rest.split(":")
    if len(parts) > 2:
        raise PersonaImageError("角色形象引用格式无效")
    persona = parts[0].strip()
    image_id = _valid_image_id(parts[1]) if len(parts) == 2 else None
    if not persona:
        raise PersonaImageError("角色形象引用缺少人格名")
    return persona, image_id


class PersonaImageStore:
    """Manage a collection of normalized appearance images per persona."""

    def __init__(self, paths: Any) -> None:
        self.root = Path(paths.PERSONAS_DIR)
        self._lock = threading.RLock()
        self._meta_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Paths and lookup
    # ------------------------------------------------------------------

    def _persona_dir(self, name: str) -> Path:
        try:
            validate_persona_name(str(name or "").strip())
        except ValueError as exc:
            raise PersonaImageError(str(exc)) from None
        persona = self.root / str(name).strip()
        if persona.is_symlink():
            raise PersonaImageError("拒绝使用符号链接人格目录")
        if not persona.is_dir() or not (persona / "persona_prompt.py").is_file():
            raise PersonaImageError("人格不存在")
        try:
            persona_resolved = persona.resolve()
            root_resolved = self.root.resolve()
        except OSError:
            raise PersonaImageError("人格目录无法读取") from None
        if persona_resolved.parent != root_resolved:
            raise PersonaImageError("人格目录越界")
        return persona

    def _appearance_dir(self, name: str, *, create: bool = False) -> Path:
        directory = self._persona_dir(name) / APPEARANCE_DIR
        if directory.is_symlink():
            raise PersonaImageError("拒绝使用符号链接形象目录")
        if directory.exists() and not directory.is_dir():
            raise PersonaImageError("形象目录不是文件夹")
        if create and not directory.exists():
            directory.mkdir(mode=0o700, parents=False)
        return directory

    def _manifest_path(self, directory: Path) -> Path:
        return directory / MANIFEST_NAME

    def _entry_path(self, directory: Path, entry: dict[str, Any]) -> Path:
        filename = str(entry.get("file") or "").strip()
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or Path(filename).name != filename
        ):
            raise PersonaImageError("形象清单包含非法文件名")
        path = directory / filename
        if path.is_symlink():
            raise PersonaImageError("拒绝读取符号链接形象文件")
        if not path.is_file():
            raise PersonaImageError("角色形象文件不存在")
        if path.suffix.lower() not in _IMAGE_EXTS:
            raise PersonaImageError("不支持的图片格式")
        return path

    def _scan_locked(self, directory: Path) -> list[dict[str, Any]]:
        """Rebuild manifest entries from appearance files without following symlinks."""
        if not directory.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for path in directory.iterdir():
            if path.is_symlink():
                raise PersonaImageError("拒绝读取符号链接形象文件")
            if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
                continue
            stem = path.stem
            if stem == LEGACY_IMAGE_STEM:
                image_id = LEGACY_IMAGE_ID
            elif IMAGE_ID_RE.fullmatch(stem):
                image_id = stem
            else:
                continue
            entries.append(
                {
                    "id": image_id,
                    "file": path.name,
                    "created_at": _iso_mtime(path),
                }
            )
        entries.sort(
            key=lambda item: (
                0 if item["id"] == LEGACY_IMAGE_ID else 1,
                item.get("created_at") or "",
                item["id"],
            )
        )
        return entries

    def _load_manifest_locked(
        self,
        directory: Path,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        manifest_path = self._manifest_path(directory)
        if manifest_path.is_symlink():
            raise PersonaImageError("拒绝使用符号链接形象清单")
        entries: list[dict[str, Any]] = []
        cover_id = ""
        if manifest_path.is_file():
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("角色形象清单损坏，按目录内容重建")
                raw = {}
            if isinstance(raw, dict):
                cover_id = str(raw.get("cover_id") or "").strip()
                values = raw.get("images")
                if isinstance(values, list):
                    for item in values:
                        if not isinstance(item, dict):
                            continue
                        try:
                            image_id = _valid_image_id(item.get("id"))
                            path = self._entry_path(directory, item)
                        except PersonaImageError:
                            continue
                        entries.append(
                            {
                                "id": image_id,
                                "file": path.name,
                                "created_at": str(item.get("created_at") or _iso_mtime(path)),
                            }
                        )
        scanned = self._scan_locked(directory)
        known_ids = {item["id"] for item in entries}
        for item in scanned:
            if item["id"] not in known_ids:
                entries.append(item)
                known_ids.add(item["id"])
        valid_ids = {item["id"] for item in entries}
        if cover_id not in valid_ids:
            cover_id = entries[0]["id"] if entries else ""
        manifest = {"version": 1, "cover_id": cover_id or None, "images": entries}
        return manifest, entries

    def _write_manifest_locked(
        self,
        directory: Path,
        manifest: dict[str, Any],
    ) -> None:
        entries = list(manifest.get("images") or [])
        manifest_path = self._manifest_path(directory)
        if not entries:
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        temp = directory / f".{MANIFEST_NAME}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, manifest_path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def _info_locked(
        self,
        name: str,
        directory: Path,
        entry: dict[str, Any],
        cover_id: str,
    ) -> dict[str, Any]:
        path = self._entry_path(directory, entry)
        stat = path.stat()
        cache_key = (int(stat.st_mtime_ns), int(stat.st_size))
        with self._lock:
            cached = self._meta_cache.get(str(path))
        if cached is not None and cached[0] == cache_key:
            intrinsic = dict(cached[1])
        else:
            width = 0
            height = 0
            try:
                with Image.open(path) as image:
                    width, height = image.size
            except (OSError, UnidentifiedImageError):
                pass
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                digest = ""
            intrinsic = {
                "mime": _MIME_BY_EXT.get(path.suffix.lower(), ""),
                "size": int(stat.st_size),
                "width": int(width),
                "height": int(height),
                "sha256": digest,
                "updated_at": _iso_mtime(path),
            }
            with self._lock:
                self._meta_cache[str(path)] = (cache_key, intrinsic)
        return {
            "persona": str(name),
            "id": entry["id"],
            "cover": entry["id"] == cover_id,
            "created_at": str(entry.get("created_at") or intrinsic.get("updated_at") or ""),
            **intrinsic,
        }

    def list_images(self, name: str) -> list[dict[str, Any]]:
        """Return public-safe metadata for every image."""
        with self._lock:
            directory = self._appearance_dir(name)
            if not directory.is_dir():
                return []
            manifest, entries = self._load_manifest_locked(directory)
            cover_id = str(manifest.get("cover_id") or "")
            return [
                self._info_locked(name, directory, entry, cover_id)
                for entry in entries
            ]

    def get(self, name: str, image_id: str | None = None) -> dict[str, Any] | None:
        """Return one image's public metadata; ``None`` means the cover image."""
        with self._lock:
            directory = self._appearance_dir(name)
            if not directory.is_dir():
                return None
            manifest, entries = self._load_manifest_locked(directory)
            if not entries:
                return None
            cover_id = str(manifest.get("cover_id") or "")
            wanted = str(image_id or "").strip()
            target = None
            if wanted:
                target = next((item for item in entries if item["id"] == wanted), None)
                if target is None:
                    raise PersonaImageError("角色形象不存在")
            else:
                target = next(
                    (item for item in entries if item["id"] == cover_id),
                    entries[0],
                )
            return self._info_locked(name, directory, target, cover_id)

    def count(self, name: str) -> int:
        return len(self.list_images(name))

    def resolve(self, name: str, image_id: str | None = None) -> Path:
        """Return a trusted local image path for helper/vision/send code only."""
        with self._lock:
            directory = self._appearance_dir(name)
            if not directory.is_dir():
                raise PersonaImageError("该人格还没有角色形象")
            manifest, entries = self._load_manifest_locked(directory)
            if not entries:
                raise PersonaImageError("该人格还没有角色形象")
            cover_id = str(manifest.get("cover_id") or "")
            wanted = str(image_id or "").strip()
            if wanted:
                entry = next((item for item in entries if item["id"] == wanted), None)
                if entry is None:
                    raise PersonaImageError("角色形象不存在")
            else:
                entry = next(
                    (item for item in entries if item["id"] == cover_id),
                    entries[0],
                )
            return self._entry_path(directory, entry)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def save(self, name: str, data: bytes) -> dict[str, Any]:
        """Validate/normalize an upload and append it to the persona gallery."""
        self._persona_dir(name)
        raw = bytes(data or b"")
        if not raw:
            raise PersonaImageError("图片内容为空")
        if len(raw) > MAX_IMAGE_BYTES:
            raise PersonaImageError(
                f"图片超过 {MAX_IMAGE_BYTES // 1024 // 1024} MiB 上限"
            )
        try:
            data_url = await prepare_image_data_url(raw, limits=ImageLimits())
        except ImageAssetError as exc:
            raise PersonaImageError(exc.safe_message()) from None
        header, separator, payload = data_url.partition(",")
        if not separator or ";base64" not in header.lower():
            raise PersonaImageError("图片处理结果无效")
        mime = header[5:].split(";", 1)[0].strip().lower()
        extension = _EXT_BY_MIME.get(mime)
        if extension is None:
            raise PersonaImageError("不支持的图片格式")
        try:
            normalized = base64.b64decode(payload, validate=True)
        except (ValueError, TypeError):
            raise PersonaImageError("图片处理结果无效") from None
        if not normalized or len(normalized) > MAX_IMAGE_BYTES:
            raise PersonaImageError("图片处理结果超过上限")
        return await asyncio.to_thread(self._append_normalized, name, normalized, extension)

    def _append_normalized(
        self,
        name: str,
        data: bytes,
        extension: str,
    ) -> dict[str, Any]:
        image_id = f"a_{secrets.token_hex(8)}"
        with self._lock:
            directory = self._appearance_dir(name, create=True)
            target = directory / f"{image_id}{extension}"
            temp = directory / f".{image_id}.{os.getpid()}.tmp"
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, target)
            finally:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
            self._meta_cache.clear()
            manifest, entries = self._load_manifest_locked(directory)
            entry = next((item for item in entries if item["id"] == image_id), None)
            if entry is None:
                entry = {
                    "id": image_id,
                    "file": target.name,
                    "created_at": _iso_mtime(target),
                }
                entries.append(entry)
            if not manifest.get("cover_id"):
                manifest["cover_id"] = image_id
            manifest["images"] = entries
            self._write_manifest_locked(directory, manifest)
            return self._info_locked(
                name,
                directory,
                entry,
                str(manifest.get("cover_id") or ""),
            )

    def set_cover(self, name: str, image_id: str) -> dict[str, Any]:
        """Choose which gallery image is used as the persona preview."""
        wanted = _valid_image_id(image_id)
        with self._lock:
            directory = self._appearance_dir(name)
            if not directory.is_dir():
                raise PersonaImageError("该人格还没有角色形象")
            manifest, entries = self._load_manifest_locked(directory)
            entry = next((item for item in entries if item["id"] == wanted), None)
            if entry is None:
                raise PersonaImageError("角色形象不存在")
            manifest["cover_id"] = wanted
            manifest["images"] = entries
            self._write_manifest_locked(directory, manifest)
            self._meta_cache.clear()
            return self._info_locked(name, directory, entry, wanted)

    def delete(self, name: str, image_id: str | None = None) -> dict[str, Any]:
        """Delete one image, or the whole gallery when ``image_id`` is omitted."""
        with self._lock:
            directory = self._appearance_dir(name)
            if not directory.is_dir():
                return {"deleted": False, "deleted_count": 0, "cover": None}
            manifest, entries = self._load_manifest_locked(directory)
            if not entries:
                return {"deleted": False, "deleted_count": 0, "cover": None}
            if image_id is None:
                removed = 0
                for entry in entries:
                    try:
                        self._entry_path(directory, entry).unlink(missing_ok=True)
                        removed += 1
                    except (OSError, PersonaImageError):
                        pass
                try:
                    self._manifest_path(directory).unlink(missing_ok=True)
                except OSError:
                    pass
                try:
                    directory.rmdir()
                except OSError:
                    pass
                self._meta_cache.clear()
                return {
                    "deleted": removed > 0,
                    "deleted_count": removed,
                    "cover": None,
                }
            wanted = _valid_image_id(image_id)
            entry = next((item for item in entries if item["id"] == wanted), None)
            if entry is None:
                raise PersonaImageError("角色形象不存在")
            try:
                self._entry_path(directory, entry).unlink(missing_ok=True)
            except OSError as exc:
                raise PersonaImageError(f"删除形象失败：{exc}") from None
            remaining = [item for item in entries if item["id"] != wanted]
            manifest["images"] = remaining
            if manifest.get("cover_id") == wanted:
                manifest["cover_id"] = remaining[0]["id"] if remaining else None
            self._write_manifest_locked(directory, manifest)
            self._meta_cache.clear()
            if not remaining:
                try:
                    directory.rmdir()
                except OSError:
                    pass
            cover = None
            if remaining:
                cover_id = str(manifest.get("cover_id") or "")
                cover_entry = next(
                    (item for item in remaining if item["id"] == cover_id),
                    remaining[0],
                )
                cover = self._info_locked(name, directory, cover_entry, cover_id)
            return {
                "deleted": True,
                "deleted_count": 1,
                "image_id": wanted,
                "cover": cover,
            }


__all__ = [
    "APPEARANCE_DIR",
    "IMAGE_ID_RE",
    "LEGACY_IMAGE_ID",
    "MANIFEST_NAME",
    "PERSONA_IMAGE_PREFIX",
    "PersonaImageError",
    "PersonaImageStore",
    "format_persona_image_ref",
    "parse_persona_image_ref",
]
