"""Native coding-agent host/container backends and custom tools."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from features.coding_agent.backends import (
    CUSTOM_TOOLS_DIR,
    ContainerBackend,
    HostBackend,
)
from features.coding_agent.install import RECIPES
from features.coding_agent.types import AGENT_MODES, mode_supports


def test_mode_capability_matrix_matches_install_recipes():
    all_capabilities = {
        "read",
        "write",
        "edit",
        "bash",
        "glob",
        "grep",
        "ls",
        "apply_patch",
        "todo",
        "spawn",
        "plan",
        "notebook",
        "custom_tools",
    }
    assert set(AGENT_MODES) == {"pi", "dsh", "claude_code"}
    assert mode_supports("pi", "custom_tools")
    assert not mode_supports("pi", "apply_patch")
    assert not mode_supports("pi", "spawn")
    assert mode_supports("dsh", "apply_patch")
    assert mode_supports("dsh", "spawn")
    assert mode_supports("dsh", "custom_tools")
    assert not mode_supports("dsh", "notebook")
    assert mode_supports("claude_code", "notebook")
    assert mode_supports("claude_code", "spawn")
    assert not mode_supports("claude_code", "custom_tools")

    for mode in AGENT_MODES:
        advertised = set(RECIPES[mode].capabilities)
        assert advertised <= all_capabilities
        for capability in all_capabilities:
            assert (capability in advertised) == mode_supports(mode, capability), (
                mode,
                capability,
            )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.txt").write_text("old line\nsecond line\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "code.py").write_text("print('hi')\n", encoding="utf-8")
    return root


@pytest.mark.asyncio
async def test_host_read_write_edit_and_raw(workspace):
    backend = HostBackend(workspace, execution_mode="host")

    written = await backend.write("new/deep.txt", "hello\n")
    assert written["ok"] is True and written["created"] is True
    assert (workspace / "new" / "deep.txt").read_text(encoding="utf-8") == "hello\n"

    edited = await backend.edit(
        "new/deep.txt",
        [{"old_string": "hello", "new_string": "world"}],
    )
    assert edited["ok"] is True and edited["replacements"] == 1
    assert "world" in (workspace / "new" / "deep.txt").read_text(encoding="utf-8")

    read = await backend.read("note.txt", offset=2, limit=1)
    assert read["ok"] is True
    assert read["content"] == "2\tsecond line"
    assert read["next_offset"] is None

    raw = await backend.read_raw("note.txt")
    assert raw["ok"] is True
    assert raw["content"] == "old line\nsecond line\n"

    deleted = await backend.delete("new/deep.txt")
    assert deleted["ok"] is True
    assert not (workspace / "new" / "deep.txt").exists()


@pytest.mark.asyncio
async def test_host_rejects_paths_outside_workspace(workspace, tmp_path):
    backend = HostBackend(workspace, execution_mode="host")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (workspace / "link.txt").symlink_to(outside)

    traversal = await backend.read("../outside.txt")
    assert traversal["ok"] is False
    assert traversal["code"] == "agent_path_forbidden"

    linked = await backend.read("link.txt")
    assert linked["ok"] is False
    assert linked["code"] == "agent_path_forbidden"

    symlink_result = await backend.write("link.txt", "overwrite")
    assert symlink_result["ok"] is False
    assert outside.read_text(encoding="utf-8") == "secret"


@pytest.mark.asyncio
async def test_host_glob_grep_ls_bash(workspace):
    backend = HostBackend(workspace, execution_mode="host")

    globbed = await backend.glob("**/*.py")
    assert globbed["ok"] is True
    assert "sub/code.py" in globbed["matches"]

    grepped = await backend.grep("old", glob="*.txt", output_mode="content")
    assert grepped["ok"] is True
    assert "note.txt:1:" in grepped["content"]

    listed = await backend.ls(".", include_hidden=True)
    names = {item["name"] for item in listed["entries"]}
    assert {"note.txt", "sub"} <= names

    bashed = await backend.bash("printf agent-ok", timeout_seconds=10)
    assert bashed["ok"] is True
    assert bashed["stdout"] == "agent-ok"
    assert bashed["exit_code"] == 0


@pytest.mark.asyncio
async def test_host_custom_tool_roundtrip(workspace):
    backend = HostBackend(workspace, execution_mode="host")
    code = (
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "print(json.dumps({'total': sum(data.get('numbers', []))}))\n"
    )

    created = await backend.write_custom_tool("sum_numbers", code, "求和")
    assert created["ok"] is True
    assert (workspace / CUSTOM_TOOLS_DIR / "sum_numbers.py").is_file()

    listed = await backend.list_custom_tools()
    assert [item["name"] for item in listed["tools"]] == ["sum_numbers"]

    ran = await backend.run_custom_tool("sum_numbers", {"numbers": [1, 2, 3]})
    assert ran["ok"] is True
    assert ran["output_json"] == {"total": 6}
    assert not list((workspace / ".karen-agents" / "tmp").glob("*.py"))

    deleted = await backend.delete_custom_tool("sum_numbers")
    assert deleted["ok"] is True
    emptied = await backend.list_custom_tools()
    assert emptied["ok"] is True
    assert emptied["tools"] == []


@pytest.mark.asyncio
async def test_custom_tool_failure_and_invalid_name(workspace):
    backend = HostBackend(workspace, execution_mode="host")
    invalid = await backend.write_custom_tool("../escape", "print(1)\n", "")
    assert invalid["ok"] is False

    code = "import sys\nsys.stderr.write('boom')\nraise SystemExit(3)\n"
    created = await backend.write_custom_tool("fail_tool", code, "")
    assert created["ok"] is True
    failed = await backend.run_custom_tool("fail_tool", {})
    assert failed["ok"] is False
    assert failed["exit_code"] == 3
    assert "boom" in failed["stderr"]


@pytest.mark.asyncio
async def test_host_apply_patch_modify_create_delete(workspace):
    backend = HostBackend(workspace, execution_mode="host")
    modify = (
        "--- a/note.txt\n"
        "+++ b/note.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-old line\n"
        "+new line\n"
        " second line\n"
        "--- /dev/null\n"
        "+++ b/created.txt\n"
        "@@ -0,0 +1,2 @@\n"
        "+hello\n"
        "+world\n"
    )
    result = await backend.apply_patch(modify)
    assert result["ok"] is True
    assert result["additions"] == 3
    assert result["deletions"] == 1
    assert (workspace / "note.txt").read_text(encoding="utf-8") == (
        "new line\nsecond line\n"
    )
    assert (workspace / "created.txt").read_text(encoding="utf-8") == "hello\nworld\n"

    delete = (
        "--- a/created.txt\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-hello\n"
        "-world\n"
    )
    removed = await backend.apply_patch(delete)
    assert removed["ok"] is True
    assert removed["files"][0]["deleted"] is True
    assert not (workspace / "created.txt").exists()


@pytest.mark.asyncio
async def test_host_apply_patch_rejects_bad_context_and_traversal(workspace, tmp_path):
    backend = HostBackend(workspace, execution_mode="host")
    bad = (
        "--- a/note.txt\n"
        "+++ b/note.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-missing line\n"
        "+replacement\n"
    )
    failed = await backend.apply_patch(bad)
    assert failed["ok"] is False
    assert "上下文不匹配" in failed["error"]
    assert (workspace / "note.txt").read_text(encoding="utf-8").startswith("old line")

    traversal = (
        "--- a/../outside.txt\n"
        "+++ b/../outside.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-a\n"
        "+b\n"
    )
    blocked = await backend.apply_patch(traversal)
    assert blocked["ok"] is False
    assert ".." in blocked["error"]

    dry = (
        "--- a/note.txt\n"
        "+++ b/note.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-old line\n"
        "+dry line\n"
    )
    preview = await backend.apply_patch(dry, dry_run=True)
    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert (workspace / "note.txt").read_text(encoding="utf-8").startswith("old line")


class FakeContainerService:
    """Minimal container filesystem used to exercise ContainerBackend."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: dict[str, str] = {}
        self.commands: list[str] = []

    def _resolve(self, path: str) -> str:
        text = str(path or "").strip()
        if text.startswith("/workspace/"):
            text = text[len("/workspace/") :]
        elif text == "/workspace":
            text = ""
        if ".." in text.split("/"):
            raise AssertionError(f"unexpected path: {path}")
        return text

    async def agent_helper(self, action, payload, *, timeout_seconds=60.0):
        path = self._resolve(payload.get("path") or "")
        if action == "write":
            content = str(payload.get("content") or "")
            self.files[path] = content
            return {"ok": True, "status": "done", "path": path}
        if action == "read_raw":
            if path not in self.files:
                return {
                    "ok": False,
                    "status": "failed",
                    "code": "agent_file_missing",
                    "error": "文件不存在",
                }
            return {
                "ok": True,
                "status": "inline",
                "content": self.files[path],
                "size_bytes": len(self.files[path].encode()),
            }
        if action == "delete":
            if path not in self.files:
                return {
                    "ok": False,
                    "status": "failed",
                    "code": "agent_file_missing",
                    "error": "文件不存在",
                }
            del self.files[path]
            return {"ok": True, "status": "done", "path": path}
        if action == "ls":
            if not path:
                entries = []
                prefixes = set()
                for name in self.files:
                    head = name.split("/", 1)[0]
                    prefixes.add(head)
                for head in sorted(prefixes):
                    entries.append(
                        {
                            "name": head,
                            "type": "dir" if any("/" in n for n in self.files) else "file",
                        }
                    )
                return {"ok": True, "entries": entries}
            entries = []
            prefix = path.rstrip("/") + "/"
            for name in sorted(self.files):
                if not name.startswith(prefix):
                    continue
                rest = name[len(prefix) :]
                if "/" in rest:
                    continue
                entries.append({"name": rest, "type": "file"})
            return {"ok": True, "entries": entries}
        return {"ok": False, "status": "failed", "error": action}

    async def exec_agent(self, command, *, cwd="/workspace", timeout_seconds=120.0, stdin=""):
        self.commands.append(command)
        marker = " -I "
        script = command.split(marker, 1)[1].strip()
        if script.startswith("/workspace/"):
            script = script[len("/workspace/") :]
        code = self.files[script]
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(stdin.encode())
        return {
            "ok": proc.returncode == 0,
            "status": "done" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "timed_out": False,
        }


@pytest.mark.asyncio
async def test_container_custom_tool_roundtrip(tmp_path):
    service = FakeContainerService(tmp_path)
    backend = ContainerBackend(service)
    code = "import json,sys\nprint(sum(json.load(sys.stdin)['numbers']))\n"

    created = await backend.write_custom_tool("sum_numbers", code, "求和")
    assert created["ok"] is True
    assert ".karen-agents/tools/sum_numbers.py" in service.files

    listed = await backend.list_custom_tools()
    assert listed["ok"] is True
    assert [item["name"] for item in listed["tools"]] == ["sum_numbers"]

    ran = await backend.run_custom_tool("sum_numbers", {"numbers": [2, 5]})
    assert ran["ok"] is True
    assert ran["output_json"] == 7
    assert not any(
        name.startswith(".karen-agents/tmp/") for name in service.files
    )

    deleted = await backend.delete_custom_tool("sum_numbers")
    assert deleted["ok"] is True
    assert not any(name.startswith(CUSTOM_TOOLS_DIR) for name in service.files)
