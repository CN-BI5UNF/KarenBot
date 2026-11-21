#!/usr/bin/env python3
"""Assemble a runnable KarenBot tree from the umbrella submodules."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .verify_modules import ROOT, VerificationError, verify
except ImportError:  # pragma: no cover - direct script execution
    from verify_modules import (  # type: ignore[no-redef]
        ROOT,
        VerificationError,
        verify,
    )

FRONTENDS = {"gui": "gui", "webui": "webui", "both": None}
BACKEND_SKIP_PREFIXES = (".github/", ".gitignore", "personas/")


def _tracked_files(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError(f"无法读取 {repo} 的 tracked files")
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def _copy_file(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise VerificationError(f"拒绝复制符号链接：{source}")
    if not source.is_file():
        raise VerificationError(f"不是普通文件：{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(
    source: Path,
    target: Path,
    *,
    prefix: str = "",
    skip_prefixes: tuple[str, ...] = (),
) -> int:
    count = 0
    for relative in _tracked_files(source):
        if prefix and not relative.startswith(prefix):
            continue
        if any(relative.startswith(item) for item in skip_prefixes):
            continue
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise VerificationError(f"不安全的路径：{relative}")
        _copy_file(source / relative_path, target / relative_path)
        count += 1
    return count


def _write_manifest(
    output: Path,
    lock: dict[str, Any],
    frontend: str,
) -> None:
    components: dict[str, Any] = {}
    selected = ["backend"]
    if frontend == "both":
        selected.extend(["gui", "webui"])
    else:
        selected.append(frontend)
    for component in selected:
        entry = lock["components"][component]
        components[component] = {
            "repo": str(entry["repo"]),
            "dir": component,
            "tag": str(entry["tag"]),
            "version": str(entry["tag"]).lstrip("vV"),
        }
    manifest: dict[str, Any] = {
        "schema": 1,
        "distribution": {
            "repo": "CN-BI5UNF/KarenBot",
            "tag": str(lock["release"]),
        },
        "components": components,
    }
    if frontend != "both":
        manifest["frontend"] = frontend
    (output / "modules.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def check() -> dict[str, Any]:
    return verify()


def assemble(frontend: str, output: Path, *, force: bool = False) -> None:
    if frontend not in FRONTENDS:
        raise VerificationError(f"未知前端：{frontend}")
    lock = verify()
    if output.is_symlink():
        raise VerificationError("输出目录不能是符号链接")
    output = output.resolve()
    if output == ROOT:
        raise VerificationError("输出目录不能是仓库根目录")
    if output.exists():
        if not output.is_dir():
            raise VerificationError(f"输出路径不是目录：{output}")
        if any(output.iterdir()) and not force:
            raise VerificationError(
                f"输出目录非空：{output}；请使用 --force 或换一个目录"
            )
        if force:
            for child in output.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    output.mkdir(parents=True, exist_ok=True)

    backend = ROOT / str(lock["components"]["backend"]["path"])
    _copy_tree(
        backend,
        output,
        skip_prefixes=BACKEND_SKIP_PREFIXES,
    )
    if frontend in {"gui", "both"}:
        gui = ROOT / str(lock["components"]["gui"]["path"])
        _copy_tree(gui, output, prefix="gui/")
    if frontend in {"webui", "both"}:
        webui = ROOT / str(lock["components"]["webui"]["path"])
        _copy_tree(webui, output, prefix="webui/")

    _copy_tree(ROOT, output, prefix="personas/")
    for name in ("LICENSE", "NOTICE"):
        source = ROOT / name
        if source.is_file():
            _copy_file(source, output / name)
    _write_manifest(output, lock, frontend)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend",
        choices=tuple(FRONTENDS),
        default="both",
        help="只组装一个前端，或两个都组装",
    )
    parser.add_argument("--output", default="", help="输出目录")
    parser.add_argument(
        "--check", action="store_true", help="只校验 submodule 与 lock"
    )
    parser.add_argument("--force", action="store_true", help="允许覆盖非空输出目录")
    args = parser.parse_args(argv)
    try:
        if args.check:
            lock = check()
            print(f"assemble check ok: {lock['release']}")
            return 0
        if not args.output:
            parser.error("--output 必填（除非使用 --check）")
        assemble(args.frontend, Path(args.output), force=args.force)
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"assembled {args.frontend} -> {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
