#!/usr/bin/env python3
"""Standalone local-uninstall helper.

This file intentionally imports only the Python standard library. The backend
copies it outside every deletion target before spawning it, then exits. The
helper waits for the backend to disappear, revalidates every target and optional
backup, and only then removes app-known paths.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

BACKUP_PATTERNS = ("Karen_Backup_*.zip", "Karen_Backup_*.zip.json")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _fail(message: str) -> int:
    print(f"karen-uninstall: {message}", file=sys.stderr)
    return 2


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(_fail(f"无法读取 plan：{exc}")) from exc
    if not isinstance(raw, dict):
        raise SystemExit(_fail("plan 不是对象"))
    return raw


def _validate_plan(plan_path: Path, plan: dict[str, Any]) -> None:
    try:
        info = os.lstat(plan_path)
    except OSError as exc:
        raise SystemExit(_fail(f"无法检查 plan：{exc}")) from exc
    if os.name != "nt":
        if int(os.geteuid()) != int(plan.get("operator_uid", -1)):
            raise SystemExit(_fail("plan owner 与当前用户不匹配"))
        if int(info.st_mode & 0o777) & 0o077:
            raise SystemExit(_fail("plan 权限过宽，拒绝执行"))
    digest = str(plan.get("plan_digest") or "")
    payload = dict(plan)
    payload.pop("plan_digest", None)
    if not digest or digest != _sha256_json(payload):
        raise SystemExit(_fail("plan digest 不匹配"))
    if float(plan.get("valid_until") or 0) < time.time():
        raise SystemExit(_fail("plan 已过期"))
    expected_helper = str(plan.get("helper_sha256") or "")
    if expected_helper:
        try:
            actual_helper = _sha256_file(Path(__file__).resolve())
        except OSError as exc:
            raise SystemExit(_fail(f"无法校验助手自身：{exc}")) from exc
        if actual_helper != expected_helper:
            raise SystemExit(_fail("助手文件哈希不匹配"))
    test_mode = bool(plan.get("test_mode"))
    if test_mode:
        root_text = os.environ.get("KAREN_UNINSTALL_TEST_ROOT", "")
        if not root_text:
            raise SystemExit(_fail("test plan 缺少 KAREN_UNINSTALL_TEST_ROOT"))
        root = Path(root_text).expanduser().resolve()
        for target in plan.get("targets") or []:
            if not _is_within(Path(str(target.get("path") or "")), root):
                raise SystemExit(_fail("test target 越界"))
        audit = plan.get("audit") or {}
        for key in ("result_path", "log_path"):
            if audit.get(key) and not _is_within(Path(audit[key]), root):
                raise SystemExit(_fail("test audit 越界"))
        backup = plan.get("backup") or {}
        for key in ("directory",):
            if backup.get(key) and not _is_within(Path(backup[key]), root):
                raise SystemExit(_fail("test backup 越界"))
        for keep in plan.get("keep_paths") or []:
            if not _is_within(Path(keep), root):
                raise SystemExit(_fail("test keep path 越界"))


def _pid_alive(pid: int, expected_ticks: int | None) -> bool:
    if pid <= 0:
        return False
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = raw.rsplit(")", 1)[1].strip().split()
        ticks = int(fields[19])
    except (OSError, IndexError, ValueError):
        if sys.platform.startswith("linux"):
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    if expected_ticks is not None and ticks != int(expected_ticks):
        return False
    return True


def _wait_backend(plan: dict[str, Any], *, timeout: float = 90.0) -> None:
    if bool(plan.get("test_mode")):
        return
    backend = plan.get("backend") or {}
    pid = int(backend.get("pid") or 0)
    ticks = backend.get("pid_start_ticks")
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid, ticks):
            return
        time.sleep(0.5)
    # Last-resort termination; the backend normally exits by itself after
    # scheduling the helper.
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid, ticks):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid, ticks):
            return
        time.sleep(0.2)
    raise SystemExit(_fail("后端进程仍未退出；为避免删除运行中数据，已中止"))


def _verify_backup(plan: dict[str, Any]) -> dict[str, Any]:
    backup = plan.get("backup") or None
    if not backup:
        return {"requested": False, "verified": True}
    for key in ("user_backup", "source_archive"):
        info = backup.get(key)
        if not isinstance(info, dict):
            raise SystemExit(_fail(f"备份信息缺少 {key}"))
        path = Path(str(info.get("path") or ""))
        if not path.is_file() or path.is_symlink():
            raise SystemExit(_fail(f"备份文件不存在或不是普通文件：{path}"))
        expected = str(info.get("sha256") or "")
        if expected and _sha256_file(path) != expected:
            raise SystemExit(_fail(f"备份哈希不匹配：{path}"))
        expected_size = int(info.get("bytes") or 0)
        if expected_size and path.stat().st_size != expected_size:
            raise SystemExit(_fail(f"备份大小不匹配：{path}"))
    return {"requested": True, "verified": True}


def _revalidate_targets(plan: dict[str, Any], helper_root: Path) -> list[dict[str, Any]]:
    targets = plan.get("targets") or []
    forbidden = {Path(str(item)) for item in plan.get("forbidden") or []}
    audit_path = Path(str((plan.get("audit") or {}).get("result_path") or ""))
    backup = plan.get("backup") or {}
    backup_dir = Path(str(backup.get("directory") or "")) if backup else None
    keep_paths = [Path(str(item)) for item in plan.get("keep_paths") or []]
    validated = []
    for item in targets:
        path = Path(str(item.get("path") or ""))
        if not path.is_absolute():
            raise SystemExit(_fail(f"目标不是绝对路径：{path}"))
        if ".." in path.parts:
            raise SystemExit(_fail(f"目标包含 ..：{path}"))
        if path in forbidden or path == Path("/"):
            raise SystemExit(_fail(f"目标在禁止路径中：{path}"))
        if _is_within(path, helper_root):
            raise SystemExit(_fail(f"目标包含助手目录：{path}"))
        if _is_within(audit_path, path):
            raise SystemExit(_fail(f"目标包含审计目录：{path}"))
        if backup_dir is not None and _is_within(backup_dir, path) and item.get("kind") != "backup_library":
            raise SystemExit(_fail(f"目标包含备份目录：{path}"))
        for keep in keep_paths:
            if _is_within(keep, path) and item.get("kind") != "backup_library":
                raise SystemExit(_fail(f"目标包含保留路径：{path}"))
        existed = bool(item.get("exists"))
        if path.is_symlink() and item.get("kind") != "systemd_enable_link":
            raise SystemExit(_fail(f"目标是符号链接：{path}"))
        if path.exists() != existed:
            raise SystemExit(_fail(f"目标存在性与预览不一致：{path}"))
        if existed:
            try:
                info = os.lstat(path)
            except OSError as exc:
                raise SystemExit(_fail(f"无法检查目标 {path}：{exc}")) from exc
            expected_dev = int(item.get("dev") or 0)
            expected_ino = int(item.get("ino") or 0)
            if expected_ino and (
                int(info.st_dev) != expected_dev or int(info.st_ino) != expected_ino
            ):
                raise SystemExit(_fail(f"目标 inode 已变化：{path}"))
        validated.append(dict(item))
    return validated


def _remove_tree(path: Path) -> tuple[int, int, list[str]]:
    files = 0
    bytes_removed = 0
    errors: list[str] = []

    def walk(current: Path) -> None:
        nonlocal files, bytes_removed
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            os.unlink(entry.path)
                        elif entry.is_dir(follow_symlinks=False):
                            walk(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            bytes_removed += int(entry.stat(follow_symlinks=False).st_size or 0)
                            os.unlink(entry.path)
                            files += 1
                    except OSError as exc:
                        errors.append(f"{entry.path}: {type(exc).__name__}: {exc}")
            os.rmdir(current)
        except OSError as exc:
            errors.append(f"{current}: {type(exc).__name__}: {exc}")

    walk(path)
    return files, bytes_removed, errors


def _delete_target(path: Path) -> dict[str, Any]:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"status": "missing", "bytes": 0, "files": 0}
    except OSError as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    if path.is_symlink():
        return {"status": "failed", "error": "root_is_symlink"}
    if path.is_dir():
        staged = path.with_name(f".{path.name}.delete-{os.getpid()}")
        try:
            os.replace(path, staged)
        except OSError as exc:
            return {"status": "failed", "error": f"rename_failed: {exc}"}
        files, bytes_removed, errors = _remove_tree(staged)
        return {
            "status": "deleted" if not errors else "partial",
            "bytes": bytes_removed,
            "files": files,
            "errors": errors,
        }
    try:
        size = int(info.st_size or 0)
        os.unlink(path)
        return {"status": "deleted", "bytes": size, "files": 1}
    except OSError as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def _delete_backup_library(path: Path, keep_paths: list[Path]) -> dict[str, Any]:
    deleted = 0
    bytes_removed = 0
    kept = 0
    errors: list[str] = []
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    for entry in entries:
        if any(_is_within(entry, keep) or entry == keep for keep in keep_paths):
            kept += 1
            continue
        name = entry.name
        recognized = (
            (entry.is_file() and not entry.is_symlink() and (
                any(fnmatch.fnmatch(name, pattern) for pattern in BACKUP_PATTERNS)
            ))
            or (entry.is_dir() and not entry.is_symlink() and name.startswith(".backup-work-"))
        )
        if not recognized:
            kept += 1
            continue
        result = _delete_target(entry)
        if result.get("status") in {"deleted", "partial"}:
            deleted += 1
            bytes_removed += int(result.get("bytes") or 0)
        if result.get("errors"):
            errors.extend(result["errors"])
        if result.get("status") == "failed":
            errors.append(f"{entry}: {result.get('error')}")
    return {
        "status": "deleted" if not errors else "partial",
        "bytes": bytes_removed,
        "files": deleted,
        "kept": kept,
        "errors": errors,
    }


def _write_audit(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KarenBot local uninstall helper")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--log", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan).expanduser()
    try:
        plan = _load_plan(plan_path)
        _validate_plan(plan_path, plan)
    except SystemExit as exc:
        return int(exc.code or 2)
    audit_info = plan.get("audit") or {}
    audit_path = Path(str(audit_info.get("result_path") or ""))
    log_path = Path(args.log or audit_info.get("log_path") or audit_path.with_suffix(".log"))
    if log_path:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] helper start plan={plan.get('plan_id')}\n"
                )
        except OSError:
            pass

    audit: dict[str, Any] = {
        "format": 1,
        "operation": "uninstall",
        "plan_id": plan.get("plan_id"),
        "plan_digest": plan.get("plan_digest"),
        "state": "running",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": {
            "pid": (plan.get("backend") or {}).get("pid"),
            "stopped": False,
        },
        "backup": None,
        "targets": [],
        "retained": list(plan.get("retained") or []),
        "helper_pid": os.getpid(),
        "dry_run": bool(args.dry_run),
        "error": None,
    }
    helper_root = Path(__file__).resolve().parent
    try:
        _wait_backend(plan)
        audit["backend"]["stopped"] = True
        audit["backup"] = _verify_backup(plan)
        targets = _revalidate_targets(plan, helper_root)
        audit["targets"] = targets
        if args.dry_run:
            audit["state"] = "dry_run"
            for index, item in enumerate(targets):
                audit["targets"][index]["status"] = "not_deleted_dry_run"
                if log_path:
                    try:
                        with log_path.open("a", encoding="utf-8") as handle:
                            handle.write(f"dry-run target={item.get('path')}\n")
                    except OSError:
                        pass
            _write_audit(audit_path, audit)
            return 0

        _write_audit(audit_path, audit)
        keep_paths = [Path(str(item)) for item in plan.get("keep_paths") or []]
        order = {
            "launcher": 0,
            "env_file": 1,
            "systemd_unit": 2,
            "systemd_enable_link": 2,
            "backup_library": 3,
            "known_data_root": 4,
            "data_root": 5,
            "data_dir": 6,
            "project_root": 99,
        }
        results: list[dict[str, Any]] = []
        for item in sorted(targets, key=lambda x: order.get(str(x.get("kind")), 50)):
            path = Path(str(item.get("path") or ""))
            if not item.get("exists"):
                results.append({**item, "status": "missing"})
                continue
            if item.get("kind") == "backup_library":
                result = _delete_backup_library(path, keep_paths)
            elif item.get("kind") == "systemd_enable_link":
                try:
                    if path.is_symlink():
                        os.unlink(path)
                        result = {"status": "deleted", "bytes": 0, "files": 1}
                    else:
                        result = {"status": "failed", "error": "not_symlink"}
                except OSError as exc:
                    result = {"status": "failed", "error": str(exc)}
            else:
                result = _delete_target(path)
            results.append({**item, "status": result.get("status"), **{
                key: result[key] for key in ("bytes", "files", "errors", "error", "kept")
                if key in result
            }})
            if log_path:
                try:
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(
                            f"target={path} status={result.get('status')} "
                            f"bytes={result.get('bytes', 0)} errors={result.get('errors') or []}\n"
                        )
                except OSError:
                    pass
        errors = [
            str(result.get("error") or result.get("errors"))
            for result in results
            if result.get("status") in {"failed", "partial"}
        ]
        audit["targets"] = results
        audit["state"] = "partial" if errors else "completed"
        audit["error"] = "; ".join(errors)[:500] if errors else None
        audit["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_audit(audit_path, audit)
        return 0 if not errors else 2
    except SystemExit as exc:
        audit["state"] = "aborted"
        audit["error"] = str(exc)
        audit["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_audit(audit_path, audit)
        raise
    except Exception as exc:  # noqa: BLE001
        audit["state"] = "failed"
        audit["error"] = f"{type(exc).__name__}: {exc}"[:500]
        audit["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_audit(audit_path, audit)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
