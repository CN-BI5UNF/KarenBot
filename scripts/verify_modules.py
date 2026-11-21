#!/usr/bin/env python3
"""Verify that the KarenBot umbrella submodules match ``modules.lock.json``."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "modules.lock.json"
LOCK_SCHEMA = 1
COMPONENT_ORDER = ("backend", "gui", "webui")
REQUIRED_PATHS = {
    "backend": ("main.py", "backend", "core", "app_config"),
    "gui": ("gui",),
    "webui": ("webui",),
}
REPO_NAMES = {
    "backend": "KarenBot-backend",
    "gui": "KarenBot-GUI",
    "webui": "KarenBot-WebUI",
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    pass


def load_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"无法读取 {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != LOCK_SCHEMA:
        raise VerificationError("modules.lock.json schema 不受支持")
    release = str(data.get("release") or "").strip()
    if not release.startswith("v"):
        raise VerificationError("modules.lock.json 缺少合法 release tag")
    components = data.get("components")
    if not isinstance(components, dict):
        raise VerificationError("modules.lock.json 缺少 components")
    for component in COMPONENT_ORDER:
        entry = components.get(component)
        if not isinstance(entry, dict):
            raise VerificationError(f"modules.lock.json 缺少 {component}")
        for key in ("repo", "path", "tag", "commit"):
            if not str(entry.get(key) or "").strip():
                raise VerificationError(
                    f"modules.lock.json 的 {component}.{key} 为空"
                )
        relative = Path(str(entry["path"]))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) < 2
            or relative.parts[0] != "modules"
        ):
            raise VerificationError(
                f"{component} 的 path 必须位于 modules/ 下"
            )
        if not _COMMIT_RE.match(str(entry["commit"])):
            raise VerificationError(f"{component} 的 commit 不合法")
    return data


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError(
            f"git {' '.join(args)} 失败（{path}）："
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def verify(tag: str | None = None, lock_path: Path = LOCK_PATH) -> dict[str, Any]:
    lock = load_lock(lock_path)
    release = str(lock["release"])
    if tag and release != tag:
        raise VerificationError(
            f"modules.lock.json 的 release={release} 与目标 tag={tag} 不一致"
        )
    for component in COMPONENT_ORDER:
        entry = lock["components"][component]
        module_path = ROOT / str(entry["path"])
        if not module_path.exists():
            raise VerificationError(
                f"{component} submodule 未初始化：{entry['path']}；"
                "请执行 git submodule update --init --recursive"
            )
        if not (module_path / ".git").exists():
            raise VerificationError(
                f"{component} 不是 Git submodule：{entry['path']}"
            )
        head = _git(module_path, "rev-parse", "HEAD")
        if head != str(entry["commit"]):
            raise VerificationError(
                f"{component} HEAD={head[:12]} 与 lock="
                f"{str(entry['commit'])[:12]} 不一致"
            )
        version = _git(module_path, "show", "HEAD:VERSION")
        expected = str(entry["tag"]).lstrip("vV")
        if version != expected:
            raise VerificationError(
                f"{component} VERSION={version!r} 与 tag={entry['tag']} 不一致"
            )
        for relative in REQUIRED_PATHS[component]:
            if not (module_path / relative).exists():
                raise VerificationError(
                    f"{component} 缺少 {relative}"
                )
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="", help="期望的发行版 tag")
    args = parser.parse_args(argv)
    try:
        lock = verify(args.tag or None)
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    components = ", ".join(
        f"{name}={lock['components'][name]['tag']}"
        for name in COMPONENT_ORDER
    )
    print(f"modules ok: {lock['release']} ({components})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
