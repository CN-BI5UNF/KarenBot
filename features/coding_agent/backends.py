"""Execution backends for native coding-agent tools.

Both backends return plain dictionaries that the tool layer wraps into the
standard KarenBot tool-result envelope.  Host reads/writes stay inside the AI
workspace; container reads/writes stay inside ``/workspace`` and are validated
again inside the container helper.
"""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import json
import os
import re
import shlex
import shutil
import signal
import stat as stat_module
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from .types import (
    MAX_BASH_OUTPUT_BYTES,
    MAX_CUSTOM_TOOL_BYTES,
    MAX_GLOB_RESULTS,
    MAX_GREP_RESULTS,
    MAX_LS_RESULTS,
    MAX_READ_BYTES,
    MAX_WRITE_BYTES,
    result_error,
)

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".run",
        "runtime",
        ".karen-agents",
    }
)

_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TZ",
    "USER",
    "LOGNAME",
    "SHELL",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMFILES",
    "PROGRAMW6432",
    "PROGRAMDATA",
)

_APPLY_PATCH_SCRIPT = r'''
import json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def fail(message, code="agent_patch_failed"):
    print(json.dumps({"ok": False, "status": "failed", "brief": message,
                      "error": message, "code": code}, ensure_ascii=False))
    raise SystemExit(1)

def parse_path(raw, strip):
    text = str(raw or "").strip()
    if "\t" in text:
        text = text.split("\t", 1)[0]
    if text == "/dev/null":
        return "/dev/null"
    parts = [p for p in text.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(part == ".." for part in parts):
        fail("补丁路径不允许包含 ..：%s" % text)
    if strip:
        parts = parts[strip:]
    if not parts:
        fail("补丁路径为空或不含有效文件名：%s" % text)
    return "/".join(parts)

def read_lines(path):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        fail("读取文件失败：%s（%s）" % (path, exc))
    if b"\x00" in raw[:8192]:
        fail("不能对二进制文件应用补丁：%s" % path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("文件不是有效 UTF-8：%s（%s）" % (path, exc))
    return text.splitlines(keepends=True)

def parse_hunks(lines, index):
    hunks = []
    while index < len(lines):
        header = lines[index]
        if header.startswith("--- ") or header.startswith("diff ") or header.startswith("Index: "):
            break
        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
        if not match:
            if header.startswith("@@") or header.strip():
                fail("无效的 hunk 头：%s" % header.rstrip())
            break
        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        index += 1
        rows = []
        old_left, new_left = old_count, new_count
        while index < len(lines) and (old_left > 0 or new_left > 0):
            line = lines[index]
            if line.startswith("\\"):
                if rows:
                    kind, text = rows[-1]
                    rows[-1] = (kind, text.rstrip("\r\n"))
                index += 1
                continue
            if line.startswith(" ") or line in ("\n", ""):
                kind, text = " ", line[1:] if line.startswith(" ") else line
                old_left -= 1
                new_left -= 1
            elif line.startswith("+"):
                kind, text = "+", line[1:]
                new_left -= 1
            elif line.startswith("-"):
                kind, text = "-", line[1:]
                old_left -= 1
            else:
                fail("无效的 hunk 行：%r" % line.rstrip())
            if old_left < 0 or new_left < 0:
                fail("hunk 行数与头部计数不匹配")
            rows.append((kind, text))
            index += 1
        if old_left or new_left:
            fail("hunk 提前结束：还差 %d 行旧内容、%d 行新内容"
                 % (old_left, new_left))
        while index < len(lines) and lines[index].startswith("\\"):
            if rows:
                kind, text = rows[-1]
                rows[-1] = (kind, text.rstrip("\r\n"))
            index += 1
        hunks.append((old_start, rows))
    return hunks, index

def apply_hunks(source, hunks):
    # Preserve the target file's existing line ending when inserting lines.
    # CRLF files are common on Windows; patch context is compared without EOL.
    newline = "\n"
    if any(line.endswith("\r\n") for line in source):
        newline = "\r\n"
    result = []
    position = 0
    for old_start, rows in hunks:
        target = old_start - 1
        if target < position or target > len(source):
            fail("hunk 起点越界或与上一段重叠")
        result.extend(source[position:target])
        position = target
        for kind, text in rows:
            if kind in (" ", "-"):
                if position >= len(source):
                    fail("补丁上下文超出文件末尾")
                actual = source[position]
                if actual.rstrip("\r\n") != text.rstrip("\r\n"):
                    fail("补丁上下文不匹配：期望 %r，实际 %r"
                         % (text.rstrip("\r\n"), actual.rstrip("\r\n")))
                if kind == " ":
                    result.append(actual)
                position += 1
            else:
                result.append(text.rstrip("\r\n") + newline)
    result.extend(source[position:])
    return result

def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        fail("请求必须是 JSON 对象")
    patch = str(request.get("patch") or "")
    if not patch.strip():
        fail("patch 不能为空", "agent_invalid_argument")
    strip = int(request.get("strip", 1))
    if strip < 0 or strip > 8:
        fail("strip 必须在 0-8 之间", "agent_invalid_argument")
    dry_run = bool(request.get("dry_run", False))
    lines = patch.splitlines(keepends=True)
    root = os.path.realpath(os.getcwd())
    plans = []
    additions = 0
    deletions = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("diff ") or line.startswith("Index: "):
            index += 1
            continue
        if not line.startswith("--- "):
            fail("补丁格式错误：期望 --- 行，实际 %r" % line.rstrip())
        if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
            fail("补丁格式错误：--- 行后缺少 +++ 行")
        old_raw = line[4:]
        new_raw = lines[index + 1][4:]
        old_path = parse_path(old_raw, strip)
        new_path = parse_path(new_raw, strip)
        index += 2
        hunks, index = parse_hunks(lines, index)
        if not hunks and old_path != "/dev/null" and new_path != "/dev/null":
            fail("补丁没有 hunk：%s" % new_path)
        if old_path == "/dev/null":
            target = new_path
            created = True
            source = []
            result = []
            for _, rows in hunks:
                for kind, text in rows:
                    if kind == "-":
                        fail("新建文件的补丁不能包含删除行")
                    if kind == "+":
                        result.append(text.rstrip("\r\n") + "\n")
            final = result
        elif new_path == "/dev/null":
            target = old_path
            created = False
            source = read_lines(os.path.join(root, target))
            final = apply_hunks(source, hunks)
            if final:
                fail("删除文件的补丁未能删除全部内容：%s" % target)
        else:
            if old_path != new_path:
                fail("不支持重命名补丁：%s -> %s" % (old_path, new_path))
            target = new_path
            created = False
            source = read_lines(os.path.join(root, target))
            final = apply_hunks(source, hunks)
        relative = target.replace("/", os.sep)
        full = os.path.join(root, relative)
        real = os.path.realpath(full)
        if real != root and not real.startswith(root + os.sep):
            fail("补丁路径越出工作区：%s" % target, "agent_path_forbidden")
        if os.path.islink(full):
            fail("补丁路径是符号链接：%s" % target, "agent_path_forbidden")
        if created and os.path.exists(full):
            fail("新建文件已存在：%s" % target)
        if not created and not os.path.isfile(full):
            fail("文件不存在：%s" % target, "agent_file_missing")
        for kind, _ in (row for _, rows in hunks for row in rows):
            if kind == "+":
                additions += 1
            elif kind == "-":
                deletions += 1
        plans.append((target, full, created, new_path == "/dev/null", final))

    if not plans:
        fail("补丁没有包含任何文件变更")
    if not dry_run:
        for target, full, created, deleting, final in plans:
            if deleting:
                try:
                    os.unlink(full)
                except OSError as exc:
                    fail("删除文件失败：%s（%s）" % (target, exc))
                continue
            data = "".join(final).encode("utf-8")
            parent = os.path.dirname(full) or root
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as exc:
                fail("创建父目录失败：%s（%s）" % (target, exc))
            mode = 0o644
            if not created:
                try:
                    mode = os.stat(full).st_mode & 0o777
                except OSError:
                    mode = 0o644
            temp = os.path.join(parent, ".%s.karen-patch-%s.tmp"
                                % (os.path.basename(full), os.getpid()))
            try:
                with open(temp, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp, mode)
                os.replace(temp, full)
            except OSError as exc:
                try:
                    os.unlink(temp)
                except OSError:
                    pass
                fail("写入文件失败：%s（%s）" % (target, exc))

    files = []
    for target, _full, created, deleting, _final in plans:
        files.append({
            "path": target,
            "created": bool(created),
            "deleted": bool(deleting),
            "modified": not created and not deleting,
        })
    print(json.dumps({
        "ok": True,
        "status": "done",
        "brief": "补丁%s：%d 个文件，+%d/-%d。"
                 % ("预检通过" if dry_run else "已应用", len(files), additions, deletions),
        "files": files,
        "additions": additions,
        "deletions": deletions,
        "dry_run": dry_run,
    }, ensure_ascii=False))

main()
'''


class AgentPathError(ValueError):
    """Raised when a host path escapes the coding workspace."""


CUSTOM_TOOLS_DIR = ".karen-agents/tools"
CUSTOM_TMP_DIR = ".karen-agents/tmp"
CUSTOM_TOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def valid_custom_tool_name(name: str) -> bool:
    return bool(CUSTOM_TOOL_NAME_RE.fullmatch(str(name or "")))


def _apply_patch_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    data = payload.get("output_json")
    if isinstance(data, dict):
        for key in (
            "files",
            "additions",
            "deletions",
            "dry_run",
            "code",
            "error",
            "brief",
        ):
            if key in data:
                payload[key] = data[key]
        payload["ok"] = bool(data.get("ok")) and bool(payload.get("ok"))
        payload["status"] = "done" if payload["ok"] else "failed"
    if not payload.get("ok") and not payload.get("error"):
        # A subprocess failure may leave stdout unparsable (for example on a
        # Windows console with legacy encoding); never drop the only diagnostic.
        payload["error"] = str(
            payload.get("stderr") or payload.get("brief") or "补丁应用失败"
        ).strip() or "补丁应用失败"
    return payload


def _custom_execution_result(
    result: dict[str, Any],
    *,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Attach custom-tool metadata and parse JSON stdout when possible."""
    payload = dict(result)
    payload["tool"] = name or "custom"
    payload["args"] = args
    payload["output_json"] = None
    stdout = str(payload.get("stdout") or "")
    if stdout.strip():
        try:
            payload["output_json"] = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            payload["output_json"] = None
    if payload.get("ok"):
        payload["status"] = "done"
        payload["brief"] = f"自定义工具 {name or 'custom'} 执行完成。"
    elif payload.get("timed_out"):
        payload["brief"] = f"自定义工具 {name or 'custom'} 执行超时。"
    else:
        payload["status"] = "failed"
        payload["brief"] = (
            f"自定义工具 {name or 'custom'} 失败，exit_code={payload.get('exit_code')}。"
        )
    return payload


def _safe_env(*, home: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if value:
            env[key] = value
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("LANG", "C.UTF-8")
    env["HOME"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def _check_path(path: Path, root: Path) -> Path:
    """Resolve and verify a host path stays inside *root*."""
    try:
        resolved_root = root.resolve(strict=False)
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise AgentPathError(f"路径解析失败: {exc}") from exc
    if not resolved.is_relative_to(resolved_root):
        raise AgentPathError(f"路径不在 workspace 内：{path}")
    return resolved


def _read_text_strict(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        raise ValueError("binary_file")
    return raw.decode("utf-8")


def _line_numbered(lines: list[str], start: int) -> str:
    return "\n".join(
        f"{start + index}\t{line.rstrip(chr(13) + chr(10))}"
        for index, line in enumerate(lines)
    )


def _count_occurrences(text: str, needle: str) -> int:
    if not needle:
        return 0
    return text.count(needle)


class HostBackend:
    """Host workspace backend.  Bash uses bubblewrap by default."""

    kind: Literal["host"] = "host"

    def __init__(
        self,
        workspace_dir: Path,
        *,
        execution_mode: Literal["sandbox", "host"] = "sandbox",
        sandbox_network: bool = True,
    ) -> None:
        self.workspace = workspace_dir.resolve(strict=False)
        self.execution_mode = execution_mode
        self.sandbox_network = bool(sandbox_network)

    # ---------------------------------------------------------- paths
    def _path(self, value: str) -> Path:
        # Lazy import keeps tools/__init__ from importing this module while it
        # is still initializing (tools.coding_tools imports this backend).
        from tools.workspace import WorkspaceError, resolve_in_workspace

        try:
            resolved = resolve_in_workspace(value, self.workspace)
        except WorkspaceError as exc:
            raise AgentPathError(str(exc)) from exc
        return _check_path(resolved, self.workspace)

    def _cwd(self, value: str) -> Path:
        cwd = self._path(value or ".")
        if not cwd.is_dir():
            raise AgentPathError(f"工作目录不存在：{value}")
        return cwd

    # ---------------------------------------------------------- read
    async def read(
        self,
        path: str,
        *,
        offset: int = 1,
        limit: int = 2000,
        max_bytes: int = 51200,
    ) -> dict[str, Any]:
        try:
            target = self._path(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if not target.exists():
            return result_error(f"文件不存在：{path}", code="agent_file_missing")
        if not target.is_file():
            return result_error(f"不是普通文件：{path}", code="agent_not_file")
        try:
            info = target.stat()
        except OSError as exc:
            return result_error(f"读取文件状态失败：{exc}", code="agent_read_failed")
        if info.st_size > MAX_READ_BYTES * 8 and offset <= 1:
            return result_error(
                "文件过大，请使用 offset/limit 分页读取",
                code="agent_file_too_large",
                size_bytes=info.st_size,
            )
        if info.st_size > MAX_READ_BYTES * 16:
            return result_error(
                "文件超过读取上限，请使用 agent_bash 分段处理",
                code="agent_file_too_large",
                size_bytes=info.st_size,
            )
        try:
            raw = await asyncio.to_thread(target.read_bytes)
        except OSError as exc:
            return result_error(f"读取文件失败：{exc}", code="agent_read_failed")
        if b"\x00" in raw[:8192]:
            return {
                "ok": True,
                "status": "binary",
                "brief": f"{path} 是二进制文件，未按文本读取。",
                "path": _relative(target, self.workspace),
                "binary": True,
                "bytes": len(raw),
                "size_bytes": info.st_size,
            }
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return result_error(
                f"文件不是有效 UTF-8：{exc}",
                code="agent_encoding_error",
                binary=False,
                bytes=len(raw),
            )
        lines = text.splitlines(keepends=True)
        total_lines = len(lines)
        start = max(1, int(offset))
        end = min(total_lines, start - 1 + max(1, int(limit)))
        selected = lines[start - 1 : end]
        rendered: list[str] = []
        used = 0
        for index, line in enumerate(selected, start=start):
            piece = f"{index}\t{line.rstrip(chr(13) + chr(10))}"
            encoded = len(piece.encode("utf-8", errors="replace")) + 1
            if rendered and used + encoded > max_bytes:
                break
            rendered.append(piece)
            used += encoded
        content = "\n".join(rendered)
        returned_end = start + len(rendered) - 1 if rendered else start - 1
        truncated = returned_end < total_lines
        return {
            "ok": True,
            "status": "inline",
            "brief": (
                f"已读取 {path} 第 {start}-{returned_end} 行"
                + ("（已截断）" if truncated else "")
            ),
            "path": _relative(target, self.workspace),
            "content": content,
            "start_line": start,
            "end_line": returned_end,
            "total_lines": total_lines,
            "next_offset": returned_end + 1 if truncated else None,
            "truncated": truncated,
            "bytes": len(content.encode("utf-8")),
            "size_bytes": info.st_size,
        }

    # ---------------------------------------------------------- write
    async def write(
        self,
        path: str,
        content: str,
        *,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        data = str(content or "").encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            return result_error("写入内容超过 8 MiB 上限", code="agent_file_too_large")
        if b"\x00" in data:
            return result_error("写入内容包含 NUL 字节", code="agent_content_invalid")
        try:
            target = self._path(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if target.exists() and target.is_dir():
            return result_error(f"目标是一个目录：{path}", code="agent_not_file")
        existed = target.exists()
        parent = target.parent
        if not parent.exists():
            if not create_parents:
                return result_error(
                    f"父目录不存在：{parent}", code="agent_parent_missing"
                )
            try:
                await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)
            except OSError as exc:
                return result_error(f"创建父目录失败：{exc}", code="agent_write_failed")
        old_mode: int | None = None
        if existed:
            try:
                old_mode = stat_module.S_IMODE(target.stat().st_mode)
            except OSError:
                old_mode = None
        try:
            await asyncio.to_thread(
                _atomic_write_bytes,
                target,
                data,
                old_mode if old_mode is not None else 0o644,
            )
        except OSError as exc:
            return result_error(f"写入失败：{exc}", code="agent_write_failed")
        return {
            "ok": True,
            "status": "done",
            "brief": f"已{'覆盖' if existed else '创建'}文件 {_relative(target, self.workspace)}",
            "path": _relative(target, self.workspace),
            "bytes": len(data),
            "created": not existed,
            "updated": existed,
        }

    # ---------------------------------------------------------- edit
    async def edit(
        self,
        path: str,
        edits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            target = self._path(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if not target.is_file():
            return result_error(f"文件不存在：{path}", code="agent_file_missing")
        try:
            size = target.stat().st_size
        except OSError as exc:
            return result_error(f"读取文件状态失败：{exc}", code="agent_read_failed")
        if size > MAX_WRITE_BYTES:
            return result_error(
                "文件超过编辑上限（8 MiB）", code="agent_file_too_large", size_bytes=size
            )
        try:
            before = await asyncio.to_thread(_read_text_strict, target)
        except ValueError:
            return result_error("文件是二进制或不是有效 UTF-8", code="agent_encoding_error")
        except OSError as exc:
            return result_error(f"读取文件失败：{exc}", code="agent_read_failed")
        try:
            after, replacements = _apply_edits(before, edits)
        except ValueError as exc:
            return result_error(str(exc), code="agent_edit_failed")
        if after == before:
            return {
                "ok": True,
                "status": "no_change",
                "brief": "编辑未产生变化。",
                "path": _relative(target, self.workspace),
                "replacements": replacements,
            }
        data = after.encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            return result_error("编辑后内容超过 8 MiB", code="agent_file_too_large")
        try:
            old_mode = stat_module.S_IMODE(target.stat().st_mode)
        except OSError:
            old_mode = 0o644
        try:
            await asyncio.to_thread(_atomic_write_bytes, target, data, old_mode)
        except OSError as exc:
            return result_error(f"写回失败：{exc}", code="agent_write_failed")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{_relative(target, self.workspace)}",
                tofile=f"b/{_relative(target, self.workspace)}",
                n=3,
            )
        )
        return {
            "ok": True,
            "status": "done",
            "brief": f"已编辑 {_relative(target, self.workspace)}，替换 {replacements} 处。",
            "path": _relative(target, self.workspace),
            "replacements": replacements,
            "diff": diff[:20000],
            "bytes": len(data),
        }

    # ---------------------------------------------------------- bash
    async def bash(
        self,
        command: str,
        *,
        cwd: str = ".",
        timeout_seconds: float = 120.0,
        stdin: str = "",
    ) -> dict[str, Any]:
        if not command.strip():
            return result_error("command 不能为空", code="agent_invalid_argument")
        if len(command.encode("utf-8")) > 64 * 1024:
            return result_error("命令超过 64 KiB", code="agent_invalid_argument")
        try:
            cwd_path = self._cwd(cwd)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        stdin_bytes = str(stdin or "").encode("utf-8")
        if len(stdin_bytes) > 1024 * 1024:
            return result_error("stdin 超过 1 MiB", code="agent_invalid_argument")
        if self.execution_mode == "host":
            argv = _host_shell_command(command)
            env = _safe_env(home=Path.home())
            sandbox = "host"
        else:
            bwrap = shutil.which("bwrap")
            if bwrap is None:
                return result_error(
                    "bubblewrap 不可用；请安装 bwrap 或把本机执行模式切换为 host。",
                    code="agent_sandbox_unavailable",
                )
            argv = _bwrap_shell_command(
                bwrap,
                command,
                cwd_path,
                self.workspace,
                network=self.sandbox_network,
            )
            env = None
            sandbox = "bubblewrap"
        return await _run_bounded(
            argv,
            cwd=cwd_path,
            env=env,
            stdin_bytes=stdin_bytes,
            timeout_seconds=timeout_seconds,
            sandbox=sandbox,
        )

    # ---------------------------------------------------------- glob
    async def glob(
        self,
        pattern: str,
        *,
        path: str = ".",
        limit: int = 200,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        if not pattern:
            return result_error("pattern 不能为空", code="agent_invalid_argument")
        try:
            root = self._cwd(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        limit = max(1, min(int(limit), MAX_GLOB_RESULTS))
        matches: list[tuple[float, str]] = []
        for current, dirnames, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in _SKIP_DIRS
                and (include_hidden or not name.startswith("."))
                and not (current_path / name).is_symlink()
            ]
            for name in filenames:
                if not include_hidden and name.startswith("."):
                    continue
                full = current_path / name
                if full.is_symlink() or not full.is_file():
                    continue
                rel = _relative(full, root)
                if not _glob_match(rel, pattern, name):
                    continue
                try:
                    mtime = full.stat().st_mtime
                except OSError:
                    mtime = 0.0
                matches.append((mtime, rel))
                if len(matches) >= limit * 4:
                    break
            if len(matches) >= limit * 4:
                break
        matches.sort(key=lambda item: (-item[0], item[1]))
        selected = [rel for _, rel in matches[:limit]]
        return {
            "ok": True,
            "status": "inline",
            "brief": f"匹配到 {len(selected)} 个文件。",
            "path": _relative(root, self.workspace),
            "pattern": pattern,
            "matches": selected,
            "truncated": len(matches) > limit,
        }

    # ---------------------------------------------------------- grep
    async def grep(
        self,
        pattern: str,
        *,
        path: str = ".",
        glob: str = "",
        ignore_case: bool = False,
        literal: bool = False,
        context: int = 0,
        output_mode: Literal["content", "files_with_matches", "count"] = "content",
        head_limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not pattern:
            return result_error("pattern 不能为空", code="agent_invalid_argument")
        try:
            root = self._cwd(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        limit = max(1, min(int(head_limit), MAX_GREP_RESULTS))
        rg = shutil.which("rg")
        if rg:
            result = await _grep_with_rg(
                rg,
                root,
                pattern,
                glob=glob,
                ignore_case=ignore_case,
                literal=literal,
                context=context,
                output_mode=output_mode,
                limit=limit,
                offset=offset,
            )
        else:
            result = await asyncio.to_thread(
                _grep_python,
                root,
                pattern,
                glob=glob,
                ignore_case=ignore_case,
                literal=literal,
                context=context,
                output_mode=output_mode,
                limit=limit,
                offset=offset,
            )
        if result.get("ok"):
            result["path"] = _relative(root, self.workspace)
        return result

    # ---------------------------------------------------------- ls
    async def ls(
        self,
        path: str = ".",
        *,
        limit: int = 500,
        include_hidden: bool = True,
    ) -> dict[str, Any]:
        try:
            root = self._cwd(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        limit = max(1, min(int(limit), MAX_LS_RESULTS))
        entries = await asyncio.to_thread(
            _list_dir, root, limit=limit, include_hidden=include_hidden
        )
        return {
            "ok": True,
            "status": "inline",
            "brief": f"列出 {len(entries)} 项。",
            "path": _relative(root, self.workspace),
            "entries": entries,
            "truncated": len(entries) >= limit,
        }

    # ---------------------------------------------------------- raw / delete
    async def read_raw(
        self,
        path: str,
        *,
        max_bytes: int = MAX_READ_BYTES,
    ) -> dict[str, Any]:
        try:
            target = self._path(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if not target.is_file():
            return result_error(f"文件不存在：{path}", code="agent_file_missing")
        try:
            size = target.stat().st_size
        except OSError as exc:
            return result_error(f"读取文件状态失败：{exc}", code="agent_read_failed")
        if size > max(1024, int(max_bytes)):
            return result_error(
                "文件过大，不能作为自定义工具读取",
                code="agent_file_too_large",
                size_bytes=size,
            )
        try:
            text = await asyncio.to_thread(_read_text_strict, target)
        except ValueError:
            return result_error("文件是二进制或不是有效 UTF-8", code="agent_encoding_error")
        except OSError as exc:
            return result_error(f"读取文件失败：{exc}", code="agent_read_failed")
        return {
            "ok": True,
            "status": "inline",
            "brief": f"已读取 {path}（原始文本）。",
            "path": _relative(target, self.workspace),
            "content": text,
            "bytes": len(text.encode("utf-8")),
            "size_bytes": size,
        }

    async def delete(self, path: str) -> dict[str, Any]:
        try:
            target = self._path(path)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if not target.exists():
            return result_error(f"文件不存在：{path}", code="agent_file_missing")
        if target.is_dir():
            return result_error(f"目标是目录：{path}", code="agent_not_file")
        try:
            await asyncio.to_thread(target.unlink)
        except OSError as exc:
            return result_error(f"删除失败：{exc}", code="agent_delete_failed")
        return {
            "ok": True,
            "status": "done",
            "brief": f"已删除 {_relative(target, self.workspace)}。",
            "path": _relative(target, self.workspace),
            "deleted": True,
        }

    # ---------------------------------------------------------- custom tools
    async def write_custom_tool(
        self,
        name: str,
        code: str,
        description: str,
    ) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名必须匹配 [A-Za-z][A-Za-z0-9_-]{0,63}", code="agent_invalid_argument")
        data = str(code or "").encode("utf-8")
        if not data.strip():
            return result_error("工具代码不能为空", code="agent_invalid_argument")
        if len(data) > MAX_CUSTOM_TOOL_BYTES:
            return result_error("工具代码超过 256 KiB", code="agent_file_too_large")
        try:
            directory = self._path(CUSTOM_TOOLS_DIR)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        try:
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
            target = directory / f"{name}.py"
            await asyncio.to_thread(_atomic_write_bytes, target, data, 0o600)
            meta = {
                "name": name,
                "description": str(description or "").strip()[:1000],
                "created_at": time.time(),
                "bytes": len(data),
            }
            meta_bytes = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            await asyncio.to_thread(
                _atomic_write_bytes, directory / f"{name}.json", meta_bytes, 0o600
            )
        except OSError as exc:
            return result_error(f"写入自定义工具失败：{exc}", code="agent_write_failed")
        return {
            "ok": True,
            "status": "done",
            "brief": f"已创建自定义工具 {name}。",
            "name": name,
            "path": f"{CUSTOM_TOOLS_DIR}/{name}.py",
            "bytes": len(data),
            "created_at": meta["created_at"],
        }

    async def list_custom_tools(self) -> dict[str, Any]:
        try:
            directory = self._path(CUSTOM_TOOLS_DIR)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        if not directory.is_dir():
            return {
                "ok": True,
                "status": "inline",
                "brief": "还没有自定义工具。",
                "tools": [],
            }
        names = sorted(
            path.stem
            for path in directory.iterdir()
            if path.is_file() and path.suffix == ".py" and valid_custom_tool_name(path.stem)
        )
        tools: list[dict[str, Any]] = []
        for name in names:
            target = directory / f"{name}.py"
            meta: dict[str, Any] = {}
            meta_path = directory / f"{name}.json"
            try:
                parsed = json.loads(await asyncio.to_thread(meta_path.read_text, "utf-8"))
                if isinstance(parsed, dict):
                    meta = parsed
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                meta = {}
            try:
                size = target.stat().st_size
                mtime = target.stat().st_mtime
            except OSError:
                size = 0
                mtime = 0.0
            tools.append(
                {
                    "name": name,
                    "description": str(meta.get("description") or ""),
                    "bytes": size,
                    "created_at": meta.get("created_at"),
                    "mtime": mtime,
                }
            )
        return {
            "ok": True,
            "status": "inline",
            "brief": f"共有 {len(tools)} 个自定义工具。",
            "tools": tools,
        }

    async def read_custom_tool(self, name: str) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        return await self.read_raw(f"{CUSTOM_TOOLS_DIR}/{name}.py")

    async def delete_custom_tool(self, name: str) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        try:
            directory = self._path(CUSTOM_TOOLS_DIR)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        removed = False
        for suffix in (".py", ".json"):
            target = directory / f"{name}{suffix}"
            if not target.exists():
                continue
            try:
                await asyncio.to_thread(target.unlink)
            except OSError as exc:
                return result_error(f"删除自定义工具失败：{exc}", code="agent_delete_failed")
            removed = True
        if not removed:
            return result_error(f"自定义工具不存在：{name}", code="agent_file_missing")
        return {
            "ok": True,
            "status": "done",
            "brief": f"已删除自定义工具 {name}。",
            "name": name,
            "deleted": True,
        }

    async def run_custom_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        read = await self.read_custom_tool(name)
        if not read.get("ok"):
            return read
        return await self.run_custom(
            str(read.get("content") or ""),
            args,
            name=name,
            timeout_seconds=timeout_seconds,
        )

    async def run_custom(
        self,
        code: str,
        args: dict[str, Any],
        *,
        name: str = "",
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """Execute one LLM-authored Python tool with JSON args on stdin."""
        text = str(code or "")
        if not text.strip():
            return result_error("工具代码不能为空", code="agent_invalid_argument")
        data = text.encode("utf-8")
        if len(data) > MAX_CUSTOM_TOOL_BYTES:
            return result_error("工具代码超过 256 KiB", code="agent_file_too_large")
        try:
            tmp_dir = self._path(CUSTOM_TMP_DIR)
        except AgentPathError as exc:
            return result_error(str(exc), code="agent_path_forbidden")
        try:
            await asyncio.to_thread(tmp_dir.mkdir, parents=True, exist_ok=True)
        except OSError as exc:
            return result_error(f"创建临时目录失败：{exc}", code="agent_write_failed")
        script = tmp_dir / f"custom-{os.getpid()}-{time.time_ns()}-{uuid.uuid4().hex[:8]}.py"
        try:
            await asyncio.to_thread(_atomic_write_bytes, script, data, 0o600)
        except OSError as exc:
            return result_error(f"写入临时工具失败：{exc}", code="agent_write_failed")
        stdin_bytes = json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False).encode(
            "utf-8"
        )
        try:
            if self.execution_mode == "host":
                argv = [sys.executable, "-I", str(script)]
                env = _safe_env(home=self.workspace)
                sandbox = "host"
            else:
                bwrap = shutil.which("bwrap")
                if bwrap is None:
                    return result_error(
                        "bubblewrap 不可用；请安装 bwrap 或把本机执行模式切换为 host。",
                        code="agent_sandbox_unavailable",
                    )
                python = sys.executable or shutil.which("python3") or "/usr/bin/python3"
                inner = f"{shlex.quote(python)} -I {shlex.quote(str(script))}"
                argv = _bwrap_shell_command(
                    bwrap,
                    inner,
                    self.workspace,
                    self.workspace,
                    network=self.sandbox_network,
                )
                env = None
                sandbox = "bubblewrap"
            result = await _run_bounded(
                argv,
                cwd=self.workspace,
                env=env,
                stdin_bytes=stdin_bytes,
                timeout_seconds=timeout_seconds,
                sandbox=sandbox,
            )
        finally:
            try:
                await asyncio.to_thread(script.unlink)
            except OSError:
                pass
        return _custom_execution_result(result, name=name, args=args)

    # ---------------------------------------------------------- apply patch
    async def apply_patch(
        self,
        patch: str,
        *,
        strip: int = 1,
        dry_run: bool = False,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        result = await self.run_custom(
            _APPLY_PATCH_SCRIPT,
            {"patch": patch, "strip": strip, "dry_run": dry_run},
            name="apply_patch",
            timeout_seconds=timeout_seconds,
        )
        return _apply_patch_result(result)


class ContainerBackend:
    """Container backend using the hardened ContainerService."""

    kind: Literal["container"] = "container"

    def __init__(self, service: Any) -> None:
        self.service = service

    async def _helper(
        self, action: str, payload: dict[str, Any], *, timeout: float = 60.0
    ) -> dict[str, Any]:
        return await self.service.agent_helper(action, payload, timeout_seconds=timeout)

    async def read(
        self,
        path: str,
        *,
        offset: int = 1,
        limit: int = 2000,
        max_bytes: int = 51200,
    ) -> dict[str, Any]:
        return await self._helper(
            "read",
            {
                "path": path,
                "offset": offset,
                "limit": limit,
                "max_bytes": max_bytes,
            },
        )

    async def write(
        self,
        path: str,
        content: str,
        *,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        return await self._helper(
            "write",
            {
                "path": path,
                "content": content,
                "create_parents": create_parents,
            },
        )

    async def edit(
        self,
        path: str,
        edits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._helper("edit", {"path": path, "edits": edits})

    async def bash(
        self,
        command: str,
        *,
        cwd: str = ".",
        timeout_seconds: float = 120.0,
        stdin: str = "",
    ) -> dict[str, Any]:
        return await self.service.exec_agent(
            command,
            cwd=cwd or "/workspace",
            timeout_seconds=timeout_seconds,
            stdin=stdin,
        )

    async def glob(
        self,
        pattern: str,
        *,
        path: str = ".",
        limit: int = 200,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        return await self._helper(
            "glob",
            {
                "pattern": pattern,
                "path": path or "/workspace",
                "limit": limit,
                "include_hidden": include_hidden,
            },
        )

    async def grep(
        self,
        pattern: str,
        *,
        path: str = ".",
        glob: str = "",
        ignore_case: bool = False,
        literal: bool = False,
        context: int = 0,
        output_mode: Literal["content", "files_with_matches", "count"] = "content",
        head_limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await self._helper(
            "grep",
            {
                "pattern": pattern,
                "path": path or "/workspace",
                "glob": glob,
                "ignore_case": ignore_case,
                "literal": literal,
                "context": context,
                "output_mode": output_mode,
                "head_limit": head_limit,
                "offset": offset,
            },
        )

    async def ls(
        self,
        path: str = ".",
        *,
        limit: int = 500,
        include_hidden: bool = True,
    ) -> dict[str, Any]:
        return await self._helper(
            "ls",
            {
                "path": path or "/workspace",
                "limit": limit,
                "include_hidden": include_hidden,
            },
        )

    async def read_raw(
        self,
        path: str,
        *,
        max_bytes: int = MAX_READ_BYTES,
    ) -> dict[str, Any]:
        return await self._helper(
            "read_raw",
            {"path": path, "max_bytes": max_bytes},
        )

    async def delete(self, path: str) -> dict[str, Any]:
        return await self._helper("delete", {"path": path})

    async def write_custom_tool(
        self,
        name: str,
        code: str,
        description: str,
    ) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名必须匹配 [A-Za-z][A-Za-z0-9_-]{0,63}", code="agent_invalid_argument")
        data = str(code or "").encode("utf-8")
        if not data.strip():
            return result_error("工具代码不能为空", code="agent_invalid_argument")
        if len(data) > MAX_CUSTOM_TOOL_BYTES:
            return result_error("工具代码超过 256 KiB", code="agent_file_too_large")
        written = await self._helper(
            "write",
            {
                "path": f"{CUSTOM_TOOLS_DIR}/{name}.py",
                "content": data.decode("utf-8"),
            },
            timeout=60.0,
        )
        if not written.get("ok"):
            return written
        meta = {
            "name": name,
            "description": str(description or "").strip()[:1000],
            "created_at": time.time(),
            "bytes": len(data),
        }
        meta_result = await self._helper(
            "write",
            {
                "path": f"{CUSTOM_TOOLS_DIR}/{name}.json",
                "content": json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            },
            timeout=60.0,
        )
        if not meta_result.get("ok"):
            return meta_result
        return {
            "ok": True,
            "status": "done",
            "brief": f"已创建自定义工具 {name}。",
            "name": name,
            "path": f"{CUSTOM_TOOLS_DIR}/{name}.py",
            "bytes": len(data),
            "created_at": meta["created_at"],
        }

    async def list_custom_tools(self) -> dict[str, Any]:
        listed = await self._helper(
            "ls",
            {"path": CUSTOM_TOOLS_DIR, "limit": 500, "include_hidden": True},
            timeout=30.0,
        )
        if not listed.get("ok"):
            if str(listed.get("code") or "") in {
                "agent_not_directory",
                "agent_file_missing",
            }:
                return {
                    "ok": True,
                    "status": "inline",
                    "brief": "还没有自定义工具。",
                    "tools": [],
                }
            return listed
        entries = listed.get("entries") or []
        names = sorted(
            str(entry.get("name") or "")[: -len(".py")]
            for entry in entries
            if entry.get("type") == "file"
            and str(entry.get("name") or "").endswith(".py")
            and valid_custom_tool_name(str(entry.get("name") or "")[: -len(".py")])
        )
        tools: list[dict[str, Any]] = []
        for name in names:
            meta: dict[str, Any] = {}
            meta_result = await self._helper(
                "read_raw",
                {"path": f"{CUSTOM_TOOLS_DIR}/{name}.json", "max_bytes": 64 * 1024},
                timeout=30.0,
            )
            if meta_result.get("ok"):
                try:
                    parsed = json.loads(str(meta_result.get("content") or ""))
                    if isinstance(parsed, dict):
                        meta = parsed
                except (json.JSONDecodeError, ValueError):
                    meta = {}
            code_result = await self._helper(
                "read_raw",
                {"path": f"{CUSTOM_TOOLS_DIR}/{name}.py", "max_bytes": MAX_CUSTOM_TOOL_BYTES},
                timeout=30.0,
            )
            tools.append(
                {
                    "name": name,
                    "description": str(meta.get("description") or ""),
                    "bytes": int(code_result.get("size_bytes") or 0)
                    if code_result.get("ok")
                    else 0,
                    "created_at": meta.get("created_at"),
                }
            )
        return {
            "ok": True,
            "status": "inline",
            "brief": f"共有 {len(tools)} 个自定义工具。",
            "tools": tools,
        }

    async def read_custom_tool(self, name: str) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        return await self.read_raw(f"{CUSTOM_TOOLS_DIR}/{name}.py")

    async def delete_custom_tool(self, name: str) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        removed = False
        for suffix in (".py", ".json"):
            result = await self._helper(
                "delete", {"path": f"{CUSTOM_TOOLS_DIR}/{name}{suffix}"}, timeout=30.0
            )
            removed = removed or bool(result.get("ok"))
        if not removed:
            return result_error(f"自定义工具不存在：{name}", code="agent_file_missing")
        return {
            "ok": True,
            "status": "done",
            "brief": f"已删除自定义工具 {name}。",
            "name": name,
            "deleted": True,
        }

    async def run_custom_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        if not valid_custom_tool_name(name):
            return result_error("工具名无效", code="agent_invalid_argument")
        read = await self.read_custom_tool(name)
        if not read.get("ok"):
            return read
        return await self.run_custom(
            str(read.get("content") or ""),
            args,
            name=name,
            timeout_seconds=timeout_seconds,
        )

    async def run_custom(
        self,
        code: str,
        args: dict[str, Any],
        *,
        name: str = "",
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        text = str(code or "")
        if not text.strip():
            return result_error("工具代码不能为空", code="agent_invalid_argument")
        data = text.encode("utf-8")
        if len(data) > MAX_CUSTOM_TOOL_BYTES:
            return result_error("工具代码超过 256 KiB", code="agent_file_too_large")
        relative_script = f"{CUSTOM_TMP_DIR}/custom-{uuid.uuid4().hex}.py"
        written = await self._helper(
            "write",
            {"path": relative_script, "content": text},
            timeout=60.0,
        )
        if not written.get("ok"):
            return written
        script = f"/workspace/{relative_script}"
        stdin_text = json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False)
        try:
            result = await self.service.exec_agent(
                f"python3 -I {shlex.quote(script)}",
                cwd="/workspace",
                timeout_seconds=timeout_seconds,
                stdin=stdin_text,
            )
        finally:
            try:
                await self._helper("delete", {"path": relative_script}, timeout=30.0)
            except Exception:  # noqa: BLE001 - cleanup must not mask the result
                pass
        return _custom_execution_result(result, name=name, args=args)

    async def apply_patch(
        self,
        patch: str,
        *,
        strip: int = 1,
        dry_run: bool = False,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        result = await self.run_custom(
            _APPLY_PATCH_SCRIPT,
            {"patch": patch, "strip": strip, "dry_run": dry_run},
            name="apply_patch",
            timeout_seconds=timeout_seconds,
        )
        return _apply_patch_result(result)


# ============================================================
# helpers
# ============================================================


def _atomic_write_bytes(path: Path, data: bytes, mode: int) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f".{path.name}.karen-{os.getpid()}-{time.time_ns()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _apply_edits(text: str, edits: list[dict[str, Any]]) -> tuple[str, int]:
    if not edits:
        raise ValueError("edits 不能为空")
    # Validate and locate spans against the original text first.
    spans: list[tuple[int, int, str]] = []
    total = 0
    for index, edit in enumerate(edits):
        old = str(edit.get("old_string") or "")
        new = str(edit.get("new_string") or "")
        replace_all = bool(edit.get("replace_all"))
        if not old:
            raise ValueError(f"edits[{index}].old_string 不能为空")
        count = _count_occurrences(text, old)
        if count == 0:
            raise ValueError(f"edits[{index}] 未找到要替换的文本")
        if count > 1 and not replace_all:
            raise ValueError(
                f"edits[{index}] 匹配到 {count} 处；请提供更精确的 old_string 或 replace_all=true"
            )
        starts: list[int] = []
        cursor = 0
        while True:
            found = text.find(old, cursor)
            if found < 0:
                break
            starts.append(found)
            cursor = found + len(old)
            if not replace_all:
                break
        for start in starts:
            spans.append((start, start + len(old), new))
            total += 1
    spans.sort(key=lambda item: (item[0], item[1]))
    for (_, end, _), (next_start, _, _) in zip(spans, spans[1:], strict=False):
        if end > next_start:
            raise ValueError("edits 之间存在重叠替换区间")
    result = text
    for start, end, new in reversed(spans):
        result = result[:start] + new + result[end:]
    return result, total


def _glob_match(rel: str, pattern: str, name: str) -> bool:
    rel_posix = rel.replace("\\", "/")
    return fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(name, pattern)


def _bwrap_shell_command(
    bwrap: str,
    command: str,
    cwd: Path,
    workspace: Path,
    *,
    network: bool = True,
) -> list[str]:
    env = _safe_env(home=workspace)
    args = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup",
        "--cap-drop",
        "ALL",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
    ]
    if not network:
        args.append("--unshare-net")
    from tools.workspace_tools import _bwrap_ro_binds, _bwrap_usr_symlinks

    for target, link in _bwrap_usr_symlinks():
        args.extend(["--symlink", target, link])
    for root in _bwrap_ro_binds():
        args.extend(["--ro-bind", str(root), str(root)])
    args.extend(
        [
            "--bind",
            str(workspace),
            str(workspace),
            "--chdir",
            str(cwd),
            "--clearenv",
        ]
    )
    for key, value in env.items():
        args.extend(["--setenv", key, value])
    args.extend(["/bin/bash", "-lc", command])
    return args


async def _read_bounded(
    stream: asyncio.StreamReader | None,
    limit: int,
) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False
    chunks: list[bytes] = []
    total = 0
    truncated = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if total + len(chunk) > limit:
            chunks.append(chunk[: max(0, limit - total)])
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks), truncated


async def _run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    stdin_bytes: bytes,
    timeout_seconds: float,
    sandbox: str,
) -> dict[str, Any]:
    timeout = max(1.0, min(float(timeout_seconds), 600.0))
    started = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin_bytes else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError as exc:
        return result_error(f"无法启动命令：{exc}", code="agent_bash_failed")
    except OSError as exc:
        return result_error(f"无法启动命令：{exc}", code="agent_bash_failed")
    out_task = asyncio.create_task(_read_bounded(proc.stdout, MAX_BASH_OUTPUT_BYTES))
    err_task = asyncio.create_task(_read_bounded(proc.stderr, MAX_BASH_OUTPUT_BYTES))
    timed_out = False
    try:
        if stdin_bytes and proc.stdin is not None:
            proc.stdin.write(stdin_bytes)
            await proc.stdin.drain()
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            _kill_process_group(proc)
            await proc.wait()
    finally:
        stdout_bytes, out_truncated = await out_task
        stderr_bytes, err_truncated = await err_task
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": proc.returncode == 0 and not timed_out,
        "status": "done" if proc.returncode == 0 and not timed_out else "failed",
        "brief": (
            f"命令结束，exit_code={proc.returncode}"
            if not timed_out
            else f"命令超时（{int(timeout)} 秒）"
        ),
        "command": argv[-1],
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
        "timed_out": timed_out,
        "truncated": out_truncated or err_truncated,
        "duration_ms": duration_ms,
        "sandbox": sandbox,
    }


def _host_shell_command(command: str) -> list[str]:
    """Choose a usable shell for host-mode commands.

    Git for Windows provides bash, but it is not installed at ``/bin/bash``.
    Fall back to cmd.exe only when no bash is available at all.
    """
    if os.name == "nt":
        bash = shutil.which("bash")
        if not bash:
            candidates = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                / "Git"
                / "bin"
                / "bash.exe",
                Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
                / "Git"
                / "bin"
                / "bash.exe",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    bash = str(candidate)
                    break
        if bash:
            return [bash, "-lc", command]
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
    bash = shutil.which("bash") or "/bin/bash"
    return [bash, "-lc", command]


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    if os.name == "nt":
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def _grep_with_rg(
    rg: str,
    root: Path,
    pattern: str,
    *,
    glob: str,
    ignore_case: bool,
    literal: bool,
    context: int,
    output_mode: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    args = [rg, "--color", "never", "--no-messages", "--max-count", str(limit + offset)]
    if ignore_case:
        args.append("-i")
    if literal:
        args.append("-F")
    if context:
        args.extend(["-C", str(max(0, min(int(context), 20)))])
    if glob:
        args.extend(["--glob", glob])
    if output_mode == "files_with_matches":
        args.append("--files-with-matches")
    elif output_mode == "count":
        args.append("--count")
    else:
        args.append("--line-number")
        args.append("--no-heading")
    args.extend(["-e", pattern, "."])
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (OSError, asyncio.TimeoutError) as exc:
        return result_error(f"ripgrep 执行失败：{exc}", code="agent_grep_failed")
    lines = stdout.decode("utf-8", errors="replace").splitlines()
    if offset:
        lines = lines[int(offset) :]
    trimmed = lines[:limit]
    return {
        "ok": proc.returncode in (0, 1),
        "status": "inline",
        "brief": f"找到 {len(trimmed)} 条匹配结果。" if trimmed else "没有匹配结果。",
        "pattern": pattern,
        "output_mode": output_mode,
        "content": "\n".join(trimmed),
        "returned": len(trimmed),
        "truncated": len(lines) > limit,
        "stderr": stderr.decode("utf-8", errors="replace")[:2000],
    }


def _grep_python(
    root: Path,
    pattern: str,
    *,
    glob: str,
    ignore_case: bool,
    literal: bool,
    context: int,
    output_mode: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    flags = re.IGNORECASE if ignore_case else 0
    matcher = re.compile(re.escape(pattern) if literal else pattern, flags)
    results: list[str] = []
    files: list[str] = []
    counts: list[str] = []
    skipped = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _SKIP_DIRS and not (current_path / name).is_symlink()
        ]
        for name in sorted(filenames):
            if glob and not _glob_match(name, glob, name):
                continue
            full = current_path / name
            if full.is_symlink() or not full.is_file():
                continue
            try:
                if full.stat().st_size > 8 * 1024 * 1024:
                    continue
                text = full.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = _relative(full, root)
            matched_lines: list[str] = []
            count = 0
            lines = text.splitlines()
            for index, line in enumerate(lines, start=1):
                if not matcher.search(line):
                    continue
                count += 1
                if output_mode == "content":
                    if context:
                        start = max(1, index - context)
                        end = min(len(lines), index + context)
                        for ctx_index in range(start, end + 1):
                            prefix = ":" if ctx_index == index else "-"
                            matched_lines.append(
                                f"{rel}:{ctx_index}{prefix}{lines[ctx_index - 1][:500]}"
                            )
                    else:
                        matched_lines.append(f"{rel}:{index}:{line[:500]}")
                if count >= limit:
                    break
            if count:
                if output_mode == "files_with_matches":
                    files.append(rel)
                elif output_mode == "count":
                    counts.append(f"{rel}:{count}")
                else:
                    results.extend(matched_lines)
                if len(files) + len(results) + len(counts) >= limit:
                    skipped += 1
                    break
        if len(files) + len(results) + len(counts) >= limit:
            break
    if output_mode == "files_with_matches":
        content = "\n".join(files[offset:][:limit])
    elif output_mode == "count":
        content = "\n".join(counts[offset:][:limit])
    else:
        content = "\n".join(results[offset:][:limit])
    return {
        "ok": True,
        "status": "inline",
        "brief": "找到匹配结果。" if content else "没有匹配结果。",
        "pattern": pattern,
        "output_mode": output_mode,
        "content": content,
        "returned": len(content.splitlines()),
        "truncated": bool(skipped),
    }


def _list_dir(root: Path, *, limit: int, include_hidden: bool) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        iterator = os.scandir(root)
    except OSError:
        return entries
    with iterator:
        for entry in iterator:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if entry.is_symlink():
                kind = "symlink"
            elif entry.is_dir(follow_symlinks=False):
                kind = "dir"
            elif entry.is_file(follow_symlinks=False):
                kind = "file"
            else:
                kind = "other"
            item: dict[str, Any] = {
                "name": entry.name,
                "path": _relative(Path(entry.path), root),
                "type": kind,
                "size": info.st_size,
                "mtime": info.st_mtime,
                "mode": oct(stat_module.S_IMODE(info.st_mode)),
            }
            if kind == "symlink":
                try:
                    item["target"] = os.readlink(entry.path)
                except OSError:
                    item["target"] = ""
            entries.append(item)
            if len(entries) >= limit:
                break
    entries.sort(key=lambda item: (0 if item["type"] == "dir" else 1, item["name"].lower()))
    return entries


__all__ = ["ContainerBackend", "HostBackend"]
