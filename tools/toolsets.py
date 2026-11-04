"""Toolset catalog for the routed tool schema profile.

Layer 1 (coarse) is the toolset catalog: the model calls ``list_toolsets`` and
``load_toolset`` to activate a group of related tools.  Layer 2 (fine) is the
existing per-tool ``tool_search`` lookup for advanced fields and risk details.

The catalog is explicit rather than derived from ``@tool.category`` because a
tool often belongs to more than one workflow (for example ``upload_file`` is
both messaging and workspace).  Keeping the mapping in one place also lets tests
assert that every registered tool is classified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ToolsetRisk = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class Toolset:
    id: str
    title: str
    description: str
    tools: tuple[str, ...]
    risk: ToolsetRisk = "low"
    always_on: bool = False


CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # Replying and ending a turn: never worth a routing round-trip.
        "send_private_messages",
        "send_group_message",
        "commit_send_attempt",
        "no_action",
        "get_recent_chat_messages",
        # Small, high-frequency context tools.
        "save_important_memory",
        "update_important_memory",
        "delete_important_memory",
        "describe_image",
        "web_search",
        "lookup_slang",
        "list_knowledge_notes",
        "tool_search",
        # Time-sensitive group window control.
        "group_trigger_window",
        # Layer-1 routing entry points.
        "list_toolsets",
        "load_toolset",
    }
)
"""Tools always exposed in routed mode (plus meta tools)."""

META_TOOL_NAMES: frozenset[str] = frozenset({"list_toolsets", "load_toolset"})


TOOLSETS: tuple[Toolset, ...] = (
    Toolset(
        id="core",
        title="核心",
        description="回复、结束本轮、基础记忆/知识/识图、@ 触发窗口与路由入口；始终可用。",
        tools=tuple(sorted(CORE_TOOL_NAMES)),
        always_on=True,
    ),
    Toolset(
        id="control",
        title="控制与调度",
        description="定时唤醒、群聊接收范围、@ 触发窗口和 tool_search；不含文件读写。",
        tools=(
            "no_action",
            "schedule_wakeup",
            "chat_selection",
            "group_trigger_window",
            "tool_search",
            "list_toolsets",
            "load_toolset",
        ),
    ),
    Toolset(
        id="messaging",
        title="消息发送",
        description="私聊/群聊发送、撤回、上传 workspace 文件和语音；upload_file 与文件集重叠。",
        tools=(
            "send_private_messages",
            "send_group_message",
            "commit_send_attempt",
            "recall_message",
            "upload_file",
            "send_voice_message",
        ),
        risk="medium",
    ),
    Toolset(
        id="qq_info",
        title="QQ 信息",
        description="联系人、群成员、单条/转发消息、戳一戳和表情回应；以只读查询为主。",
        tools=(
            "list_contacts",
            "get_user_info",
            "get_forward_msg",
            "get_msg",
            "get_group_self_role",
            "send_poke",
            "set_msg_emoji_like",
        ),
        risk="medium",
    ),
    Toolset(
        id="qq_admin",
        title="群管理与审核",
        description="高风险：踢人、禁言、全员禁言、退群，以及好友/入群申请审核；需明确指令。",
        tools=(
            "set_group_kick",
            "set_group_ban",
            "set_group_whole_ban",
            "set_group_leave",
            "set_friend_add_request",
            "set_group_add_request",
        ),
        risk="high",
    ),
    Toolset(
        id="history",
        title="历史与归档",
        description="当前最近窗口、群/会话总结、归档筛选与检索；总结优先用 summarize_*。",
        tools=(
            "get_recent_chat_messages",
            "summarize_chat_history",
            "summarize_conversation",
            "filter_archive_records",
            "recall_history",
        ),
        risk="medium",
    ),
    Toolset(
        id="memory",
        title="长期记忆",
        description="保存、更新、删除跨会话长期重要记忆；短聊天事实不要写。",
        tools=(
            "save_important_memory",
            "update_important_memory",
            "delete_important_memory",
        ),
    ),
    Toolset(
        id="knowledge",
        title="知识与热梗",
        description="保存/整理网络资料与知识笔记、删除过时笔记；查询用 list_knowledge_notes。",
        tools=(
            "save_knowledge_note",
            "research_web_to_prompt",
            "list_knowledge_notes",
            "delete_knowledge_note",
        ),
        risk="medium",
    ),
    Toolset(
        id="slang",
        title="群聊黑话",
        description="查询当前群已确认的黑话、缩写和群梗；不保存普通知识。",
        tools=("lookup_slang",),
    ),
    Toolset(
        id="web",
        title="联网与天气",
        description="联网搜索、读取网页正文和查询天气。",
        tools=("web_search", "web_fetch", "get_weather"),
    ),
    Toolset(
        id="emoji",
        title="表情包",
        description="列出、收藏、改名和删除表情包；发送时用 send_* 的 emoji 字段。",
        tools=(
            "list_emoji",
            "save_emoji_from_url",
            "save_emoji_from_workspace",
            "rename_emoji",
            "delete_emoji",
        ),
        risk="medium",
    ),
    Toolset(
        id="workspace",
        title="文件与文档",
        description="本机 AI 工作区文件读写/编辑/删除、运行 Python、上传到 QQ、后台整理；隔离执行用 container。",
        tools=(
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "delete_file",
            "run_python",
            "upload_file",
            "start_agent_task",
        ),
        risk="medium",
    ),
    Toolset(
        id="persona",
        title="人格状态",
        description="人格进食、睡眠和自主工作状态。",
        tools=("eat", "sleep", "work"),
    ),
    Toolset(
        id="container",
        title="受控容器",
        description="在受控 Docker 容器内执行命令、读写容器 /workspace、诊断或重置；不是本机工作区。",
        tools=("container",),
        risk="high",
    ),
)

TOOLSET_BY_ID: dict[str, Toolset] = {item.id: item for item in TOOLSETS}

TOOLSET_ALIASES: dict[str, str] = {
    "doc": "workspace",
    "docs": "workspace",
    "files": "workspace",
    "file": "workspace",
    "qq": "qq_info",
    "admin": "qq_admin",
    "group_admin": "qq_admin",
    "search": "web",
    "history_archive": "history",
    "persona_state": "persona",
    "docker": "container",
}


@dataclass(slots=True)
class ToolsetSession:
    """Loaded toolset IDs for one conversation.

    State is intentionally memory-only and scoped by the pipeline to a
    conversation id.  A runtime restart starts from the core set again.
    """

    loaded: set[str] = field(default_factory=set)
    version: int = 0

    def load(self, name: str) -> bool:
        toolset = resolve_toolset(name)
        if toolset is None:
            raise ValueError(f"未知工具集：{name}")
        if toolset.always_on or toolset.id in self.loaded:
            return False
        self.loaded.add(toolset.id)
        self.version += 1
        return True

    def loaded_ids(self) -> list[str]:
        return sorted(self.loaded)

    def allowed_tool_names(self) -> set[str]:
        return allowed_tool_names(self.loaded)


def resolve_toolset(name: str) -> Toolset | None:
    key = str(name or "").strip().lower()
    if not key:
        return None
    if key in TOOLSET_ALIASES:
        key = TOOLSET_ALIASES[key]
    return TOOLSET_BY_ID.get(key)


def toolsets_for_tool(name: str) -> tuple[str, ...]:
    return tuple(item.id for item in TOOLSETS if name in item.tools)


def allowed_tool_names(loaded: set[str] | frozenset[str] | None = None) -> set[str]:
    names = set(CORE_TOOL_NAMES)
    for toolset_id in loaded or set():
        toolset = TOOLSET_BY_ID.get(str(toolset_id))
        if toolset is not None:
            names.update(toolset.tools)
    return names


def unclassified_tools(tool_names: set[str] | frozenset[str]) -> set[str]:
    classified: set[str] = set()
    for toolset in TOOLSETS:
        classified.update(toolset.tools)
    return set(tool_names) - classified


def catalog_snapshot() -> list[dict[str, object]]:
    """Return the static catalog without runtime filtering or loaded state."""
    return [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "risk": item.risk,
            "always_on": item.always_on,
            "tools": list(item.tools),
        }
        for item in TOOLSETS
    ]


__all__ = [
    "CORE_TOOL_NAMES",
    "META_TOOL_NAMES",
    "TOOLSETS",
    "TOOLSET_ALIASES",
    "TOOLSET_BY_ID",
    "Toolset",
    "ToolsetSession",
    "allowed_tool_names",
    "catalog_snapshot",
    "resolve_toolset",
    "toolsets_for_tool",
    "unclassified_tools",
]
