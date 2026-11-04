"""Per-group @-trigger receive windows.

The user can mark selected groups as @-only.  In those groups ordinary
messages are dropped until someone mentions the bot.  A mention opens a
receive window bounded by a message count and/or a duration; when both are
configured, whichever limit is reached first closes the window.  Groups that
are not listed keep the normal receive behavior.

The model can temporarily bypass the gate through the ``group_trigger_window``
tool.  At most two groups can be open through model-created windows at the
same time.  An active mention window can be extended (converted into a
model-owned window), and either kind of window can be closed early.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

MAX_LLM_GROUPS = 2
MAX_WINDOW_MINUTES = 1440
MIN_WINDOW_MINUTES = 1
WINDOW_SOURCE_MENTION = "mention"
WINDOW_SOURCE_LLM = "llm"
_NEAR_MESSAGE_CAP = 2
_NEAR_SECONDS_CAP = 300.0
_NEAR_SECONDS_FLOOR = 60.0


def _positive_ids(values: Iterable[int] | None) -> tuple[int, ...]:
    result: list[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in result:
            result.append(number)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class GroupTriggerRule:
    group_id: int
    max_messages: int = 0
    window_minutes: int = 0

    @property
    def has_window(self) -> bool:
        return self.max_messages > 0 or self.window_minutes > 0


@dataclass(slots=True)
class TriggerWindow:
    group_id: int
    source: str
    opened_at: float
    until: float | None
    max_messages: int
    remaining_messages: int | None
    reason: str = ""
    updated_at: float = 0.0
    duration_seconds: float | None = None

    def timed_out(self, now: float) -> bool:
        return self.until is not None and self.until <= now

    def exhausted(self) -> bool:
        return self.remaining_messages is not None and self.remaining_messages <= 0


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    allowed: bool
    configured: bool
    is_mention: bool
    window: dict[str, Any] | None = None
    opened: bool = False
    closed: bool = False


class GroupTriggerManager:
    """Runtime state for mention-triggered groups.

    State is intentionally memory-only.  Restarting the runtime restores the
    user's configured rules but closes transient windows.
    """

    def __init__(self, config: Any | None = None) -> None:
        self.enabled = False
        self._rules: dict[int, GroupTriggerRule] = {}
        self._windows: dict[int, TriggerWindow] = {}
        self._last_notices: dict[int, dict[str, Any]] = {}
        self.configure(config)

    def configure(self, config: Any | None) -> None:
        enabled = bool(getattr(config, "enabled", False))
        groups = list(getattr(config, "groups", []) or [])
        rules: dict[int, GroupTriggerRule] = {}
        for item in groups:
            try:
                group_id = int(getattr(item, "group_id", 0))
            except (TypeError, ValueError):
                continue
            if group_id <= 0:
                continue
            try:
                max_messages = max(0, int(getattr(item, "max_messages", 0) or 0))
            except (TypeError, ValueError):
                max_messages = 0
            try:
                window_minutes = max(
                    0, int(getattr(item, "window_minutes", 0) or 0)
                )
            except (TypeError, ValueError):
                window_minutes = 0
            rules[group_id] = GroupTriggerRule(
                group_id=group_id,
                max_messages=max_messages,
                window_minutes=window_minutes,
            )
        previous_rules = self._rules
        self.enabled = enabled
        self._rules = rules
        if not enabled:
            self._windows.clear()
            self._last_notices.clear()
            return
        for group_id in list(self._windows):
            if group_id not in rules or rules[group_id] != previous_rules.get(
                group_id
            ):
                self._windows.pop(group_id, None)
        for group_id in list(self._last_notices):
            if group_id not in rules or rules[group_id] != previous_rules.get(
                group_id
            ):
                self._last_notices.pop(group_id, None)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def rule(self, group_id: int | str) -> GroupTriggerRule | None:
        try:
            return self._rules.get(int(group_id))
        except (TypeError, ValueError):
            return None

    def is_configured(self, group_id: int | str) -> bool:
        return self.rule(group_id) is not None

    def _active_window(
        self, group_id: int, now: float
    ) -> TriggerWindow | None:
        window = self._windows.get(group_id)
        if window is None:
            return None
        if window.timed_out(now) or window.exhausted():
            self._windows.pop(group_id, None)
            return None
        return window

    def _remember_notice(
        self,
        group_id: int,
        snapshot: dict[str, Any] | None,
        *,
        closed_after: bool,
        now: float,
    ) -> None:
        if not snapshot:
            return
        self._last_notices[group_id] = {
            "window": dict(snapshot),
            "closed_after": bool(closed_after),
            "at": float(now),
        }

    def context_snapshot(
        self, group_id: int | str, *, now: float | None = None
    ) -> dict[str, Any] | None:
        """Return the window state for prompt construction.

        The message that exhausts a count window is still delivered, so keep
        its last snapshot briefly.  That lets the task context explain that
        the window has just closed and that ``open`` can be used to resume.
        """
        current = time.time() if now is None else float(now)
        snapshot = self.snapshot(group_id, now=current)
        if snapshot and snapshot.get("active"):
            result = dict(snapshot)
            result["closed_after"] = False
            return result
        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            return snapshot
        notice = self._last_notices.get(gid)
        if notice and current - float(notice.get("at") or 0) <= 300.0:
            result = dict(notice.get("window") or {})
            result["active"] = False
            result["closed_after"] = bool(notice.get("closed_after"))
            result["stale"] = True
            return result
        return snapshot

    def _open_mention_window(
        self, rule: GroupTriggerRule, now: float
    ) -> TriggerWindow | None:
        if not rule.has_window:
            self._windows.pop(rule.group_id, None)
            return None
        window = TriggerWindow(
            group_id=rule.group_id,
            source=WINDOW_SOURCE_MENTION,
            opened_at=now,
            until=(
                now + rule.window_minutes * 60.0
                if rule.window_minutes > 0
                else None
            ),
            max_messages=rule.max_messages,
            remaining_messages=(
                rule.max_messages if rule.max_messages > 0 else None
            ),
            duration_seconds=(
                rule.window_minutes * 60.0 if rule.window_minutes > 0 else None
            ),
            updated_at=now,
        )
        self._windows[rule.group_id] = window
        return window

    def on_inbound(
        self,
        group_id: int | str,
        is_mention: bool,
        *,
        now: float | None = None,
    ) -> TriggerDecision:
        """Apply the configured gate to one group message.

        @ messages always pass and open/refresh a mention window.  A window
        created by the model takes precedence and is time-only.  Ordinary
        messages consume one message slot only when a mention window allows
        them.
        """
        current = time.time() if now is None else float(now)
        rule = self.rule(group_id)
        if not self.enabled or rule is None:
            return TriggerDecision(
                allowed=True,
                configured=False,
                is_mention=bool(is_mention),
            )
        gid = rule.group_id
        active = self._active_window(gid, current)
        if is_mention:
            if active is not None and active.source == WINDOW_SOURCE_LLM:
                snapshot = self._snapshot_window(active, current)
                self._remember_notice(
                    gid, snapshot, closed_after=False, now=current
                )
                return TriggerDecision(
                    allowed=True,
                    configured=True,
                    is_mention=True,
                    window=snapshot,
                )
            window = self._open_mention_window(rule, current)
            snapshot = (
                self._snapshot_window(window, current) if window else None
            )
            self._remember_notice(
                gid, snapshot, closed_after=False, now=current
            )
            return TriggerDecision(
                allowed=True,
                configured=True,
                is_mention=True,
                window=snapshot,
                opened=window is not None,
            )
        if active is None:
            return TriggerDecision(
                allowed=False,
                configured=True,
                is_mention=False,
            )
        if active.source == WINDOW_SOURCE_LLM:
            snapshot = self._snapshot_window(active, current)
            self._remember_notice(
                gid, snapshot, closed_after=False, now=current
            )
            return TriggerDecision(
                allowed=True,
                configured=True,
                is_mention=False,
                window=snapshot,
            )
        if active.remaining_messages is not None:
            active.remaining_messages = max(0, active.remaining_messages - 1)
            active.updated_at = current
        snapshot = self._snapshot_window(active, current)
        if active.exhausted():
            self._windows.pop(gid, None)
            self._remember_notice(
                gid, snapshot, closed_after=True, now=current
            )
            return TriggerDecision(
                allowed=True,
                configured=True,
                is_mention=False,
                window=snapshot,
                closed=True,
            )
        self._remember_notice(
            gid, snapshot, closed_after=False, now=current
        )
        return TriggerDecision(
            allowed=True,
            configured=True,
            is_mention=False,
            window=snapshot,
        )

    def _snapshot_window(
        self, window: TriggerWindow | None, now: float
    ) -> dict[str, Any] | None:
        if window is None:
            return None
        remaining_seconds = (
            max(0, int(window.until - now + 0.999))
            if window.until is not None
            else None
        )
        rule = self._rules.get(window.group_id)
        near_seconds = self._near_seconds(window)
        near = (
            window.remaining_messages is not None
            and window.remaining_messages <= self._near_messages(window)
        ) or (
            remaining_seconds is not None
            and remaining_seconds <= near_seconds
        )
        return {
            "group_id": window.group_id,
            "source": window.source,
            "active": True,
            "until": window.until,
            "remaining_seconds": remaining_seconds,
            "remaining_minutes": (
                max(0, int((remaining_seconds + 59) // 60))
                if remaining_seconds is not None
                else None
            ),
            "remaining_messages": window.remaining_messages,
            "max_messages": window.max_messages,
            "window_minutes": (
                rule.window_minutes
                if window.source == WINDOW_SOURCE_MENTION and rule is not None
                else (
                    int(round((window.duration_seconds or 0) / 60))
                    if window.duration_seconds
                    else 0
                )
            ),
            "reason": window.reason,
            "near_limit": bool(near),
            "llm_owned": window.source == WINDOW_SOURCE_LLM,
        }

    @staticmethod
    def _near_messages(window: TriggerWindow) -> int:
        if window.max_messages <= 0:
            return _NEAR_MESSAGE_CAP
        return min(_NEAR_MESSAGE_CAP, max(1, window.max_messages // 5))

    @staticmethod
    def _near_seconds(window: TriggerWindow) -> float:
        if not window.duration_seconds or window.duration_seconds <= 0:
            return _NEAR_SECONDS_FLOOR
        return max(
            _NEAR_SECONDS_FLOOR,
            min(_NEAR_SECONDS_CAP, window.duration_seconds * 0.2),
        )

    def snapshot(
        self, group_id: int | str, *, now: float | None = None
    ) -> dict[str, Any] | None:
        current = time.time() if now is None else float(now)
        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            return None
        rule = self._rules.get(gid) if self.enabled else None
        if rule is None:
            return None
        window = self._active_window(gid, current)
        if window is None:
            return {
                "group_id": gid,
                "active": False,
                "configured": True,
                "max_messages": rule.max_messages,
                "window_minutes": rule.window_minutes,
            }
        snapshot = self._snapshot_window(window, current) or {}
        snapshot["configured"] = True
        return snapshot

    def snapshots(self, *, now: float | None = None) -> list[dict[str, Any]]:
        current = time.time() if now is None else float(now)
        result: list[dict[str, Any]] = []
        for gid in list(self._windows):
            data = self.snapshot(gid, now=current)
            if data and data.get("active"):
                result.append(data)
        result.sort(key=lambda item: int(item.get("group_id") or 0))
        return result

    def llm_owned_group_ids(self, *, now: float | None = None) -> set[int]:
        current = time.time() if now is None else float(now)
        result: set[int] = set()
        for gid in list(self._windows):
            window = self._windows.get(gid)
            if window is None or window.source != WINDOW_SOURCE_LLM:
                continue
            if self._active_window(gid, current) is not None:
                result.add(gid)
        return result

    def _normalize_groups(
        self, group_ids: Iterable[int] | None, default_group_id: int | None
    ) -> tuple[int, ...]:
        normalized = _positive_ids(group_ids)
        if not normalized and default_group_id is not None:
            try:
                default_id = int(default_group_id)
            except (TypeError, ValueError):
                default_id = 0
            if default_id > 0:
                normalized = (default_id,)
        if not normalized:
            raise ValueError("请至少提供一个群号")
        if len(normalized) > MAX_LLM_GROUPS:
            raise ValueError(f"每次最多操作 {MAX_LLM_GROUPS} 个群")
        if not self.enabled:
            raise ValueError("群聊 @ 触发未启用")
        missing = [gid for gid in normalized if gid not in self._rules]
        if missing:
            raise ValueError(
                "以下群未配置为 @ 触发：" + "、".join(str(gid) for gid in missing)
            )
        return normalized

    @staticmethod
    def _duration_seconds(duration_minutes: int | None) -> int:
        try:
            minutes = int(duration_minutes if duration_minutes is not None else 0)
        except (TypeError, ValueError):
            raise ValueError("duration_minutes 必须是整数") from None
        if minutes < MIN_WINDOW_MINUTES or minutes > MAX_WINDOW_MINUTES:
            raise ValueError(
                f"duration_minutes 必须在 {MIN_WINDOW_MINUTES}-{MAX_WINDOW_MINUTES} 之间"
            )
        return minutes * 60

    def _ensure_llm_capacity(
        self, targets: tuple[int, ...], now: float
    ) -> None:
        active = self.llm_owned_group_ids(now=now)
        union = active | set(targets)
        if len(union) > MAX_LLM_GROUPS:
            names = "、".join(str(gid) for gid in sorted(union))
            raise ValueError(
                f"LLM 临时窗口最多同时覆盖 {MAX_LLM_GROUPS} 个群；"
                f"当前涉及 {names}，请先关闭其它窗口"
            )

    def open_llm_window(
        self,
        group_ids: Iterable[int] | None,
        *,
        duration_minutes: int,
        reason: str = "",
        default_group_id: int | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        targets = self._normalize_groups(group_ids, default_group_id)
        seconds = self._duration_seconds(duration_minutes)
        self._ensure_llm_capacity(targets, current)
        opened: list[dict[str, Any]] = []
        for gid in targets:
            window = TriggerWindow(
                group_id=gid,
                source=WINDOW_SOURCE_LLM,
                opened_at=current,
                until=current + seconds,
                max_messages=0,
                remaining_messages=None,
                reason=str(reason or "").strip(),
                updated_at=current,
                duration_seconds=float(seconds),
            )
            self._windows[gid] = window
            opened.append(self._snapshot_window(window, current) or {})
        return {
            "action": "open",
            "group_ids": list(targets),
            "duration_minutes": duration_minutes,
            "windows": opened,
            "active_llm_groups": sorted(self.llm_owned_group_ids(now=current)),
        }

    def extend_llm_window(
        self,
        group_ids: Iterable[int] | None,
        *,
        duration_minutes: int,
        reason: str = "",
        default_group_id: int | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        targets = self._normalize_groups(group_ids, default_group_id)
        seconds = self._duration_seconds(duration_minutes)
        closed = [
            gid for gid in targets if self._active_window(gid, current) is None
        ]
        if closed:
            raise ValueError(
                "以下群当前没有可延长的窗口："
                + "、".join(str(gid) for gid in closed)
                + "；窗口关闭后请改用 open"
            )
        self._ensure_llm_capacity(targets, current)
        extended: list[dict[str, Any]] = []
        for gid in targets:
            previous = self._windows.get(gid)
            window = TriggerWindow(
                group_id=gid,
                source=WINDOW_SOURCE_LLM,
                opened_at=previous.opened_at if previous else current,
                until=current + seconds,
                max_messages=0,
                remaining_messages=None,
                reason=str(reason or "").strip()
                or (previous.reason if previous else ""),
                updated_at=current,
                duration_seconds=float(seconds),
            )
            self._windows[gid] = window
            extended.append(self._snapshot_window(window, current) or {})
        return {
            "action": "extend",
            "group_ids": list(targets),
            "duration_minutes": duration_minutes,
            "windows": extended,
            "active_llm_groups": sorted(self.llm_owned_group_ids(now=current)),
        }

    def close_window(
        self,
        group_ids: Iterable[int] | None,
        *,
        default_group_id: int | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        targets = self._normalize_groups(group_ids, default_group_id)
        closed: list[int] = []
        absent: list[int] = []
        for gid in targets:
            if self._active_window(gid, current) is None:
                absent.append(gid)
                continue
            self._windows.pop(gid, None)
            closed.append(gid)
        return {
            "action": "close",
            "group_ids": list(targets),
            "closed": closed,
            "absent": absent,
            "active_llm_groups": sorted(self.llm_owned_group_ids(now=current)),
        }

    def status(
        self,
        group_ids: Iterable[int] | None = None,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        normalized = _positive_ids(group_ids)
        if normalized:
            snapshots = []
            for gid in normalized:
                item = self.snapshot(gid, now=current)
                if item is not None:
                    snapshots.append(item)
        else:
            snapshots = self.snapshots(now=current)
        return {
            "action": "status",
            "enabled": self.enabled,
            "rules": [
                {
                    "group_id": rule.group_id,
                    "max_messages": rule.max_messages,
                    "window_minutes": rule.window_minutes,
                }
                for rule in sorted(
                    self._rules.values(), key=lambda item: item.group_id
                )
            ],
            "windows": [item for item in snapshots if item and item.get("active")],
            "active_llm_groups": sorted(self.llm_owned_group_ids(now=current)),
        }

    def apply_tool_action(
        self,
        *,
        action: str,
        group_ids: Iterable[int] | None,
        duration_minutes: int = 30,
        reason: str = "",
        default_group_id: int | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized == "open":
            return self.open_llm_window(
                group_ids,
                duration_minutes=duration_minutes,
                reason=reason,
                default_group_id=default_group_id,
                now=now,
            )
        if normalized == "extend":
            return self.extend_llm_window(
                group_ids,
                duration_minutes=duration_minutes,
                reason=reason,
                default_group_id=default_group_id,
                now=now,
            )
        if normalized == "close":
            return self.close_window(
                group_ids,
                default_group_id=default_group_id,
                now=now,
            )
        if normalized == "status":
            return self.status(group_ids, now=now)
        raise ValueError("action 必须是 open、extend、close 或 status")


__all__ = [
    "GroupTriggerManager",
    "GroupTriggerRule",
    "MAX_LLM_GROUPS",
    "MAX_WINDOW_MINUTES",
    "MIN_WINDOW_MINUTES",
    "TriggerDecision",
    "TriggerWindow",
]
