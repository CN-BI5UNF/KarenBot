#!/usr/bin/env python3
"""Build the three component archives and ``modules.json`` for a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .verify_modules import (
        COMPONENT_ORDER,
        REPO_NAMES,
        ROOT,
        VerificationError,
        verify,
    )
except ImportError:  # pragma: no cover - direct script execution
    from verify_modules import (  # type: ignore[no-redef]
        COMPONENT_ORDER,
        REPO_NAMES,
        ROOT,
        VerificationError,
        verify,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive(module: Path, commit: str, destination: Path, prefix: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(module),
            "archive",
            "--format=tar.gz",
            f"--prefix={prefix}/",
            "-o",
            str(destination),
            commit,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError(
            f"git archive 失败（{module}）：{result.stderr.strip()}"
        )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise VerificationError(f"生成的资产为空：{destination}")


def build(tag: str, output: Path) -> dict[str, Any]:
    lock = verify(tag)
    if output.is_symlink():
        raise VerificationError("输出目录不能是符号链接")
    output = output.resolve()
    if output == ROOT:
        raise VerificationError("输出目录不能是仓库根目录")
    output.mkdir(parents=True, exist_ok=True)
    components: dict[str, Any] = {}
    for component in COMPONENT_ORDER:
        entry = lock["components"][component]
        module = ROOT / str(entry["path"])
        version = str(entry["tag"]).lstrip("vV")
        asset_name = f"{REPO_NAMES[component]}-{tag}.tar.gz"
        asset = output / asset_name
        _archive(
            module,
            str(entry["commit"]),
            asset,
            f"{REPO_NAMES[component]}-{tag}",
        )
        components[component] = {
            "repo": str(entry["repo"]),
            "tag": str(entry["tag"]),
            "version": version,
            "asset": asset_name,
            "sha256": _sha256(asset),
            "size": asset.stat().st_size,
        }
    manifest = {
        "schema": 1,
        "release": tag,
        "components": components,
    }
    manifest_path = output / "modules.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="发行版 tag，例如 v2.0.0-alpha")
    parser.add_argument(
        "--output", default=str(ROOT / "dist"), help="资产输出目录"
    )
    args = parser.parse_args(argv)
    try:
        manifest = build(args.tag, Path(args.output))
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"built {args.tag}: "
        + ", ".join(
            f"{name}={item['asset']} ({item['size']} bytes)"
            for name, item in manifest["components"].items()
        )
    )
    print(f"manifest: {Path(args.output) / 'modules.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
