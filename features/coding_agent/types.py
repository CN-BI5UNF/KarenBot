"""Shared types and limits for KarenBot's native coding-agent tools.

The three selectable container modes (Pi, DSH, Claude Code) are implemented as
native tool semantics, not as their TUI/GUI/CLI front-ends.  This module keeps
the mode matrix and limits in one place so the tool layer, backends and WebUI
cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentMode = Literal["pi", "dsh", "claude_code"]
AgentTarget = Literal["host", "container"]
HostExecutionMode = Literal["sandbox", "host"]

AGENT_MODES: tuple[AgentMode, ...] = ("pi", "dsh", "claude_code")

MODE_LABELS: dict[AgentMode, str] = {
    "pi": "Pi Coding Agent",
    "dsh": "DeepSeek Harness",
    "claude_code": "Claude Code",
}

MODE_DESCRIPTIONS: dict[AgentMode, str] = {
    "pi": "精简文件/命令工具，并允许 LLM 自己编写、保存和运行自定义工具。",
    "dsh": "插件式工具集：文件/补丁/搜索/子 Agent/计划，并允许 LLM 编写插件式工具。",
    "claude_code": "覆盖最完整的编码工具集：读写、编辑、命令、搜索、子 Agent、待办和计划。",
}

HOST_MODE: AgentMode = "claude_code"
"""本机固定使用 Claude Code 语义。"""

HOST_LABEL = "Claude Code（本机）"

MAX_READ_LINES = 20_000
MAX_READ_BYTES = 1 * 1024 * 1024
MAX_WRITE_BYTES = 8 * 1024 * 1024
MAX_PATCH_BYTES = 1 * 1024 * 1024
MAX_BASH_COMMAND_BYTES = 64 * 1024
MAX_BASH_STDIN_BYTES = 1 * 1024 * 1024
MAX_BASH_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_GLOB_RESULTS = 2_000
MAX_GREP_RESULTS = 500
MAX_LS_RESULTS = 2_000
MAX_CUSTOM_TOOL_BYTES = 256 * 1024
MAX_CUSTOM_TOOL_NAME = 64
MAX_CUSTOM_TOOLS = 64


@dataclass(frozen=True, slots=True)
class AgentRuntimeInfo:
    """One resolved execution context for a coding tool call."""

    target: AgentTarget
    mode: AgentMode
    host_execution: HostExecutionMode
    workspace: str
    container_mode: AgentMode | None = None


def normalize_mode(value: object, *, default: AgentMode = "claude_code") -> AgentMode:
    text = str(value or "").strip().lower()
    if text in AGENT_MODES:
        return text  # type: ignore[return-value]
    aliases = {
        "claude": "claude_code",
        "claude-code": "claude_code",
        "deepseek": "dsh",
        "deepseek_harness": "dsh",
        "pi-coding": "pi",
        "pi_coding": "pi",
    }
    return aliases.get(text, default)  # type: ignore[return-value]


def mode_supports(mode: AgentMode, capability: str) -> bool:
    """Return whether a mode exposes one capability.

    ``capability`` is a stable key such as ``custom_tools`` or ``spawn``.
    Claude Code is the superset; Pi is deliberately minimal; DSH sits between.
    """
    common = {
        "read",
        "write",
        "edit",
        "bash",
        "glob",
        "grep",
        "ls",
    }
    if capability in common:
        return True
    if mode == "pi":
        return capability == "custom_tools"
    if mode == "dsh":
        return capability in {
            "apply_patch",
            "todo",
            "spawn",
            "plan",
            "custom_tools",
        }
    return capability in {
        "apply_patch",
        "todo",
        "spawn",
        "plan",
        "notebook",
    }


def result_error(
    message: str,
    *,
    code: str = "agent_tool_error",
    **extra: object,
) -> dict:
    payload = {
        "ok": False,
        "status": "failed",
        "brief": message,
        "error": message,
        "code": code,
    }
    payload.update(extra)
    return payload


__all__ = [
    "AGENT_MODES",
    "AgentMode",
    "AgentRuntimeInfo",
    "AgentTarget",
    "HOST_LABEL",
    "HOST_MODE",
    "HostExecutionMode",
    "MAX_BASH_COMMAND_BYTES",
    "MAX_BASH_OUTPUT_BYTES",
    "MAX_BASH_STDIN_BYTES",
    "MAX_CUSTOM_TOOL_BYTES",
    "MAX_CUSTOM_TOOL_NAME",
    "MAX_CUSTOM_TOOLS",
    "MAX_GLOB_RESULTS",
    "MAX_GREP_RESULTS",
    "MAX_LS_RESULTS",
    "MAX_PATCH_BYTES",
    "MAX_READ_BYTES",
    "MAX_READ_LINES",
    "MAX_WRITE_BYTES",
    "MODE_DESCRIPTIONS",
    "MODE_LABELS",
    "mode_supports",
    "normalize_mode",
    "result_error",
]
