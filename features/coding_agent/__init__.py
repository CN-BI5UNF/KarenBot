"""Native coding-agent modes for KarenBot's LLM.

The package implements Pi/DSH/Claude Code *tool semantics* only.  It does not
start or expose their TUI, GUI or WebUI.  Host mode is fixed to Claude Code
semantics; container mode uses the single active mode from the container page.
"""

from .types import (
    AGENT_MODES,
    HOST_MODE,
    MODE_DESCRIPTIONS,
    MODE_LABELS,
    AgentMode,
    AgentRuntimeInfo,
    AgentTarget,
    HostExecutionMode,
    mode_supports,
    normalize_mode,
)

__all__ = [
    "AGENT_MODES",
    "HOST_MODE",
    "AgentMode",
    "AgentRuntimeInfo",
    "AgentTarget",
    "HostExecutionMode",
    "MODE_DESCRIPTIONS",
    "MODE_LABELS",
    "mode_supports",
    "normalize_mode",
]
