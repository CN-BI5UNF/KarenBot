"""角色页接口 —— 列人格、切换、新建/生成、改写、复制、导入导出、删除。

对应原 GUI 的 ``ui/dashboard/personas_page.py``。人格目录约定见
``agents/persona_loader.py``：``personas/<name>/persona_prompt.py``。

生成 / 改写走 ``webui/persona_admin.py``（纯函数，好单测）；它复用
``agents/persona_gen_agent.py`` 的 ``PersonaGenAgent``——那套生成器一直是完整的，
只是此前 WebUI 没有入口。

注意路由声明顺序：``/draft``、``/refine`` 这类静态段必须排在 ``/{name}`` 之前，
否则会被路径参数吃掉。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from core.persona_image import PersonaImageError, PersonaImageStore
from utils.image_contracts import MAX_IMAGE_BYTES
from webui import persona_admin
from webui.persona_admin import PersonaAdminError

from .deps import require_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/personas", tags=["personas"])

BUILTIN_PERSONAS = {"大肥鱼", "deepseek"}


def _fail(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _persona_dirs(paths: Any) -> list[Path]:
    root = Path(paths.PERSONAS_DIR)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir() and (p / "persona_prompt.py").is_file()),
        key=lambda p: p.name,
    )


def _persona_images(rt: Any) -> PersonaImageStore:
    store = getattr(rt, "persona_image_store", None)
    return store if isinstance(store, PersonaImageStore) else PersonaImageStore(rt.paths)


def _safe_appearance(rt: Any, name: str) -> dict[str, Any] | None:
    try:
        return _persona_images(rt).get(name)
    except (PersonaImageError, OSError):
        return None


def _safe_appearance_count(rt: Any, name: str) -> int:
    try:
        return _persona_images(rt).count(name)
    except (PersonaImageError, OSError):
        return 0


@router.get("")
async def list_personas(request: Request) -> dict[str, Any]:
    rt = require_runtime(request)
    paths = rt.paths
    active = getattr(rt.config.persona, "active", "")
    items = []
    for directory in _persona_dirs(paths):
        name = directory.name
        items.append(
            {
                "id": name,
                "name": name,
                "active": name == active,
                "builtin": name in BUILTIN_PERSONAS,
                "path": str(directory),
                "description": _read_description(directory),
                "appearance": _safe_appearance(rt, name),
                "appearance_count": _safe_appearance_count(rt, name),
            }
        )
    return {"personas": items, "active": active}


@router.get("/{name}/appearance")
async def get_persona_appearance(request: Request, name: str) -> dict[str, Any]:
    rt = require_runtime(request)
    store = _persona_images(rt)
    try:
        images = store.list_images(name)
        info = store.get(name)
    except PersonaImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(status_code=404, detail="该人格还没有角色形象")
    return {
        "ok": True,
        "appearance": info,
        "cover_id": info.get("id"),
        "images": images,
    }


@router.get("/{name}/appearance/file")
async def get_persona_appearance_file(
    request: Request,
    name: str,
    image_id: str | None = Query(None),
) -> FileResponse:
    rt = require_runtime(request)
    try:
        store = _persona_images(rt)
        path = store.resolve(name, image_id)
        info = store.get(name, image_id) or {}
    except PersonaImageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=str(info.get("mime") or "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/{name}/appearance")
async def upload_persona_appearance(
    request: Request,
    name: str,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    rt = require_runtime(request)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"图片超过 {MAX_IMAGE_BYTES // 1024 // 1024} MiB 上限",
        )
    try:
        info = await _persona_images(rt).save(name, data)
    except PersonaImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "appearance": info,
        "message": f"已添加 {name} 的角色形象",
    }


@router.post("/{name}/appearance/{image_id}/cover")
async def set_persona_appearance_cover(
    request: Request,
    name: str,
    image_id: str,
) -> dict[str, Any]:
    rt = require_runtime(request)
    try:
        info = _persona_images(rt).set_cover(name, image_id)
    except PersonaImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "appearance": info, "message": "已设为角色形象预览图"}


@router.delete("/{name}/appearance/{image_id}")
async def delete_persona_appearance_image(
    request: Request,
    name: str,
    image_id: str,
) -> dict[str, Any]:
    rt = require_runtime(request)
    try:
        result = _persona_images(rt).delete(name, image_id)
    except PersonaImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        **result,
        "message": "已删除该角色形象",
    }


@router.delete("/{name}/appearance")
async def delete_persona_appearance(request: Request, name: str) -> dict[str, Any]:
    rt = require_runtime(request)
    try:
        result = _persona_images(rt).delete(name)
    except PersonaImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        **result,
        "message": "已删除角色形象" if result.get("deleted") else "该人格没有可删除的角色形象",
    }


def _read_description(directory: Path) -> str:
    """从 persona_prompt.py 里抠一句简介，读不到就算了。"""
    readme = directory / "README.md"
    if readme.is_file():
        try:
            for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line[:160]
        except OSError:
            pass
    return ""


# ============================================================
# 生成 / 改写（静态段，必须排在 /{name} 之前）
# ============================================================


@router.post("/draft")
async def create_draft(request: Request, payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """按简述生成初版人格。**只返回草稿，不落盘**。

    用户要先看到、可能还要反复重写，落盘由 ``POST /api/personas`` 单独做。
    """
    rt = require_runtime(request)
    try:
        return await persona_admin.generate_draft(rt, payload)
    except PersonaAdminError as e:
        raise _fail(e) from e


@router.get("/brief")
async def read_stashed_brief(request: Request) -> dict[str, Any]:
    """读向导里暂存的角色描述，供「新建角色」预填。

    向导运行时 Runtime 还没起来，生成器调不了；那份描述先落在这里，
    配置完成后由前端取走并清除，免得用户填了两遍。
    """
    rt = require_runtime(request)
    path = Path(rt.paths.DATA_DIR) / "persona_brief.json"
    if not path.is_file():
        return {"brief": None}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("暂存的角色描述读不出来，忽略", exc_info=True)
        return {"brief": None}
    return {"brief": data if isinstance(data, dict) else None}


@router.delete("/brief")
async def clear_stashed_brief(request: Request) -> dict[str, Any]:
    """用掉之后清掉暂存，避免下次新建角色又被旧描述预填。"""
    rt = require_runtime(request)
    path = Path(rt.paths.DATA_DIR) / "persona_brief.json"
    try:
        await asyncio.to_thread(path.unlink, True)
    except OSError:
        logger.debug("清除暂存角色描述失败", exc_info=True)
    return {"ok": True}


@router.post("/refine")
async def refine_draft(request: Request, payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """按反馈出修订版人格。同样不落盘，可以反复调用（``refined_count`` 递增）。"""
    rt = require_runtime(request)
    try:
        return await persona_admin.refine_draft(rt, payload)
    except PersonaAdminError as e:
        raise _fail(e) from e


@router.post("")
async def save_persona(request: Request, payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """把草稿落盘成 ``personas/<name>/persona_prompt.py``。

    覆盖已有角色时先自动备份到 ``.backups/``，响应里回备份路径。
    """
    rt = require_runtime(request)
    name = str(payload.get("name") or "").strip()
    xml = str(payload.get("xml") or "")
    raw = bool(payload.get("raw") or payload.get("mode") == "raw")
    try:
        brief = (
            persona_admin.brief_from_payload(payload)
            if (not raw and payload.get("personality"))
            else None
        )
        result = await asyncio.to_thread(
            persona_admin.save_persona,
            rt.paths,
            name,
            xml,
            brief=brief,
            overwrite=bool(payload.get("overwrite")),
            raw=raw,
            display_name=str(payload.get("display_name") or ""),
            gender=str(payload.get("gender") or ""),
            age=payload.get("age"),
            admins=payload.get("admins"),
            preserve_vars=raw or (bool(payload.get("overwrite")) and brief is None),
        )
    except PersonaAdminError as e:
        raise _fail(e) from e
    return result


@router.post("/{name}/duplicate")
async def duplicate_persona(
    request: Request, name: str, payload: Annotated[dict, Body()]
) -> dict[str, Any]:
    """复制一个角色。"""
    rt = require_runtime(request)
    new_name = str(payload.get("new_name") or "").strip()
    try:
        created = await asyncio.to_thread(
            persona_admin.duplicate_persona, rt.paths, name, new_name
        )
    except PersonaAdminError as e:
        raise _fail(e) from e
    return {"ok": True, "id": created, "message": f"已复制为 {created}"}


@router.get("/{name}/source")
async def read_prompt_source(request: Request, name: str) -> dict[str, Any]:
    """取出人格的 PERSONA_PROMPT 字面量，供「修改角色」作为改写底稿。

    与 ``/{name}/prompt`` 的区别：那条回整个 .py 源码（给人看），这条只回提示词
    本身（给模型改）。
    """
    rt = require_runtime(request)
    path = Path(rt.paths.PERSONAS_DIR) / name / persona_admin.PERSONA_FILE
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"人格 {name!r} 不存在")
    try:
        text = await asyncio.to_thread(path.read_text, "utf-8", "replace")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取失败：{e}") from e
    return {
        "id": name,
        "xml": persona_admin.extract_prompt_source(text),
        "vars": persona_admin.extract_persona_vars(text),
    }


@router.post("/{name}/activate")
async def activate(request: Request, name: str) -> dict[str, Any]:
    """切换当前人格（写配置，需要重启 Runtime 生效）。"""
    rt = require_runtime(request)
    host = request.app.state.host
    paths = rt.paths
    if not (Path(paths.PERSONAS_DIR) / name / "persona_prompt.py").is_file():
        raise HTTPException(status_code=404, detail=f"人格 {name!r} 不存在")

    rt.config.persona.active = name
    await asyncio.to_thread(host.save_config)
    logger.info("已切换人格为 %s（等待重启生效）", name)
    return {
        "ok": True,
        "message": f"已切换为 {name}，重启 Runtime 后生效",
        "needs_restart": True,
    }


@router.delete("/{name}")
async def delete_persona(request: Request, name: str) -> dict[str, Any]:
    rt = require_runtime(request)
    try:
        name = persona_admin.validate_persona_name(name)
    except PersonaAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    root = Path(rt.paths.PERSONAS_DIR)
    directory = root / name
    if name in BUILTIN_PERSONAS:
        raise HTTPException(status_code=400, detail=f"{name} 是内置人格，不能删除")
    if name == getattr(rt.config.persona, "active", ""):
        raise HTTPException(status_code=400, detail="不能删除当前正在使用的人格，请先切换")
    if directory.is_symlink():
        raise HTTPException(status_code=400, detail="拒绝删除符号链接人格目录")
    try:
        if directory.resolve().parent != root.resolve():
            raise HTTPException(status_code=400, detail="人格目录越界")
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法检查人格目录：{exc}") from exc
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"人格 {name!r} 不存在")
    await asyncio.to_thread(shutil.rmtree, directory)
    logger.info("已删除人格目录 %s", directory)
    return {"ok": True, "message": f"已删除 {name}"}


@router.get("/{name}/export")
async def export_persona(request: Request, name: str) -> FileResponse:
    """把人格目录打包成 zip 下载。"""
    rt = require_runtime(request)
    directory = Path(rt.paths.PERSONAS_DIR) / name
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"人格 {name!r} 不存在")

    def _zip() -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="karen-persona-")) / f"{name}.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in directory.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(directory.parent))
        return tmp

    archive = await asyncio.to_thread(_zip)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"{name}.zip",
    )


@router.post("/import")
async def import_persona(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """上传 zip 导入人格；目录名冲突时 ``import_persona_zip`` 会加后缀。"""
    rt = require_runtime(request)
    from agents.persona_import import import_persona_zip

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="只支持 .zip 人格包")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传内容为空")

    def _do_import() -> str:
        tmp_dir = Path(tempfile.mkdtemp(prefix="karen-persona-import-"))
        tmp_zip = tmp_dir / "persona.zip"
        tmp_zip.write_bytes(data)
        try:
            return import_persona_zip(tmp_zip, Path(rt.paths.PERSONAS_DIR))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        name = await asyncio.to_thread(_do_import)
    except Exception as e:  # noqa: BLE001
        logger.exception("导入人格失败")
        raise HTTPException(status_code=400, detail=f"导入失败：{e}") from e
    return {"ok": True, "message": f"已导入人格 {name}", "id": name}


@router.get("/{name}/prompt")
async def read_prompt(request: Request, name: str) -> dict[str, Any]:
    """读取人格提示词源码（只读预览）。"""
    rt = require_runtime(request)
    path = Path(rt.paths.PERSONAS_DIR) / name / "persona_prompt.py"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"人格 {name!r} 不存在")
    try:
        text = await asyncio.to_thread(path.read_text, "utf-8", "replace")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取失败：{e}") from e
    return {"id": name, "path": str(path), "source": text, "size": len(text)}


__all__ = ["router"]
