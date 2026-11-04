"""Read-only WebUI browser for the host AI workspace.

The host workspace is ``AppPaths.WORKSPACE_DIR`` (normally
``~/.local/share/Debata_Agent/instances/default/workspace``).  This is a
different directory from the container's ``/workspace``, which is the
container storage mount under ``.../container/workspace``.

The API is read-only and never follows symlinks.  Directory listings are
bounded and only regular files are previewed; binary files never send their
bytes to the browser.
"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from webui.file_types import MAX_IMAGE_BYTES, image_media_type

from .deps import require_runtime

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

_MAX_ENTRIES = 1000
_MAX_PREVIEW_BYTES = 128 * 1024


class WorkspaceFileError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _safe_text(value: Any, limit: int = 512) -> str:
    text = "".join(
        ch for ch in str(value or "") if ord(ch) >= 32 and ord(ch) != 127
    )
    return text[:limit]


def _valid_component(part: str) -> bool:
    if not part or part in {".", ".."}:
        return False
    if "/" in part or "\\" in part or ":" in part:
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in part)


def _normalize_parts(root: Path, raw: str) -> tuple[str, ...]:
    text = str(raw or "").strip().replace("\\", "/")
    root_text = root.as_posix().rstrip("/")
    if text == root_text:
        return ()
    if text.startswith(root_text + "/"):
        text = text[len(root_text) + 1 :]
    if text.startswith("/"):
        text = text.lstrip("/")
    parts = tuple(part for part in text.split("/") if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise WorkspaceFileError(
            "工作区路径不允许 ..", code="workspace_path_forbidden"
        )
    if any(not _valid_component(part) for part in parts):
        raise WorkspaceFileError(
            "工作区路径包含无效字符", code="workspace_path_invalid"
        )
    return parts


def _display_path(parts: tuple[str, ...]) -> str:
    return "/" + "/".join(parts) if parts else "/"


def _root(request: Request) -> Path:
    rt = require_runtime(request)
    path = Path(rt.paths.WORKSPACE_DIR)
    try:
        root = path.resolve()
    except (OSError, RuntimeError):
        raise WorkspaceFileError(
            "本机工作区路径无效", code="workspace_root_invalid"
        ) from None
    if not root.is_dir():
        raise WorkspaceFileError(
            "本机工作区目录不存在", code="workspace_root_missing"
        )
    return root


def _resolve_target(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts[:-1]:
        candidate = current / part
        try:
            st = os.lstat(candidate)
        except FileNotFoundError:
            raise WorkspaceFileError(
                "目录不存在", code="workspace_path_not_found"
            ) from None
        except PermissionError:
            raise WorkspaceFileError(
                "没有权限读取该目录", code="workspace_permission_denied"
            ) from None
        except OSError:
            raise WorkspaceFileError(
                "无法读取目录", code="workspace_read_failed"
            ) from None
        if stat.S_ISLNK(st.st_mode):
            raise WorkspaceFileError(
                "不允许通过符号链接浏览目录",
                code="workspace_symlink_forbidden",
            )
        if not stat.S_ISDIR(st.st_mode):
            raise WorkspaceFileError(
                "路径中存在非目录项", code="workspace_not_directory"
            )
        current = candidate
    target = current.joinpath(*parts[-1:]) if parts else root
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        raise WorkspaceFileError(
            "路径不存在", code="workspace_path_not_found"
        ) from None
    except PermissionError:
        raise WorkspaceFileError(
            "没有权限读取该路径", code="workspace_permission_denied"
        ) from None
    except OSError:
        raise WorkspaceFileError(
            "无法读取路径", code="workspace_read_failed"
        ) from None
    if stat.S_ISLNK(st.st_mode):
        raise WorkspaceFileError(
            "不允许通过符号链接访问文件",
            code="workspace_symlink_forbidden",
        )
    return target


def _entry_type(st: os.stat_result) -> str:
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    if stat.S_ISREG(st.st_mode):
        return "file"
    return "other"


def _browse(root: Path, raw_path: str) -> dict[str, Any]:
    parts = _normalize_parts(root, raw_path)
    target = _resolve_target(root, parts)
    try:
        st = os.lstat(target)
    except OSError as exc:  # already handled in _resolve_target, defensive
        raise WorkspaceFileError(
            "无法读取目录", code="workspace_read_failed"
        ) from exc
    if not stat.S_ISDIR(st.st_mode):
        raise WorkspaceFileError(
            "路径不是目录", code="workspace_not_directory"
        )
    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        with os.scandir(target) as iterator:
            for entry in iterator:
                if len(entries) >= _MAX_ENTRIES:
                    truncated = True
                    break
                if not _valid_component(entry.name):
                    continue
                try:
                    item_st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                kind = _entry_type(item_st)
                target_text = ""
                if kind == "symlink":
                    try:
                        target_text = _safe_text(os.readlink(entry.path), 1024)
                    except OSError:
                        target_text = ""
                entries.append(
                    {
                        "name": entry.name,
                        "path": _display_path(parts + (entry.name,)),
                        "type": kind,
                        "size": max(0, int(item_st.st_size)),
                        "mtime": max(0.0, float(item_st.st_mtime)),
                        "mode": format(stat.S_IMODE(item_st.st_mode), "04o"),
                        "target": target_text,
                    }
                )
    except PermissionError:
        raise WorkspaceFileError(
            "没有权限读取该目录", code="workspace_permission_denied"
        ) from None
    except OSError:
        raise WorkspaceFileError(
            "无法读取目录", code="workspace_read_failed"
        ) from None
    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    return {
        "ok": True,
        "root": str(root),
        "path": _display_path(parts),
        "parent": None if not parts else (_display_path(parts[:-1]) or "/"),
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
        "max_entries": _MAX_ENTRIES,
    }


def _preview(root: Path, raw_path: str) -> dict[str, Any]:
    parts = _normalize_parts(root, raw_path)
    if not parts:
        raise WorkspaceFileError(
            "该操作需要具体文件路径", code="workspace_path_invalid"
        )
    target = _resolve_target(root, parts)
    try:
        st = os.lstat(target)
    except OSError as exc:
        raise WorkspaceFileError(
            "无法读取文件", code="workspace_read_failed"
        ) from exc
    if stat.S_ISLNK(st.st_mode):
        raise WorkspaceFileError(
            "不允许通过符号链接读取文件",
            code="workspace_symlink_forbidden",
        )
    if not stat.S_ISREG(st.st_mode):
        raise WorkspaceFileError(
            "路径不是普通文件", code="workspace_not_regular_file"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        raise WorkspaceFileError(
            "文件不存在", code="workspace_path_not_found"
        ) from None
    except PermissionError:
        raise WorkspaceFileError(
            "没有权限读取该文件", code="workspace_permission_denied"
        ) from None
    except OSError:
        raise WorkspaceFileError(
            "无法读取文件", code="workspace_read_failed"
        ) from None
    try:
        opened_st = os.fstat(fd)
        if not stat.S_ISREG(opened_st.st_mode):
            raise WorkspaceFileError(
                "路径不是普通文件", code="workspace_not_regular_file"
            )
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(_MAX_PREVIEW_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    truncated = len(data) > _MAX_PREVIEW_BYTES
    data = data[:_MAX_PREVIEW_BYTES]
    binary = b"\x00" in data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
        binary = True
    return {
        "ok": True,
        "root": str(root),
        "path": _display_path(parts),
        "name": _safe_text(target.name, 512),
        "size": max(0, int(opened_st.st_size)),
        "mtime": max(0.0, float(opened_st.st_mtime)),
        "mode": format(stat.S_IMODE(opened_st.st_mode), "04o"),
        "content": "" if binary else text,
        "binary": binary,
        "truncated": truncated,
        "preview_bytes": min(len(data), _MAX_PREVIEW_BYTES),
    }


def _read_image(root: Path, raw_path: str) -> dict[str, Any]:
    parts = _normalize_parts(root, raw_path)
    if not parts:
        raise WorkspaceFileError(
            "该操作需要具体文件路径", code="workspace_path_invalid"
        )
    target = _resolve_target(root, parts)
    try:
        st = os.lstat(target)
    except OSError as exc:
        raise WorkspaceFileError(
            "无法读取文件", code="workspace_read_failed"
        ) from exc
    if stat.S_ISLNK(st.st_mode):
        raise WorkspaceFileError(
            "不允许通过符号链接读取文件",
            code="workspace_symlink_forbidden",
        )
    if not stat.S_ISREG(st.st_mode):
        raise WorkspaceFileError(
            "路径不是普通文件", code="workspace_not_regular_file"
        )
    if st.st_size > MAX_IMAGE_BYTES:
        raise WorkspaceFileError(
            "图片超过文件管理器的预览上限", code="workspace_image_too_large"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        raise WorkspaceFileError(
            "文件不存在", code="workspace_path_not_found"
        ) from None
    except PermissionError:
        raise WorkspaceFileError(
            "没有权限读取该文件", code="workspace_permission_denied"
        ) from None
    except OSError:
        raise WorkspaceFileError(
            "无法读取文件", code="workspace_read_failed"
        ) from None
    try:
        opened_st = os.fstat(fd)
        if not stat.S_ISREG(opened_st.st_mode):
            raise WorkspaceFileError(
                "路径不是普通文件", code="workspace_not_regular_file"
            )
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(MAX_IMAGE_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > MAX_IMAGE_BYTES:
        raise WorkspaceFileError(
            "图片超过文件管理器的预览上限", code="workspace_image_too_large"
        )
    media_type = image_media_type(data)
    if media_type is None:
        raise WorkspaceFileError(
            "该文件不是支持的图片格式", code="workspace_not_image"
        )
    return {
        "data": data,
        "media_type": media_type,
        "path": _display_path(parts),
        "name": _safe_text(target.name, 512),
        "size": max(0, int(opened_st.st_size)),
        "mtime": max(0.0, float(opened_st.st_mtime)),
        "mode": format(stat.S_IMODE(opened_st.st_mode), "04o"),
    }


def _http_error(exc: WorkspaceFileError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/files")
async def workspace_files(request: Request, path: str = "/") -> dict[str, Any]:
    try:
        root = _root(request)
        return await asyncio.to_thread(_browse, root, path)
    except WorkspaceFileError as exc:
        raise _http_error(exc) from exc


@router.get("/files/raw")
async def workspace_file_raw(request: Request, path: str = "") -> Response:
    try:
        root = _root(request)
        payload = await asyncio.to_thread(_read_image, root, path)
        return Response(
            content=payload["data"],
            media_type=payload["media_type"],
            headers={
                "Cache-Control": "private, max-age=60",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except WorkspaceFileError as exc:
        raise _http_error(exc) from exc


@router.get("/files/content")
async def workspace_file_content(
    request: Request, path: str = ""
) -> dict[str, Any]:
    try:
        root = _root(request)
        return await asyncio.to_thread(_preview, root, path)
    except WorkspaceFileError as exc:
        raise _http_error(exc) from exc


__all__ = ["router", "WorkspaceFileError"]
