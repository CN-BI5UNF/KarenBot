"""Standard-library-only helper executed inside the container.

The source is materialized as ``/tmp/karen-agent-helper.py`` by
:meth:`ContainerService.agent_helper` and run with ``python3 -I <file>``.
It reads one JSON request from stdin and writes one JSON response to stdout.
Actions are ``read``, ``read_raw``, ``write``, ``edit``, ``delete``, ``glob``,
``grep`` and ``ls``.  Keeping the whole path check and file operation inside
the container avoids shell interpolation and catches symlink escapes that the
lexical host-side validator cannot see.
"""

from __future__ import annotations

AGENT_HELPER_SOURCE = r'''
import difflib, fnmatch, json, os, re, stat, sys

ROOT = "/workspace"
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".run", "runtime",
    ".karen-agents",
}
MAX_READ_BYTES = 1024 * 1024
MAX_WRITE_BYTES = 8 * 1024 * 1024
MAX_RESULTS = 2000


def fail(message, code="container_agent_error", **extra):
    payload = {"ok": False, "status": "failed", "brief": message, "error": message, "code": code}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(0)


def norm(path):
    text = str(path or "").strip()
    if not text:
        fail("路径不能为空", "agent_path_invalid")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        fail("路径包含控制字符", "agent_path_invalid")
    if ".." in text.split("/"):
        fail("路径不允许 ..", "agent_path_forbidden")
    if not text.startswith("/"):
        text = ROOT + "/" + text
    normalized = os.path.normpath(text)
    if normalized != ROOT and not normalized.startswith(ROOT + "/"):
        fail("路径必须位于 /workspace", "agent_path_forbidden")
    real = os.path.realpath(normalized)
    if real != normalized:
        fail("路径包含符号链接或越界", "agent_path_forbidden")
    return normalized


def is_binary(data):
    return b"\x00" in data[:8192]


def read_text(path):
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        fail("读取文件失败：%s" % exc, "agent_read_failed")
    if is_binary(data):
        fail("文件是二进制文件", "agent_binary_file", binary=True, bytes=len(data))
    try:
        return data.decode("utf-8"), data
    except UnicodeDecodeError as exc:
        fail("文件不是有效 UTF-8：%s" % exc, "agent_encoding_error")


def atomic_write(path, data, mode):
    parent = os.path.dirname(path) or ROOT
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        fail("创建父目录失败：%s" % exc, "agent_write_failed")
    tmp = os.path.join(parent, ".%s.karen-%s.tmp" % (os.path.basename(path), os.getpid()))
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as exc:
        fail("写入失败：%s" % exc, "agent_write_failed")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def do_read(req):
    path = norm(req.get("path"))
    if not os.path.exists(path):
        fail("文件不存在", "agent_file_missing")
    if not os.path.isfile(path):
        fail("不是普通文件", "agent_not_file")
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        fail("读取文件状态失败：%s" % exc, "agent_read_failed")
    if info.st_size > 16 * 1024 * 1024:
        fail("文件超过读取上限，请使用 exec 分段处理", "agent_file_too_large")
    text, raw = read_text(path)
    lines = text.splitlines(keepends=True)
    total = len(lines)
    offset = max(1, int(req.get("offset") or 1))
    limit = max(1, min(int(req.get("limit") or 2000), 20000))
    max_bytes = max(1024, min(int(req.get("max_bytes") or 51200), MAX_READ_BYTES))
    start = min(offset, total + 1)
    end = min(total, start - 1 + limit)
    rendered = []
    used = 0
    for index in range(start, end + 1):
        piece = "%d\t%s" % (index, lines[index - 1].rstrip("\n"))
        size = len(piece.encode("utf-8", "replace")) + 1
        if rendered and used + size > max_bytes:
            break
        rendered.append(piece)
        used += size
    returned_end = start + len(rendered) - 1 if rendered else start - 1
    truncated = returned_end < total
    content = "\n".join(rendered)
    return {
        "ok": True,
        "status": "inline",
        "brief": "已读取 %s 第 %d-%d 行%s" % (
            rel(path), start, returned_end, "（已截断）" if truncated else ""
        ),
        "path": rel(path),
        "content": content,
        "start_line": start,
        "end_line": returned_end,
        "total_lines": total,
        "next_offset": returned_end + 1 if truncated else None,
        "truncated": truncated,
        "bytes": len(content.encode("utf-8")),
        "size_bytes": info.st_size,
    }


def do_read_raw(req):
    path = norm(req.get("path"))
    if not os.path.exists(path):
        fail("文件不存在", "agent_file_missing")
    if not os.path.isfile(path):
        fail("不是普通文件", "agent_not_file")
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        fail("读取文件状态失败：%s" % exc, "agent_read_failed")
    max_bytes = max(1024, min(int(req.get("max_bytes") or MAX_READ_BYTES), 8 * 1024 * 1024))
    if info.st_size > max_bytes:
        fail("文件过大", "agent_file_too_large", size_bytes=info.st_size)
    text, raw = read_text(path)
    return {
        "ok": True,
        "status": "inline",
        "brief": "已读取 %s（原始文本）。" % rel(path),
        "path": rel(path),
        "content": text,
        "bytes": len(raw),
        "size_bytes": info.st_size,
    }


def do_delete(req):
    path = norm(req.get("path"))
    if not os.path.exists(path):
        fail("文件不存在", "agent_file_missing")
    if not os.path.isfile(path):
        fail("不是普通文件", "agent_not_file")
    try:
        os.unlink(path)
    except OSError as exc:
        fail("删除文件失败：%s" % exc, "agent_delete_failed")
    return {
        "ok": True,
        "status": "done",
        "brief": "已删除 %s。" % rel(path),
        "path": rel(path),
        "deleted": True,
    }


def do_write(req):
    path = norm(req.get("path"))
    content = str(req.get("content") or "")
    data = content.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        fail("写入内容超过 8 MiB", "agent_file_too_large")
    if b"\x00" in data:
        fail("写入内容包含 NUL 字节", "agent_content_invalid")
    existed = os.path.exists(path)
    if existed and os.path.isdir(path):
        fail("目标是一个目录", "agent_not_file")
    if not existed and req.get("create_parents") is False:
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            fail("父目录不存在", "agent_parent_missing")
    mode = 0o644
    if existed:
        try:
            mode = stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode)
        except OSError:
            pass
    atomic_write(path, data, mode)
    return {
        "ok": True,
        "status": "done",
        "brief": "已%s文件 %s" % ("覆盖" if existed else "创建", rel(path)),
        "path": rel(path),
        "bytes": len(data),
        "created": not existed,
        "updated": existed,
    }


def apply_edits(text, edits):
    if not edits:
        fail("edits 不能为空", "agent_invalid_argument")
    spans = []
    total = 0
    for index, edit in enumerate(edits):
        old = str(edit.get("old_string") or "")
        new = str(edit.get("new_string") or "")
        replace_all = bool(edit.get("replace_all"))
        if not old:
            fail("edits[%d].old_string 不能为空" % index, "agent_invalid_argument")
        count = text.count(old)
        if count == 0:
            fail("edits[%d] 未找到要替换的文本" % index, "agent_edit_not_found")
        if count > 1 and not replace_all:
            fail("edits[%d] 匹配到 %d 处；请提供更精确的 old_string 或 replace_all=true" % (index, count), "agent_edit_ambiguous")
        cursor = 0
        found_count = 0
        while True:
            start = text.find(old, cursor)
            if start < 0:
                break
            spans.append((start, start + len(old), new))
            total += 1
            found_count += 1
            cursor = start + len(old)
            if not replace_all or found_count >= count:
                break
    spans.sort(key=lambda item: (item[0], item[1]))
    for (_, end, _), (next_start, _, _) in zip(spans, spans[1:]):
        if end > next_start:
            fail("edits 之间存在重叠替换区间", "agent_edit_overlap")
    result = text
    for start, end, new in reversed(spans):
        result = result[:start] + new + result[end:]
    return result, total


def do_edit(req):
    path = norm(req.get("path"))
    if not os.path.isfile(path):
        fail("文件不存在", "agent_file_missing")
    try:
        size = os.stat(path, follow_symlinks=False).st_size
    except OSError as exc:
        fail("读取文件状态失败：%s" % exc, "agent_read_failed")
    if size > MAX_WRITE_BYTES:
        fail("文件超过编辑上限（8 MiB）", "agent_file_too_large")
    before, raw = read_text(path)
    after, replacements = apply_edits(before, list(req.get("edits") or []))
    data = after.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        fail("编辑后内容超过 8 MiB", "agent_file_too_large")
    mode = stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode)
    atomic_write(path, data, mode)
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="a/" + rel(path),
        tofile="b/" + rel(path),
        n=3,
    ))
    return {
        "ok": True,
        "status": "done",
        "brief": "已编辑 %s，替换 %d 处。" % (rel(path), replacements),
        "path": rel(path),
        "replacements": replacements,
        "diff": diff[:20000],
        "bytes": len(data),
    }


def skip_dir(name, full, include_hidden):
    if name in SKIP_DIRS:
        return True
    if not include_hidden and name.startswith("."):
        return True
    try:
        return os.path.islink(full)
    except OSError:
        return True


def do_glob(req):
    root = norm(req.get("path") or ROOT)
    if not os.path.isdir(root):
        fail("目录不存在", "agent_not_directory")
    pattern = str(req.get("pattern") or "")
    if not pattern:
        fail("pattern 不能为空", "agent_invalid_argument")
    limit = max(1, min(int(req.get("limit") or 200), MAX_RESULTS))
    include_hidden = bool(req.get("include_hidden"))
    matches = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if not skip_dir(name, os.path.join(current, name), include_hidden)]
        for name in filenames:
            if not include_hidden and name.startswith("."):
                continue
            full = os.path.join(current, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            if not (fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern)):
                continue
            try:
                mtime = os.stat(full, follow_symlinks=False).st_mtime
            except OSError:
                mtime = 0.0
            matches.append((mtime, relative))
            if len(matches) >= limit * 4:
                break
        if len(matches) >= limit * 4:
            break
    matches.sort(key=lambda item: (-item[0], item[1]))
    selected = [item[1] for item in matches[:limit]]
    return {
        "ok": True,
        "status": "inline",
        "brief": "匹配到 %d 个文件。" % len(selected),
        "path": rel(root),
        "pattern": pattern,
        "matches": selected,
        "truncated": len(matches) > limit,
    }


def do_grep(req):
    root = norm(req.get("path") or ROOT)
    if not os.path.isdir(root):
        fail("目录不存在", "agent_not_directory")
    pattern = str(req.get("pattern") or "")
    if not pattern:
        fail("pattern 不能为空", "agent_invalid_argument")
    glob_pattern = str(req.get("glob") or "")
    flags = re.IGNORECASE if req.get("ignore_case") else 0
    try:
        matcher = re.compile(re.escape(pattern) if req.get("literal") else pattern, flags)
    except re.error as exc:
        fail("正则表达式无效：%s" % exc, "agent_invalid_argument")
    output_mode = str(req.get("output_mode") or "content")
    context = max(0, min(int(req.get("context") or 0), 20))
    limit = max(1, min(int(req.get("head_limit") or 100), 500))
    offset = max(0, int(req.get("offset") or 0))
    results, files, counts = [], [], []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if not skip_dir(name, os.path.join(current, name), True)]
        for name in sorted(filenames):
            if glob_pattern and not (fnmatch.fnmatch(name, glob_pattern) or fnmatch.fnmatch(name, glob_pattern)):
                continue
            full = os.path.join(current, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            try:
                if os.stat(full, follow_symlinks=False).st_size > 8 * 1024 * 1024:
                    continue
                with open(full, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            lines = text.splitlines()
            count = 0
            for index, line in enumerate(lines, start=1):
                if not matcher.search(line):
                    continue
                count += 1
                if output_mode == "content":
                    if context:
                        start_line = max(1, index - context)
                        end_line = min(len(lines), index + context)
                        for ctx_index in range(start_line, end_line + 1):
                            prefix = ":" if ctx_index == index else "-"
                            results.append("%s:%d%s%s" % (relative, ctx_index, prefix, lines[ctx_index - 1][:500]))
                    else:
                        results.append("%s:%d:%s" % (relative, index, line[:500]))
                if count >= limit:
                    break
            if count:
                if output_mode == "files_with_matches":
                    files.append(relative)
                elif output_mode == "count":
                    counts.append("%s:%d" % (relative, count))
                if len(files) + len(results) + len(counts) >= limit * 2:
                    break
        if len(files) + len(results) + len(counts) >= limit * 2:
            break
    if output_mode == "files_with_matches":
        selected = files
    elif output_mode == "count":
        selected = counts
    else:
        selected = results
    selected = selected[offset:offset + limit]
    content = "\n".join(selected)
    return {
        "ok": True,
        "status": "inline",
        "brief": "找到匹配结果。" if content else "没有匹配结果。",
        "path": rel(root),
        "pattern": pattern,
        "output_mode": output_mode,
        "content": content,
        "returned": len(selected),
        "truncated": len(selected) >= limit,
    }


def do_ls(req):
    root = norm(req.get("path") or ROOT)
    if not os.path.isdir(root):
        fail("目录不存在", "agent_not_directory")
    limit = max(1, min(int(req.get("limit") or 500), MAX_RESULTS))
    include_hidden = bool(req.get("include_hidden", True))
    entries = []
    try:
        iterator = os.scandir(root)
    except OSError as exc:
        fail("读取目录失败：%s" % exc, "agent_list_failed")
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
            item = {
                "name": entry.name,
                "path": os.path.relpath(entry.path, root).replace(os.sep, "/"),
                "type": kind,
                "size": info.st_size,
                "mtime": info.st_mtime,
                "mode": oct(stat.S_IMODE(info.st_mode)),
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
    return {
        "ok": True,
        "status": "inline",
        "brief": "列出 %d 项。" % len(entries),
        "path": rel(root),
        "entries": entries,
        "truncated": len(entries) >= limit,
    }


ACTIONS = {
    "read": do_read,
    "read_raw": do_read_raw,
    "delete": do_delete,
    "write": do_write,
    "edit": do_edit,
    "glob": do_glob,
    "grep": do_grep,
    "ls": do_ls,
}


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    handler = ACTIONS.get(action)
    if handler is None:
        fail("未知 agent helper 操作：%s" % action, "agent_invalid_argument")
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            fail("请求必须是 JSON 对象", "agent_invalid_argument")
        result = handler(request)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        fail("agent helper 异常：%s" % exc, "agent_helper_failed")


main()
'''
