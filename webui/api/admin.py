"""Authenticated endpoints for irreversible data operations.

These routes deliberately do not use ``require_runtime``: the job endpoints must
remain reachable while Runtime is paused for a cleanup. The host-level admin
guard prevents Runtime from being restarted underneath a deletion job.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from core.destructive_admin import (
    DestructiveAdminError,
    PersonaCleanupService,
    UninstallService,
)
from memory.admin_store import AdminStore

from .deps import get_host

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin_request(request: Request) -> None:
    """Reject cross-site form/fetch attempts and require an explicit admin header."""
    if request.headers.get("x-karen-admin") != "1":
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_header_required", "message": "缺少危险操作确认头"},
        )
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        parsed = urlparse(origin)
        host = (request.headers.get("host") or "").strip()
        if parsed.scheme not in {"http", "https"} or parsed.netloc != host:
            raise HTTPException(
                status_code=403,
                detail={"code": "origin_mismatch", "message": "请求来源不匹配"},
            )
    fetch_site = (request.headers.get("sec-fetch-site") or "").strip()
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise HTTPException(
            status_code=403,
            detail={"code": "sec_fetch_cross_site", "message": "拒绝跨站危险操作"},
        )


class PersonaCleanupExecutePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=8, max_length=160)
    confirmation_token: str = Field(min_length=16, max_length=256)
    expected_generation: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)
    typed_confirmation: str = Field(min_length=1, max_length=160)
    acknowledge_destructive: bool
    create_backup: bool = False


class UninstallExecutePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=8, max_length=160)
    confirmation_token: str = Field(min_length=16, max_length=256)
    expected_generation: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)
    typed_confirmation: str = Field(min_length=1, max_length=160)
    acknowledge_destructive: bool
    create_backup: bool = False


def _http_error(exc: DestructiveAdminError) -> HTTPException:
    status = 400
    if exc.code in {"preview_not_found", "job_not_found"}:
        status = 404
    elif exc.code in {"preview_expired"}:
        status = 410
    elif exc.code in {
        "preview_already_used",
        "confirmation_token_invalid",
        "generation_conflict",
        "idempotency_conflict",
        "operation_in_progress",
        "job_not_cancellable",
        "runtime_state_changed",
        "impact_changed",
        "preview_subject_mismatch",
    }:
        status = 409
    elif exc.code in {
        "invalid_persona",
        "unsafe_target",
        "knowledge_unreadable",
        "confirmation_phrase_mismatch",
        "acknowledgement_required",
        "idempotency_required",
        "backup_requires_runtime",
        "backup_inside_target",
        "backup_not_verified",
        "unsupported_platform",
        "unsupported_launch_mode",
    }:
        status = 400
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


def _services(request: Request) -> tuple[PersonaCleanupService, UninstallService]:
    host = get_host(request)
    cached = getattr(host, "_admin_services", None)
    if cached is not None:
        return cached
    paths = host.build_paths()
    store = AdminStore(paths.MAINTENANCE_DIR / "admin.sqlite3")
    hub = getattr(request.app.state, "hub", None)

    def _exit_backend() -> None:
        host.request_stop()
        server = getattr(request.app.state, "server", None)
        if server is not None:
            server.should_exit = True

    persona = PersonaCleanupService(
        host,
        store,
        on_restarted=getattr(hub, "attach_timeline", None),
    )
    uninstall = UninstallService(
        host,
        store,
        exit_callback=_exit_backend,
    )
    cached = (persona, uninstall)
    host._admin_services = cached
    return cached


def _service(request: Request) -> PersonaCleanupService:
    return _services(request)[0]


def _uninstall_service(request: Request) -> UninstallService:
    return _services(request)[1]


@router.post(
    "/personas/{name}/cleanup/preview",
    dependencies=[Depends(require_admin_request)],
)
async def persona_cleanup_preview(request: Request, name: str) -> dict[str, Any]:
    try:
        return await _service(request).preview(name)
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/personas/{name}/cleanup/execute",
    dependencies=[Depends(require_admin_request)],
)
async def persona_cleanup_execute(
    request: Request,
    name: str,
    payload: Annotated[PersonaCleanupExecutePayload, Body()],
) -> JSONResponse:
    try:
        job, created = await _service(request).execute(
            name,
            preview_id=payload.preview_id,
            confirmation_token=payload.confirmation_token,
            expected_generation=payload.expected_generation,
            idempotency_key=payload.idempotency_key,
            typed_confirmation=payload.typed_confirmation,
            acknowledge_destructive=payload.acknowledge_destructive,
            create_backup=payload.create_backup,
        )
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc
    job["created"] = bool(created)
    return JSONResponse(status_code=202, content=job)


@router.post(
    "/uninstall/preview",
    dependencies=[Depends(require_admin_request)],
)
async def uninstall_preview(request: Request) -> dict[str, Any]:
    try:
        return await _uninstall_service(request).preview()
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/uninstall/execute",
    dependencies=[Depends(require_admin_request)],
)
async def uninstall_execute(
    request: Request,
    payload: Annotated[UninstallExecutePayload, Body()],
) -> JSONResponse:
    try:
        job, created = await _uninstall_service(request).execute(
            preview_id=payload.preview_id,
            confirmation_token=payload.confirmation_token,
            expected_generation=payload.expected_generation,
            idempotency_key=payload.idempotency_key,
            typed_confirmation=payload.typed_confirmation,
            acknowledge_destructive=payload.acknowledge_destructive,
            create_backup=payload.create_backup,
        )
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc
    job["created"] = bool(created)
    return JSONResponse(status_code=202, content=job)


@router.get("/jobs", dependencies=[Depends(require_admin_request)])
async def list_jobs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return {"jobs": await _service(request).list_jobs(limit)}
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc


@router.get("/jobs/{job_id}", dependencies=[Depends(require_admin_request)])
async def get_job(request: Request, job_id: str) -> dict[str, Any]:
    try:
        job = await _service(request).get_job(job_id)
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "job_not_found", "message": "任务不存在"},
        )
    return job


@router.post(
    "/jobs/{job_id}/cancel",
    dependencies=[Depends(require_admin_request)],
)
async def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
    try:
        return await _service(request).cancel(job_id)
    except DestructiveAdminError as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
