"""KarenBot 工具系统。

模块组成：
    base                —— ITool / ToolContext / ToolRegistry / @tool 装饰器
    schemas             —— 全部 Pydantic args 模型
    message_builder     —— 表情包/CQ 码/打字延迟等消息辅助
    messaging           —— send_private / send_group / recall / upload_file
    memory_tools        —— save / update / delete_important_memory
    platform_tools      —— list_contacts / get_user_info / get_forward_msg /
                           set_*_add_request / summarize_chat_history /
                           summarize_conversation / recall_history
    agent_task_tools    —— start_agent_task 后台子 Agent 资料处理
    control_tools       —— no_action / schedule_wakeup / chat_selection /
                           group_trigger_window
    persona_tools       —— eat / sleep / work 人格状态工具
    feature_tools       —— describe_image / web_search / get_weather
    toolset_tools       —— list_toolsets / load_toolset（工具集双层路由）

公开 API：
    ToolContext         —— 给 AgentRunner 用的执行上下文
    ToolRegistry        —— 工具集合
    build_default_registry(config)
                        —— 构造稳定工具集合的工厂
    get_default_specs() —— 全部已注册的工具规格
"""

from __future__ import annotations

import logging
from dataclasses import replace

# 导入各模块的副作用：注册装饰器把工具加入全局列表
from . import (  # noqa: F401
    agent_task_tools,
    container_tools,
    control_tools,
    emoji_tools,
    feature_tools,
    group_admin_tools,
    knowledge_tools,
    memory_tools,
    messaging,
    persona_tools,
    platform_tools,
    qq_action_tools,
    slang_tools,
    tool_search_tools,
    toolset_tools,
    workspace_tools,
)
from .base import (
    DEFAULT_NO_FEEDBACK_TOOLS,
    AgentTaskCallback,
    IVisionService,
    IWeatherService,
    IWebSearchService,
    ToolContext,
    ToolRegistry,
    ToolSchemaMode,
    ToolSpec,
    WakeupCallback,
    clear_default_registry,
    get_default_specs,
    tool,
)
from .message_builder import (
    FORBIDDEN_TAGS,
    build_emoji_hint,
    build_message_action,
    contains_forbidden,
    list_emoji_files,
    list_emoji_names,
    resolve_emoji_path,
    resolve_send_image_ref,
    typing_delay,
)
from .toolsets import (
    META_TOOL_NAMES,
    TOOLSETS,
    ToolsetSession,
    toolsets_for_tool,
    unclassified_tools,
)

logger = logging.getLogger(__name__)


__all__ = [
    # base
    "ToolContext",
    "ToolRegistry",
    "ToolSpec",
    "ToolSchemaMode",
    "WakeupCallback",
    "IVisionService",
    "IWebSearchService",
    "IWeatherService",
    "DEFAULT_NO_FEEDBACK_TOOLS",
    "AgentTaskCallback",
    "tool",
    "get_default_specs",
    "clear_default_registry",
    # message_builder
    "FORBIDDEN_TAGS",
    "build_emoji_hint",
    "build_message_action",
    "contains_forbidden",
    "list_emoji_files",
    "list_emoji_names",
    "resolve_emoji_path",
    "resolve_send_image_ref",
    "typing_delay",
    # factory
    "build_default_registry",
    "MEMORY_FILE_TOOLS",
    "MEMORY_TOOLS",
    "PLATFORM_OPTIONAL_TOOLS",
    "FEATURE_TOOL_FEATURES",
    "FULL_SCHEMA_TOOLS",
    "STUB_SCHEMA_TOOLS",
    "TOOLSETS",
    "ToolsetSession",
]


# ============================================================
# 工厂：按配置决定启用工具集合
# ============================================================


MEMORY_TOOLS: set[str] = {
    "save_important_memory",
    "update_important_memory",
    "delete_important_memory",
}
"""长期重要记忆工具。RAG 只是历史召回，不再替代 important.json。"""

# 兼容旧测试/旧导入名。
MEMORY_FILE_TOOLS = MEMORY_TOOLS


PLATFORM_OPTIONAL_TOOLS: set[str] = {
    "set_friend_add_request",
    "set_group_add_request",
}
"""依赖白名单模式的工具——whitelist.mode == "verify" 时才有意义。
其它模式下保留注册，仅记录警告。"""


FEATURE_TOOL_FEATURES: dict[str, str] = {
    "describe_image": "vision",
    "web_search": "web_search",
    "web_fetch": "web_search",
    "get_weather": "weather",
    "send_voice_message": "tts",
    "container": "container",
}
"""feature 工具名 → features 字典里的字段名。"""


FULL_SCHEMA_TOOLS: set[str] = {
    "send_private_messages",
    "send_group_message",
    "commit_send_attempt",
    "no_action",
    "save_important_memory",
    "update_important_memory",
    "delete_important_memory",
    "get_recent_chat_messages",
    "get_forward_msg",
    "recall_message",
    "describe_image",
    "tool_search",
    "schedule_wakeup",
    "list_contacts",
    "get_user_info",
    "get_group_self_role",
    "get_msg",
    "send_poke",
    "set_msg_emoji_like",
    "set_friend_add_request",
    "set_group_add_request",
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "delete_file",
    "run_python",
    "web_search",
    "web_fetch",
    "get_weather",
    "lookup_slang",
    "list_knowledge_notes",
    "eat",
    "sleep",
    "work",
    "chat_selection",
}
"""常驻完整 schema 工具（full profile 回滚用）。"""


COMPACT_SCHEMA_TOOLS: set[str] = {
    "send_private_messages",
    "send_group_message",
    "commit_send_attempt",
    "no_action",
    "save_important_memory",
    "update_important_memory",
    "delete_important_memory",
    "get_recent_chat_messages",
    "describe_image",
    "web_search",
    "lookup_slang",
    "list_knowledge_notes",
    "tool_search",
    "container",
    "work",
}
"""compact profile 下直接暴露核心字段的工具。

其余工具全部降为 stub，模型需要时先 tool_search。依据真实调用频率选择：
这些覆盖了绝大多数主流程调用，低频/高风险工具按需展开。知识/黑话现在改为
按需查询，所以 lookup_slang 和 list_knowledge_notes 直接暴露。
"""


_COMPACT_SHORT_DESCRIPTIONS: dict[str, str] = {
    "send_private_messages": "发送私聊消息；targets 按 order 排序，delay 控制间隔。",
    "send_group_message": "发送群消息；targets 按 order 排序，delay 控制间隔。",
    "commit_send_attempt": "提交 needs_review 的发送尝试；同一 attempt 只能提交一次。",
    "no_action": "本轮不操作，结束回复。",
    "save_important_memory": "保存一条长期重要记忆。",
    "update_important_memory": "更新已有重要记忆。",
    "delete_important_memory": "删除重要记忆。",
    "get_recent_chat_messages": "读取当前会话最近的真实消息窗口。",
    "describe_image": "理解图片内容或提取图中文字。",
    "web_search": "联网搜索实时/最新信息。",
    "lookup_slang": "查询当前群已确认的黑话/缩写/群梗。",
    "list_knowledge_notes": "按需查询知识库中的热梗/事实笔记。",
    "tool_search": "查询工具参数、完整 schema、示例与风险；路由模式会标注所属工具集和加载状态。",
    "work": "进入自主工作状态；期间暂存 @/私聊，到时自动退出。",
    "group_trigger_window": "管理按群 @ 触发窗口：open/extend/close/status，最多同时 2 个群；可附带被过滤聊天记录。",
    "list_toolsets": "列出可加载的工具集；按任务选择 1-2 个后调用 load_toolset，核心工具已可用。",
    "load_toolset": "加载一个工具集（一次一个）；下一次请求出现其工具，本会话内保持。",
}


_COMPACT_HIDDEN_FIELDS: dict[str, list[str]] = {
    "send_private_messages": [
        "reviewed_until_seq",
        "review_policy",
        "delivery_interrupt_policy",
        "ignore_review_interrupts",
        "responding_to_message_ids",
        "reply_to_message_id",
        "reason",
    ],
    "send_group_message": [
        "reviewed_until_seq",
        "review_policy",
        "delivery_interrupt_policy",
        "ignore_review_interrupts",
        "responding_to_message_ids",
        "reply_to_message_id",
        "reason",
    ],
    "commit_send_attempt": [
        "reviewed_until_seq",
        "delivery_interrupt_policy",
        "reply_to_message_id",
        "ignore_review_interrupts",
        "reason",
    ],
    "save_important_memory": ["pinned"],
    "update_important_memory": ["pinned", "reason"],
    "delete_important_memory": ["keyword"],
    "get_recent_chat_messages": ["include_raw", "before_msg_id"],
    "describe_image": ["prompt"],
    "tool_search": ["intent"],
}


def _routed_short_description(spec: ToolSpec) -> str:
    """Describe a loaded toolset tool without the compact stub wording.

    Routed mode exposes compact schemas for loaded tools directly, so telling
    the model to call tool_search just to call the tool would be misleading.
    Prefer the curated compact/stub summaries when they are descriptive, and
    otherwise use a bounded first sentence of the full description.
    """
    candidates = (
        _COMPACT_SHORT_DESCRIPTIONS.get(spec.name),
        _STUB_SHORT_DESCRIPTIONS.get(spec.name),
        spec.short_description,
        spec.description,
    )
    for candidate in candidates:
        text = " ".join(str(candidate or "").split()).strip()
        if not text:
            continue
        if (
            "tool_search" in text
            and not spec.name.startswith("tool")
            and spec.name not in META_TOOL_NAMES
        ):
            continue
        if len(text) > 140:
            text = text[:137].rstrip() + "..."
        return text
    fallback = " ".join(str(spec.description or "").split()).strip()
    if not fallback:
        return spec.name
    return fallback[:137].rstrip() + "..." if len(fallback) > 140 else fallback


_PERSONA_CONDITIONAL_TOOLS: dict[str, tuple[str, str]] = {
    "sleep": ("energy", "tool"),
    "eat": ("satiety", "tool"),
}


STUB_SCHEMA_TOOLS: set[str] = {
    "start_agent_task",
    "summarize_chat_history",
    "summarize_conversation",
    "filter_archive_records",
    "recall_history",
    "upload_file",
    "send_voice_message",
    "set_group_kick",
    "set_group_ban",
    "set_group_whole_ban",
    "set_group_leave",
    "list_emoji",
    "save_emoji_from_url",
    "save_emoji_from_workspace",
    "rename_emoji",
    "delete_emoji",
    "save_knowledge_note",
    "research_web_to_prompt",
    "delete_knowledge_note",
}
"""低频/高风险/大 schema 工具：常驻名称与简述，调用前通过 tool_search 查询参数摘要。

``lookup_slang`` / ``list_knowledge_notes`` 是核心按需查询工具，直接暴露完整/紧凑
schema，不走 tool_search，否则模型要为了查一条知识多花一轮调用。
"""


_STUB_SHORT_DESCRIPTIONS: dict[str, str] = {
    "start_agent_task": "后台子 Agent 整理资料、提取或转换内容。",
    "summarize_chat_history": "拉取并总结指定群的近期消息。",
    "summarize_conversation": "总结本地私聊/群聊历史。",
    "filter_archive_records": "按关键词、时间、会话筛选归档记录。",
    "recall_history": "检索归档中的旧对话原文。",
    "upload_file": "把 workspace 文件发送到 QQ。",
    "send_voice_message": "用 TTS 合成语音并发送。",
    "set_group_kick": "高风险：把成员踢出群，需明确指令。",
    "set_group_ban": "高风险：禁言成员，需明确时长。",
    "set_group_whole_ban": "高风险：开启/关闭全员禁言。",
    "set_group_leave": "高风险：让机器人退出当前群。",
    "schedule_wakeup": "延迟唤醒自己或到点发送消息。",
    "read_file": "读取 workspace 文本文件，可分页。",
    "write_file": "创建或覆盖 workspace 文本文件。",
    "edit_file": "按唯一字符串替换文件内容。",
    "list_files": "列出 workspace 文件，支持 glob。",
    "delete_file": "删除 workspace 内的单个文件。",
    "run_python": "在 workspace 执行 Python（优先 bubblewrap 沙箱），默认 30 秒超时。",
    "get_user_info": "查询指定 QQ 用户的公开资料。",
    "get_forward_msg": "展开合并转发消息的内容。",
    "get_group_self_role": "查询机器人在群里的身份权限。",
    "recall_message": "撤回 2 分钟内发出的消息。",
    "set_friend_add_request": "处理好友添加请求。",
    "set_group_add_request": "处理加群申请或邀请。",
    "list_contacts": "查询好友、群或群成员列表。",
    "send_poke": "向明确用户发送戳一戳。",
    "set_msg_emoji_like": "给消息添加或取消表情回应。",
    "get_msg": "读取一条已知消息的详情。",
    "get_weather": "查询城市实时天气与多日预报。",
    "eat": "记录人格开始进食。",
    "sleep": "记录人格开始睡眠或休息。",
    "list_emoji": "列出可发送的表情包名称。",
    "save_emoji_from_url": "把网络图片保存为表情包。",
    "save_emoji_from_workspace": "把消息图片保存为表情包。",
    "rename_emoji": "给已有表情包改名。",
    "delete_emoji": "删除一个表情包，不可恢复。",
    "save_knowledge_note": "保存已核对的知识或热梗笔记。",
    "research_web_to_prompt": "联网研究主题并整理成知识笔记。",
    "delete_knowledge_note": "删除一条知识笔记。",
    "web_fetch": "读取单个公开网页的正文。",
    "chat_selection": "暂停、恢复或限定群聊接收范围。",
    "group_trigger_window": "打开、延长或关闭群聊 @ 触发窗口。",
}


_STUB_RISK_LEVELS: dict[str, str] = {
    "upload_file": "medium",
    "send_voice_message": "medium",
    "start_agent_task": "medium",
    "set_group_kick": "high",
    "set_group_ban": "high",
    "set_group_whole_ban": "high",
    "set_group_leave": "high",
    "write_file": "medium",
    "delete_file": "medium",
    "run_python": "high",
    "schedule_wakeup": "medium",
    "save_emoji_from_url": "medium",
    "save_emoji_from_workspace": "medium",
    "rename_emoji": "medium",
    "delete_emoji": "high",
    "save_knowledge_note": "medium",
    "research_web_to_prompt": "medium",
    "delete_knowledge_note": "medium",
    "web_fetch": "medium",
}


def build_default_registry(config) -> ToolRegistry:
    """根据 RootConfig 构造稳定工具 Registry。

    规则：
        - messaging 工具（send_*/recall）：始终启用
        - upload_file：始终注册为 stub，执行受 ctx.workspace_dir / adapter 进一步限制
        - memory 工具：始终启用；RAG 是历史召回，不替代 important.json
        - platform 工具：始终启用（按需）
        - control 工具：始终启用
        - feature 工具：始终注册；执行时按 ctx 是否注入 service 返回成功或未启用
        - 低频/高风险/大 schema 工具：始终注册为 stub，通过 tool_search 查询参数摘要

    Args:
        config: RootConfig 实例

    Returns:
        ToolRegistry 实例
    """
    specs = list(get_default_specs())
    memory_mode = config.features.long_term_memory.mode
    features = config.features
    persona_management = getattr(config, "persona_management", None)
    persona_enabled = bool(getattr(persona_management, "enabled", False))
    physiology = getattr(persona_management, "physiology", None)
    energy_mode = _persona_physiology_mode(physiology, "energy")
    satiety_mode = _persona_physiology_mode(physiology, "satiety")
    persona_modes = {
        "energy": energy_mode,
        "satiety": satiety_mode,
    }

    schema_profile = str(
        getattr(getattr(config, "behavior", None), "tool_schema_profile", "compact")
        or "compact"
    )
    routed = schema_profile == "routed"
    unmapped = unclassified_tools({spec.name for spec in specs})
    if unmapped:
        raise ValueError(
            "以下工具没有归入任何工具集：" + ", ".join(sorted(unmapped))
        )
    container_enabled = bool(
        getattr(getattr(features, "container", None), "enabled", False)
    )
    enabled: list[ToolSpec] = []
    for spec in specs:
        if spec.name in META_TOOL_NAMES and not routed:
            continue
        spec = replace(
            spec,
            toolsets=list(toolsets_for_tool(spec.name)),
        )
        if spec.name in _PERSONA_CONDITIONAL_TOOLS:
            mode_name, required_mode = _PERSONA_CONDITIONAL_TOOLS[spec.name]
            if not persona_enabled or persona_modes[mode_name] != required_mode:
                continue
        if spec.name == "work" and not persona_enabled:
            continue
        if spec.name == "container" and not container_enabled:
            continue

        configured = spec
        if routed:
            # Routed mode: every available tool uses a compact schema, but only
            # core tools and loaded toolsets are exposed by the schema provider.
            configured = replace(
                spec,
                schema_mode=ToolSchemaMode.COMPACT,
                short_description=_routed_short_description(spec),
                compact_hidden_fields=list(
                    _COMPACT_HIDDEN_FIELDS.get(spec.name, [])
                ),
                risk_level=_STUB_RISK_LEVELS.get(spec.name, spec.risk_level),
            )
        elif schema_profile == "full":
            # 旧行为：保留给回滚与对照测试。
            if spec.name in STUB_SCHEMA_TOOLS:
                configured = replace(
                    spec,
                    schema_mode=ToolSchemaMode.STUB,
                    short_description=_STUB_SHORT_DESCRIPTIONS.get(spec.name),
                    risk_level=_STUB_RISK_LEVELS.get(spec.name, "low"),
                    search_tags=list(spec.search_tags) or [spec.category, spec.name],
                )
            elif spec.name in FULL_SCHEMA_TOOLS:
                configured = replace(spec, schema_mode=ToolSchemaMode.FULL)
        elif spec.name in COMPACT_SCHEMA_TOOLS:
            configured = replace(
                spec,
                schema_mode=ToolSchemaMode.COMPACT,
                short_description=(
                    _COMPACT_SHORT_DESCRIPTIONS.get(spec.name)
                    or spec.short_description
                ),
                compact_hidden_fields=list(
                    _COMPACT_HIDDEN_FIELDS.get(spec.name, [])
                ),
            )
        else:
            configured = replace(
                spec,
                schema_mode=ToolSchemaMode.STUB,
                short_description=(
                    _STUB_SHORT_DESCRIPTIONS.get(spec.name)
                    or spec.short_description
                ),
                risk_level=_STUB_RISK_LEVELS.get(spec.name, spec.risk_level),
                search_tags=list(spec.search_tags) or [spec.category, spec.name],
            )
        enabled.append(configured)

    registry = ToolRegistry(enabled, schema_profile=schema_profile)
    logger.info(
        f"build_default_registry: 启用 {len(registry)} 个工具 "
        f"(schema_profile={schema_profile}, routed={routed}, memory_mode={memory_mode}, "
        f"vision={features.vision.enabled}, "
        f"web_search={features.web_search.enabled}, "
        f"weather={features.weather.enabled}, "
        f"container={container_enabled}, "
        f"persona_management={persona_enabled}, "
        f"energy_mode={energy_mode}, "
        f"satiety_mode={satiety_mode})"
    )
    return registry


def _persona_physiology_mode(physiology, name: str) -> str:
    item = physiology.get(name) if isinstance(physiology, dict) else getattr(physiology, name, None)
    if isinstance(item, dict):
        return str(item.get("mode") or "disabled")
    return str(getattr(item, "mode", "disabled") or "disabled")
