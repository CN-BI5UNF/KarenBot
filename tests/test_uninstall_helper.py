"""The standalone uninstall helper must validate before touching anything."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from core.destructive_admin import scan_tree
from tools.karen_uninstall_helper import main as helper_main


def _target_record(path: Path) -> dict:
    stats = scan_tree(path)
    info = os.lstat(path)
    return {
        "kind": "project_root",
        "path": str(path),
        "exists": True,
        "is_symlink": False,
        "bytes": stats.bytes,
        "files": stats.files,
        "dirs": stats.dirs,
        "symlinks": stats.symlinks,
        "dev": int(info.st_dev),
        "ino": int(info.st_ino),
    }


def _plan(root: Path, target: Path, *, digest: str | None = None) -> Path:
    audit = root / "audit" / "uninstall-test.json"
    plan = {
        "format": 1,
        "operation": "uninstall",
        "plan_id": "test-plan",
        "created_at": "2026-10-31T00:00:00Z",
        "valid_until": time.time() + 300,
        "operator_uid": os.geteuid() if hasattr(os, "geteuid") else 0,
        "test_mode": True,
        "test_root": str(root),
        "helper_sha256": "",
        "backend": {
            "pid": 0,
            "pid_start_ticks": None,
            "project_root": str(target),
        },
        "service_mode": "test",
        "targets": [_target_record(target)],
        "backup": None,
        "audit": {
            "result_path": str(audit),
            "log_path": str(root / "audit" / "uninstall-test.log"),
        },
        "keep_paths": [],
        "forbidden": ["/"],
    }
    payload = dict(plan)
    payload.pop("plan_digest", None)
    from core.destructive_admin import _sha256_json

    plan["plan_digest"] = digest if digest is not None else _sha256_json(payload)
    path = root / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def test_helper_dry_run_leaves_target_and_writes_audit(tmp_path, monkeypatch):
    root = tmp_path
    target = root / "project"
    target.mkdir()
    (target / "main.py").write_text("print('x')", encoding="utf-8")
    plan_path = _plan(root, target)
    monkeypatch.setenv("KAREN_UNINSTALL_TEST_ROOT", str(root))
    assert helper_main(["--plan", str(plan_path), "--dry-run"]) == 0
    assert target.is_dir()
    audit = json.loads((root / "audit" / "uninstall-test.json").read_text(encoding="utf-8"))
    assert audit["state"] == "dry_run"
    assert audit["targets"][0]["status"] == "not_deleted_dry_run"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows holds open directory handles")
def test_helper_deletes_only_the_validated_target(tmp_path, monkeypatch):
    root = tmp_path
    target = root / "project"
    target.mkdir()
    (target / "main.py").write_text("print('x')", encoding="utf-8")
    keep = root / "keep"
    keep.mkdir()
    (keep / "keep.txt").write_text("keep", encoding="utf-8")
    plan_path = _plan(root, target)
    monkeypatch.setenv("KAREN_UNINSTALL_TEST_ROOT", str(root))
    assert helper_main(["--plan", str(plan_path)]) == 0
    assert not target.exists()
    assert keep.is_dir()
    audit = json.loads((root / "audit" / "uninstall-test.json").read_text(encoding="utf-8"))
    assert audit["state"] == "completed"
    assert audit["targets"][0]["status"] == "deleted"


def test_helper_rejects_tampered_plan_without_deleting(tmp_path, monkeypatch):
    root = tmp_path
    target = root / "project"
    target.mkdir()
    (target / "main.py").write_text("print('x')", encoding="utf-8")
    plan_path = _plan(root, target, digest="0" * 64)
    monkeypatch.setenv("KAREN_UNINSTALL_TEST_ROOT", str(root))
    assert helper_main(["--plan", str(plan_path), "--dry-run"]) == 2
    assert target.is_dir()


def test_helper_rejects_target_outside_test_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x").write_text("x", encoding="utf-8")
    plan_path = _plan(root, outside)
    monkeypatch.setenv("KAREN_UNINSTALL_TEST_ROOT", str(root))
    assert helper_main(["--plan", str(plan_path), "--dry-run"]) == 2
    assert outside.is_dir()
