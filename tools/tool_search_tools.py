"""ToolSearch: discover tools and load deferred schemas.

Profiles:
- compact/full: return tool details and approve a stub tool for execution.
- routed: toolset-level loading stays in ``load_toolset``; this tool only reports.
- agent: exact names or ``select`` load schemas for the next model request.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, tool
from .schemas import ToolSearchArgs


def _discover(registry: Any, query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for name in registry.names():
        spec = registry.get_spec(name)
        if spec is None:
            continue
        haystacks = [
            name.lower(),
            str(spec.description or "").lower(),
            str(spec.short_description or "").lower(),
            " ".join(str(tag).lower() for tag in spec.search_tags or []),
            " ".join(str(item).lower() for item in spec.toolsets or []),
        ]
        if not any(needle in value for value in haystacks):
            continue
        if name.lower() == needle:
            score = 0
        elif name.lower().startswith(needle):
            score = 1
        elif needle in name.lower():
            score = 2
        else:
            score = 3
        ranked.append(
            (
                score,
                name,
                {
                    "name": name,
                    "short_description": (
                        spec.short_description
                        or " ".join(str(spec.description or "").split())[:140]
                    ),
                    "risk": spec.risk_level,
                    "toolsets": list(spec.toolsets),
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:8]]


@tool(
    name="tool_search",
    description=(
        "查询工具说明、参数摘要/完整 JSON schema、示例和风险。"
        "agent 档位下，用 tool_search select=[工具名...] 加载延迟工具的 schema，"
        "下一次模型请求才能调用；用 query=关键词 发现候选，不会自动加载。"
        "compact/full 下用于解锁 stub 工具；路由模式结果会标注所属工具集和加载状态。"
    ),
    args_model=ToolSearchArgs,
    category="control",
)
async def tool_search(args: ToolSearchArgs, ctx: ToolContext) -> dict:
    registry = ctx.extras.get("tool_registry")
    if registry is None or not hasattr(registry, "get_spec"):
        return {
            "ok": False,
            "status": "unavailable",
            "error": "当前运行时未注入工具注册表，无法查询工具详情",
        }

    session = ctx.extras.get("toolset_session")
    profile = str(getattr(registry, "schema_profile", "compact"))

    if args.query:
        candidates = _discover(registry, args.query)
        loaded = set(getattr(session, "loaded_tools", set()) or set())
        for item in candidates:
            item["loaded"] = item["name"] in loaded
        return {
            "ok": True,
            "status": "discovered",
            "query": args.query,
            "candidates": candidates,
            "loaded_tools": sorted(loaded),
            "next": (
                "从候选中选 1-3 个真正需要的工具，用 tool_search "
                "select=[工具名...] 加载；加载后下一次请求出现 schema。"
                if profile == "agent"
                else "请用 tool_name 查询具体工具的完整参数。"
            ),
        }

    requested: list[str] = []
    if args.tool_name:
        requested.append(args.tool_name.strip())
    requested.extend(
        str(name).strip() for name in args.select if str(name).strip()
    )
    requested = list(dict.fromkeys(requested))
    if not requested:
        return {
            "ok": False,
            "status": "invalid_request",
            "error": "tool_name、select、query 至少提供一个",
        }

    specs = []
    missing: list[str] = []
    for name in requested:
        spec = registry.get_spec(name)
        if spec is None:
            missing.append(name)
        else:
            specs.append(spec)
    if missing:
        candidates = [
            candidate
            for name in missing
            for candidate in [
                tool_name
                for tool_name in registry.names()
                if name.lower() in tool_name.lower()
            ]
        ][:10]
        return {
            "ok": False,
            "status": "not_found",
            "tool_name": missing[0],
            "missing": missing,
            "candidates": list(dict.fromkeys(candidates)),
            "next": "请检查工具名；不要猜测不存在的工具。",
        }

    approved = ctx.extras.setdefault("tool_search_approved_tools", set())
    added: list[str] = []
    if isinstance(approved, set):
        for spec in specs:
            approved.add(spec.name)
    if profile == "agent" and session is not None:
        loader = getattr(session, "load_tool", None)
        if callable(loader):
            for spec in specs:
                if loader(spec.name):
                    added.append(spec.name)
        loaded_tools = list(getattr(session, "loaded_tool_ids", lambda: [])())
    else:
        loaded_tools = []

    if len(specs) == 1:
        spec = specs[0]
        result = spec.tool_search_result(detail=args.detail)
        result["intent"] = args.intent
        if profile == "agent" and session is not None:
            loaded = spec.name in set(loaded_tools)
            result["loaded"] = loaded
            result["loaded_tools"] = loaded_tools
            if added:
                result["added_tools"] = added
                result["next"] = (
                    "该工具的 schema 已加入下一次模型请求；现在可以直接调用。"
                    "需要更多工具时继续 select，不要一次加载全部。"
                )
            elif loaded:
                result["next"] = (
                    "该工具已加载，可直接按参数摘要调用；需要完整 JSON schema 时用 "
                    "detail=full 重新查询。"
                )
            else:
                result["next"] = (
                    "该工具尚未加载；用 tool_search select=["
                    f"{spec.name}] 加载后再调用。"
                )
        elif profile == "routed" and session is not None and hasattr(
            registry, "routed_tool_names"
        ):
            loaded = set(registry.routed_tool_names(session))
            result["loaded"] = spec.name in loaded
            result["toolsets"] = list(spec.toolsets)
            if spec.name not in loaded:
                result["next"] = (
                    "该工具尚未加载。先调用 load_toolset 加载其工具集（"
                    + "、".join(spec.toolsets or ["未知"])
                    + "），下一次模型请求才会出现该工具。"
                )
            else:
                result["next"] = (
                    "该工具已加载，可直接按参数摘要调用；需要完整 JSON schema 时用 "
                    "detail=full 重新查询。"
                )
        return result

    summaries = []
    for spec in specs:
        item = spec.tool_search_result(detail="summary")
        item["loaded"] = spec.name in set(loaded_tools)
        summaries.append(item)
    return {
        "ok": True,
        "status": "loaded" if added else "already_loaded",
        "tools": summaries,
        "added_tools": added,
        "loaded_tools": loaded_tools,
        "next": (
            "已加载的工具 schema 会出现在下一次模型请求中；直接调用即可。"
            if profile == "agent"
            else "请按摘要检查参数后调用。"
        ),
    }
