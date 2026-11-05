"""WebUI API for the built-in Docker container feature."""

from __future__ import annotations

import asyncio
import logging
import posixpath
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from features.coding_agent import AGENT_MODES
from features.coding_agent import install as agent_install
from features.container import ContainerError
from features.container.admin import admin_capabilities
from webui.config_edit import apply_validated
from webui.file_types import image_media_type

from .deps import require_runtime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/container", tags=["container"])


def _service(request: Request) -> Any:
    rt = require_runtime(request)
    service = getattr(rt, "container", None)
    if service is None:
        raise HTTPException(status_code=503, detail="容器服务尚未就绪")
    return service


def _workspace_file_path(path: str) -> str:
    """The WebUI file manager is restricted to the container workspace."""
    text = str(path or "").strip()
    if not text or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "container_path_invalid",
                "message": "容器文件路径无效",
            },
        )
    if ".." in text.split("/"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "container_path_forbidden",
                "message": "容器文件路径不允许 ..",
            },
        )
    normalized = posixpath.normpath(text)
    if normalized != "/workspace" and not normalized.startswith("/workspace/"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "container_path_forbidden",
                "message": "文件管理器仅允许访问容器 /workspace",
            },
        )
    return normalized


def _http_error(exc: ContainerError) -> HTTPException:
    detail: dict[str, Any] = {
        "code": exc.code,
        "message": exc.safe_message(),
    }
    if exc.details:
        detail["details"] = exc.details
    return HTTPException(status_code=400, detail=detail)


@router.get("/status")
async def container_status(request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        status = await service.status(public=False)
    except ContainerError as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "status": status}


@router.get("/storage")
async def container_storage(request: Request) -> dict[str, Any]:
    service = _service(request)
    status = service.storage.status(include_host_paths=True)
    return {
        "ok": True,
        "storage": status.as_dict(include_host_paths=True),
        "setup": service.storage.setup_commands(),
        "admin": admin_capabilities(service.platform_name),
    }


@router.post("/storage/setup")
async def container_storage_setup(
    request: Request,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict[str, Any]:
    """One-time C storage setup.

    The request may contain ``password`` for Linux sudo. It is consumed in
    memory, sent only to ``sudo -S`` stdin, and never logged or returned.
    Windows ignores it and uses the UAC prompt instead.
    """
    service = _service(request)
    data = payload or {}
    password = data.get("password")
    if password is not None and not isinstance(password, str):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "container_admin_password_invalid",
                "message": "密码格式无效",
            },
        )
    try:
        return await service.setup_storage(password=password)
    except ContainerError as exc:
        raise _http_error(exc) from exc


@router.get("/files")
async def container_files(
    request: Request,
    path: str = "/workspace",
) -> dict[str, Any]:
    service = _service(request)
    try:
        return await service.browse_files(_workspace_file_path(path))
    except ContainerError as exc:
        raise _http_error(exc) from exc


@router.get("/files/content")
async def container_file_content(
    request: Request,
    path: str = "",
) -> dict[str, Any]:
    service = _service(request)
    try:
        return await service.preview_file(_workspace_file_path(path))
    except ContainerError as exc:
        raise _http_error(exc) from exc


@router.get("/files/raw")
async def container_file_raw(request: Request, path: str = "") -> Response:
    service = _service(request)
    try:
        payload = await service.read_image(_workspace_file_path(path))
        media_type = image_media_type(payload["data"])
        if media_type is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "container_not_image",
                    "message": "该文件不是支持的图片格式",
                },
            )
        return Response(
            content=payload["data"],
            media_type=media_type,
            headers={
                "Cache-Control": "private, max-age=60",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except ContainerError as exc:
        raise _http_error(exc) from exc


@router.post("/test")
async def container_test(request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        result = await service.exec("printf karen-container-ok", timeout_seconds=15)
    except ContainerError as exc:
        raise _http_error(exc) from exc
    return {"ok": bool(result.get("ok")), "result": result}


@router.post("/reset")
async def container_reset(request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        return await service.reset()
    except ContainerError as exc:
        raise _http_error(exc) from exc


class AgentHostConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_mode: Literal["sandbox", "host"]
    sandbox_network: bool = True


def _agent_config(rt: Any) -> Any:
    container_cfg = getattr(rt.config.features, "container", None)
    return getattr(container_cfg, "agent", None)


async def _agent_status(rt: Any) -> dict[str, Any]:
    service = getattr(rt, "container", None)
    cfg = _agent_config(rt)
    active = str(getattr(cfg, "active_mode", "off") or "off")
    host_execution = str(getattr(cfg, "host_execution", "sandbox") or "sandbox")
    sandbox_network = bool(getattr(cfg, "sandbox_network", True))
    try:
        data = await agent_install.status(
            service,
            active_mode=active,
            host_execution=host_execution,
            sandbox_network=sandbox_network,
        )
    except ContainerError as exc:
        raise _http_error(exc) from exc
    data["host_runtime"] = agent_install.host_runtime_status(
        host_execution, sandbox_network
    )
    return data


@router.get("/agents")
async def container_agents(request: Request) -> dict[str, Any]:
    rt = require_runtime(request)
    return await _agent_status(rt)


@router.post("/agents/{mode}/install")
async def container_agent_install(request: Request, mode: str) -> dict[str, Any]:
    if mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail="未知 Agent 模式")
    rt = require_runtime(request)
    service = getattr(rt, "container", None)
    try:
        result = await agent_install.install(service, mode)
    except ContainerError as exc:
        raise _http_error(exc) from exc
    result["status"] = await _agent_status(rt)
    return result


@router.delete("/agents/{mode}")
async def container_agent_uninstall(request: Request, mode: str) -> dict[str, Any]:
    if mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail="未知 Agent 模式")
    rt = require_runtime(request)
    cfg = _agent_config(rt)
    if str(getattr(cfg, "active_mode", "off")) == mode:
        raise HTTPException(
            status_code=409,
            detail={"code": "agent_mode_active", "message": "先停用当前 Agent 模式再卸载"},
        )
    try:
        result = await agent_install.uninstall(getattr(rt, "container", None), mode)
    except ContainerError as exc:
        raise _http_error(exc) from exc
    result["status"] = await _agent_status(rt)
    return result


@router.post("/agents/{mode}/activate")
async def container_agent_activate(request: Request, mode: str) -> dict[str, Any]:
    if mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail="未知 Agent 模式")
    rt = require_runtime(request)
    service = getattr(rt, "container", None)
    if not await agent_install.is_installed(service, mode):
        raise HTTPException(
            status_code=409,
            detail={"code": "agent_mode_not_installed", "message": "该 Agent 模式尚未安装"},
        )
    host = request.app.state.host
    try:
        apply_validated(
            rt.config,
            lambda draft: setattr(
                draft.features.container.agent, "active_mode", mode
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"配置不合法：{exc}") from exc
    await asyncio.to_thread(host.save_config)
    return {"ok": True, "active": mode, "status": await _agent_status(rt)}


@router.post("/agents/deactivate")
async def container_agent_deactivate(request: Request) -> dict[str, Any]:
    rt = require_runtime(request)
    host = request.app.state.host
    apply_validated(
        rt.config,
        lambda draft: setattr(draft.features.container.agent, "active_mode", "off"),
    )
    await asyncio.to_thread(host.save_config)
    return {"ok": True, "active": "off", "status": await _agent_status(rt)}


@router.patch("/agents/host")
async def container_agent_host(
    request: Request,
    payload: Annotated[AgentHostConfigPayload, Body()],
) -> dict[str, Any]:
    rt = require_runtime(request)
    host = request.app.state.host
    apply_validated(
        rt.config,
        lambda draft: (
            setattr(
                draft.features.container.agent,
                "host_execution",
                payload.execution_mode,
            ),
            setattr(
                draft.features.container.agent,
                "sandbox_network",
                bool(payload.sandbox_network),
            ),
        ),
    )
    await asyncio.to_thread(host.save_config)
    return {"ok": True, "status": await _agent_status(rt)}
