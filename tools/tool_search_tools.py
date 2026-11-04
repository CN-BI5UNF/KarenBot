"""工具检索入口：为 stub 工具按需返回参数摘要或完整 schema。"""

from __future__ import annotations

from .base import ToolContext, tool
from .schemas import ToolSearchArgs


@tool(
    name="tool_search",
    description=(
        "查询工具的说明、真实参数摘要/完整 JSON schema、示例和风险约束。stub 工具或"
        "不确定参数/风险时先调用；路由模式结果会标注所属工具集和是否已加载，未加载时"
        "先 load_toolset。"
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
            "tool_name": args.tool_name,
            "error": "当前运行时未注入工具注册表，无法查询工具详情",
        }
    spec = registry.get_spec(args.tool_name)
    if spec is None:
        candidates = [
            name
            for name in getattr(registry, "names", lambda: [])()
            if args.tool_name.lower() in name.lower()
        ][:10]
        return {
            "ok": False,
            "status": "not_found",
            "tool_name": args.tool_name,
            "candidates": candidates,
            "next": "请检查工具名；不要猜测不存在的工具。",
        }
    approved = ctx.extras.setdefault("tool_search_approved_tools", set())
    if isinstance(approved, set):
        approved.add(spec.name)
    result = spec.tool_search_result(detail=args.detail)
    result["intent"] = args.intent
    session = ctx.extras.get("toolset_session")
    if session is not None and hasattr(registry, "routed_tool_names"):
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
