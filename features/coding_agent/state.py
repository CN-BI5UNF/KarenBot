"""Per-conversation state for native coding-agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MAX_TODOS = 20
MAX_TODO_CHARS = 200

AgentSessionMode = Literal["coding", "plan"]


@dataclass(slots=True)
class AgentSessionState:
    """Memory-only state shared by coding tools in one conversation."""

    mode: AgentSessionMode = "coding"
    todos: list[dict[str, str]] = field(default_factory=list)
    plan: str = ""
    pending_question: dict | None = None

    def replace_todos(self, items: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for item in items[:MAX_TODOS]:
            content = str(item.get("content") or "").strip()
            status = str(item.get("status") or "pending").strip().lower()
            if not content:
                continue
            if status not in {"pending", "in_progress", "completed"}:
                status = "pending"
            cleaned.append({"content": content[:MAX_TODO_CHARS], "status": status})
        self.todos = cleaned
        return list(self.todos)

    def set_plan(self, plan: str) -> str:
        self.plan = str(plan or "")[:16384]
        self.mode = "coding"
        return self.plan


__all__ = ["AgentSessionMode", "AgentSessionState", "MAX_TODOS", "MAX_TODO_CHARS"]
