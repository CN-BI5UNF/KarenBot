"""Durable markers for destructive persona cleanup.

After a persona's runtime database is removed, the startup legacy importer must
not recreate usage records from the global ``logs/model_usage.jsonl``. A small
marker under the maintenance directory suppresses that one import path without
touching the global log.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKER_DIRNAME = "persona_cleanup"


def _marker_dir(paths: Any) -> Path:
    return Path(paths.MAINTENANCE_DIR) / MARKER_DIRNAME


def cleanup_marker_path(paths: Any, persona: str) -> Path:
    name = str(persona or "").strip()
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    return _marker_dir(paths) / f"{digest}.json"


def write_cleanup_marker(
    paths: Any,
    persona: str,
    *,
    reason: str = "persona_runtime_cleanup",
    cleaned_at: float | None = None,
) -> Path:
    target = cleanup_marker_path(paths, persona)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "persona": str(persona or "").strip(),
        "reason": str(reason or "persona_runtime_cleanup")[:120],
        "cleaned_at": float(cleaned_at if cleaned_at is not None else time.time()),
        "suppress_legacy_usage_import": True,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = target.with_name(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp"
    )
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def read_cleanup_marker(paths: Any, persona: str) -> dict[str, Any] | None:
    target = cleanup_marker_path(paths, persona)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def legacy_usage_import_suppressed(paths: Any, persona: str) -> bool:
    data = read_cleanup_marker(paths, persona)
    return bool(data and data.get("suppress_legacy_usage_import") is True)


__all__ = [
    "MARKER_DIRNAME",
    "cleanup_marker_path",
    "legacy_usage_import_suppressed",
    "read_cleanup_marker",
    "write_cleanup_marker",
]
