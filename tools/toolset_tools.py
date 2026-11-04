"""Layer-1 toolset routing tools: list_toolsets / load_toolset."""

from __future__ import annotations

from .base import ToolContext, tool
from .schemas import ListToolsetsArgs, LoadToolsetArgs
from .toolsets import TOOLSETS, resolve_toolset


def _registry(ctx: ToolContext):
    registry = ctx.extras.get("tool_registry")
    if registry is None or not hasattr(registry, "routed_tool_names"):
        return None
    return registry


@tool(
    name="list_toolsets",
    description=(
        "列出按需加载的工具集（第一层路由）。核心工具已直接可用；需要文件、群管理、"
        "联网等其它能力时先查本目录，按当前任务加载 1-2 个，不要一次加载全部。工具集"
        "可重叠，加载后下一次模型请求才会出现对应工具。参数细节仍可用 tool_search 查询。"
    ),
    args_model=ListToolsetsArgs,
    category="control",
    no_feedback=True,
    search_tags=["工具集", "路由", "toolsets", "load_toolset"],
)
async def list_toolsets(args: ListToolsetsArgs, ctx: ToolContext) -> dict:
    registry = _registry(ctx)
    session = ctx.extras.get("toolset_session")
    if registry is None or session is None:
        return {
            "ok": False,
            "status": "unavailable",
            "brief": "工具集路由未启用，无法列出工具集。",
            "error": "toolset routing unavailable",
        }
    available_names = set(registry.names())
    loaded = set(getattr(session, "loaded", set()) or set())
    toolsets = []
    for item in TOOLSETS:
        members = [name for name in item.tools if name in available_names]
        if not members:
            continue
        toolsets.append(
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "risk": item.risk,
                "always_on": item.always_on,
                "loaded": item.always_on or item.id in loaded,
                "tools": members,
            }
        )
    return {
        "ok": True,
        "status": "listed",
        "brief": f"共 {len(toolsets)} 个可用工具集。",
        "loaded_toolsets": sorted(loaded),
        "toolsets": toolsets,
        "next": (
            "按当前任务选择 1-2 个真正需要的工具集，调用 load_toolset(name)；核心工具"
            "已可用，不要加载全部。加载后会在下一次模型请求中出现对应工具。参数细节"
            "可用 tool_search 查询。"
        ),
    }


@tool(
    name="load_toolset",
    description=(
        "加载一个按需工具集（第一层路由）。一次加载一个；加载后下一次模型请求会包含"
        "该工具集的紧凑 schema，已加载集合在本会话内保持。未加载的工具调用会被拒绝。"
        "需要完整参数或高级字段时再用 tool_search detail=full（第二层路由）。"
    ),
    args_model=LoadToolsetArgs,
    category="control",
    no_feedback=True,
    search_tags=["工具集", "加载", "路由", "load_toolset", "toolsets"],
)
async def load_toolset(args: LoadToolsetArgs, ctx: ToolContext) -> dict:
    registry = _registry(ctx)
    session = ctx.extras.get("toolset_session")
    if registry is None or session is None:
        return {
            "ok": False,
            "status": "unavailable",
            "brief": "工具集路由未启用，无法加载工具集。",
            "error": "toolset routing unavailable",
        }
    toolset = resolve_toolset(args.name)
    if toolset is None:
        available_names = set(registry.names())
        candidates = [
            {
                "id": item.id,
                "title": item.title,
            }
            for item in TOOLSETS
            if any(name in available_names for name in item.tools)
        ]
        return {
            "ok": False,
            "status": "not_found",
            "brief": f"未知工具集：{args.name}",
            "candidates": candidates,
            "next": "请从候选工具集中选择一个 id。",
        }
    available_names = set(registry.names())
    available = [name for name in toolset.tools if name in available_names]
    if not available:
        return {
            "ok": False,
            "status": "unavailable",
            "brief": f"工具集 {toolset.id} 当前没有可用工具。",
            "toolset": toolset.id,
            "next": "该功能可能未启用；不要反复加载。",
        }
    before = set(registry.routed_tool_names(session))
    already_loaded = toolset.always_on or toolset.id in set(
        getattr(session, "loaded", set()) or set()
    )
    if not toolset.always_on:
        session.load(toolset.id)
    after = set(registry.routed_tool_names(session))
    added = [name for name in registry.names() if name in after - before]
    status = "already_loaded" if already_loaded else "loaded"
    return {
        "ok": True,
        "status": status,
        "brief": (
            f"工具集 {toolset.id} 已加载。"
            if not already_loaded
            else f"工具集 {toolset.id} 已经可用。"
        ),
        "toolset": toolset.id,
        "title": toolset.title,
        "risk": toolset.risk,
        "added_tools": added,
        "tools": available,
        "loaded_toolsets": session.loaded_ids(),
        "next": (
            "下一次模型请求会包含该工具集的工具。已加载的工具集无需重复加载；需要"
            "另一类能力时再加载对应工具集。高级字段用 tool_search detail=full 查询。"
        ),
    }
