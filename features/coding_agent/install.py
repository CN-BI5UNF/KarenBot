"""Install and inspect native coding-agent runtimes.

Native tools need only a small helper runtime; this module intentionally does
not install the Pi/DSH/Claude Code CLIs or any TUI.  Recipes are code-owned so
the LLM can never supply a package name, path, or image.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from features.container.errors import ContainerError

from .types import (
    AGENT_MODES,
    MODE_DESCRIPTIONS,
    MODE_LABELS,
    AgentMode,
    normalize_mode,
)

RUNTIME_ROOT = "/workspace/.karen-agents"
MANIFEST_VERSION = "native-v1"


@dataclass(frozen=True, slots=True)
class AgentRecipe:
    mode: AgentMode
    label: str
    description: str
    dependencies: tuple[str, ...]
    capabilities: tuple[str, ...]


RECIPES: dict[AgentMode, AgentRecipe] = {
    "pi": AgentRecipe(
        mode="pi",
        label=MODE_LABELS["pi"],
        description=MODE_DESCRIPTIONS["pi"],
        dependencies=(),
        capabilities=("read", "write", "edit", "bash", "glob", "grep", "ls", "custom_tools"),
    ),
    "dsh": AgentRecipe(
        mode="dsh",
        label=MODE_LABELS["dsh"],
        description=MODE_DESCRIPTIONS["dsh"],
        dependencies=(),
        capabilities=(
            "read",
            "write",
            "edit",
            "bash",
            "glob",
            "grep",
            "ls",
            "apply_patch",
            "todo",
            "spawn",
            "plan",
            "custom_tools",
        ),
    ),
    "claude_code": AgentRecipe(
        mode="claude_code",
        label=MODE_LABELS["claude_code"],
        description=MODE_DESCRIPTIONS["claude_code"],
        dependencies=(),
        capabilities=(
            "read",
            "write",
            "edit",
            "bash",
            "glob",
            "grep",
            "ls",
            "apply_patch",
            "todo",
            "spawn",
            "plan",
            "notebook",
        ),
    ),
}


def _host_binary(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    candidates = [
        Path.home() / ".cherrystudio" / "bin" / name,
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _marker_file(service: Any) -> Path | None:
    paths = getattr(service, "paths", None)
    data_root = getattr(paths, "data_root", None)
    if data_root is None:
        return None
    return Path(data_root) / "container_agents.json"


def _read_markers(service: Any) -> dict[str, dict[str, Any]]:
    marker = _marker_file(service)
    if marker is None or not marker.is_file():
        return {}
    try:
        parsed = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): value
        for key, value in parsed.items()
        if isinstance(value, dict) and value.get("mode") == key
    }


def _write_marker(service: Any, manifest: dict[str, Any]) -> None:
    marker = _marker_file(service)
    if marker is None:
        return
    data = _read_markers(service)
    data[str(manifest["mode"])] = manifest
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        temp = marker.with_suffix(".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(marker)
    except OSError:
        # The container manifest is authoritative; the host marker only keeps
        # install state visible while the container is stopped.
        return


def _remove_marker(service: Any, mode: str) -> None:
    marker = _marker_file(service)
    if marker is None or not marker.is_file():
        return
    data = _read_markers(service)
    if mode not in data:
        return
    data.pop(mode, None)
    try:
        temp = marker.with_suffix(".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(marker)
    except OSError:
        return


async def _container_running(service: Any) -> bool:
    if service is None:
        return False
    state_getter = getattr(service, "container_state", None)
    if not callable(state_getter):
        return True
    try:
        return await state_getter() == "running"
    except Exception:  # noqa: BLE001 - status must stay read-only
        return False


async def _manifest(
    service: Any,
    mode: AgentMode,
    *,
    running: bool | None = None,
) -> dict[str, Any] | None:
    if service is None:
        return None
    if running is None:
        running = await _container_running(service)
    if not running:
        return _read_markers(service).get(mode)
    path = f"{RUNTIME_ROOT}/{mode}/manifest.json"
    try:
        reader = getattr(service, "read_file", None)
        if callable(reader):
            try:
                result = await reader(path, ensure_running=False)
            except TypeError:
                # Older/fake services may not accept the keyword.
                result = await reader(path)
        else:
            return _read_markers(service).get(mode)
    except ContainerError:
        # A rebuilt/recreated container can drop /workspace/.karen-agents.
        _remove_marker(service, mode)
        return None
    try:
        parsed = json.loads(str(result.get("content") or ""))
    except (json.JSONDecodeError, TypeError):
        _remove_marker(service, mode)
        return None
    if not isinstance(parsed, dict):
        _remove_marker(service, mode)
        return None
    return parsed


async def is_installed(service: Any, mode: str) -> bool:
    if service is None:
        return False
    selected = normalize_mode(mode, default="claude_code")
    if str(mode or "").strip().lower() not in AGENT_MODES:
        return False
    manifest = await _manifest(service, selected)
    return bool(manifest and manifest.get("mode") == selected)


async def status(
    service: Any,
    *,
    active_mode: str = "off",
    host_execution: str = "sandbox",
    sandbox_network: bool = True,
) -> dict[str, Any]:
    active = str(active_mode or "off").strip().lower()
    agents: list[dict[str, Any]] = []
    running = await _container_running(service) if service is not None else False
    manifests = (
        await asyncio.gather(
            *(_manifest(service, mode, running=running) for mode in AGENT_MODES)
        )
        if service is not None
        else [None] * len(AGENT_MODES)
    )
    for mode, manifest in zip(AGENT_MODES, manifests, strict=True):
        recipe = RECIPES[mode]
        installed = bool(manifest and manifest.get("mode") == mode)
        agents.append(
            {
                "id": mode,
                "label": recipe.label,
                "description": recipe.description,
                "installed": installed,
                "active": installed and active == mode,
                "version": str(manifest.get("version") or "") if manifest else "",
                "installed_at": manifest.get("installed_at") if manifest else None,
                "dependencies": list((manifest or {}).get("dependencies") or []),
                "capabilities": list(recipe.capabilities),
                "error": "",
            }
        )
    return {
        "ok": True,
        "active": active if active in AGENT_MODES else "off",
        "agents": agents,
        "host": {
            "mode": "claude_code",
            "label": "Claude Code（本机）",
            "description": "本机固定使用 Claude Code 语义；可选择沙箱联网或直接控制整台电脑。",
            "execution_mode": host_execution if host_execution in {"sandbox", "host"} else "sandbox",
            "sandbox_network": bool(sandbox_network),
            "installed": True,
        },
    }


async def install(
    service: Any,
    mode: str,
) -> dict[str, Any]:
    selected = normalize_mode(mode, default="claude_code")
    if str(mode or "").strip().lower() not in AGENT_MODES:
        raise ContainerError("未知 Agent 模式", code="container_agent_mode_invalid")
    if service is None:
        raise ContainerError("容器功能未启用", code="container_disabled")
    await service.ensure_running()
    root = f"{RUNTIME_ROOT}/{selected}"
    prepared = await service.exec(f"mkdir -p {root}/bin", timeout_seconds=15)
    if not prepared.get("ok"):
        raise ContainerError(
            "无法创建容器 Agent 运行时目录",
            code="container_agent_install_failed",
        )
    installed_deps: list[str] = []
    for dependency in RECIPES[selected].dependencies:
        source = _host_binary(dependency)
        if source is None:
            continue
        target = f"{root}/bin/{dependency}"
        try:
            await service.copy_host_file(source, target, executable=True)
        except ContainerError:
            continue
        installed_deps.append(dependency)
    manifest = {
        "mode": selected,
        "version": MANIFEST_VERSION,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "dependencies": installed_deps,
        "architecture": "native",
        "note": "Native tool semantics; no TUI/GUI/CLI agent runtime installed.",
    }
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    written = await service.agent_helper(
        "write",
        {"path": f".karen-agents/{selected}/manifest.json", "content": content},
        timeout_seconds=30,
    )
    if not written.get("ok"):
        raise ContainerError(
            "写入容器 Agent manifest 失败",
            code="container_agent_install_failed",
        )
    _write_marker(service, manifest)
    return {
        "ok": True,
        "mode": selected,
        "manifest": manifest,
        "status": await status(service, active_mode=selected),
    }


async def uninstall(service: Any, mode: str) -> dict[str, Any]:
    selected = normalize_mode(mode, default="claude_code")
    if str(mode or "").strip().lower() not in AGENT_MODES:
        raise ContainerError("未知 Agent 模式", code="container_agent_mode_invalid")
    if service is None:
        raise ContainerError("容器功能未启用", code="container_disabled")
    result = await service.exec(
        f"rm -rf {RUNTIME_ROOT}/{selected}",
        timeout_seconds=30,
    )
    if not result.get("ok"):
        raise ContainerError(
            "卸载容器 Agent 运行时失败",
            code="container_agent_uninstall_failed",
        )
    _remove_marker(service, selected)
    return {"ok": True, "mode": selected, "removed": True}


def mode_info(mode: str) -> dict[str, Any]:
    selected = normalize_mode(mode, default="claude_code")
    recipe = RECIPES[selected]
    return {
        "id": selected,
        "label": recipe.label,
        "description": recipe.description,
        "dependencies": list(recipe.dependencies),
        "capabilities": list(recipe.capabilities),
    }


def host_runtime_status(execution_mode: str, sandbox_network: bool) -> dict[str, Any]:
    rg = _host_binary("rg")
    return {
        "mode": "claude_code",
        "execution_mode": execution_mode,
        "sandbox_network": bool(sandbox_network),
        "rg_available": rg is not None,
        "rg_path": str(rg) if rg is not None else "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "time_unix": time.time(),
    }


__all__ = [
    "AGENT_MODES",
    "MANIFEST_VERSION",
    "RECIPES",
    "RUNTIME_ROOT",
    "host_runtime_status",
    "install",
    "mode_info",
    "status",
    "uninstall",
]
