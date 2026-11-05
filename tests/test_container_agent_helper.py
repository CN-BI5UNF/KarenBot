"""Execute the embedded container agent helper locally against a temp root."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from features.container.agent_helper import AGENT_HELPER_SOURCE


@pytest.fixture
def helper(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    source = AGENT_HELPER_SOURCE.replace(
        'ROOT = "/workspace"', f"ROOT = {json.dumps(str(root))}"
    )
    script = tmp_path / "helper.py"
    script.write_text(source, encoding="utf-8")

    def run(action: str, payload: dict) -> dict:
        proc = subprocess.run(
            [sys.executable, "-I", str(script), action],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    return root, run


def test_helper_write_read_raw_and_delete(helper):
    root, run = helper
    written = run(
        "write",
        {"path": "nested/note.txt", "content": "hello\nworld\n"},
    )
    assert written["ok"] is True
    assert (root / "nested" / "note.txt").read_text(encoding="utf-8") == "hello\nworld\n"

    raw = run("read_raw", {"path": "nested/note.txt"})
    assert raw["ok"] is True
    assert raw["content"] == "hello\nworld\n"

    numbered = run("read", {"path": "nested/note.txt", "offset": 2, "limit": 1})
    assert numbered["ok"] is True
    assert numbered["content"] == "2\tworld"

    deleted = run("delete", {"path": "nested/note.txt"})
    assert deleted["ok"] is True
    assert not (root / "nested" / "note.txt").exists()


def test_helper_rejects_traversal_and_symlink_escape(helper, tmp_path):
    root, run = helper
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)

    traversal = run("read_raw", {"path": "../outside.txt"})
    assert traversal["ok"] is False
    assert traversal["code"] == "agent_path_forbidden"

    linked = run("read_raw", {"path": "link.txt"})
    assert linked["ok"] is False
    assert linked["code"] == "agent_path_forbidden"

    escaped = run("write", {"path": "link.txt", "content": "overwrite"})
    assert escaped["ok"] is False
    assert outside.read_text(encoding="utf-8") == "secret"


def test_helper_glob_grep_and_ls(helper):
    root, run = helper
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.py").write_text("print('beta')\n", encoding="utf-8")

    globbed = run("glob", {"pattern": "**/*.py", "path": "."})
    assert globbed["ok"] is True
    assert "sub/b.py" in globbed["matches"]

    grepped = run("grep", {"pattern": "beta", "path": ".", "glob": "*.py"})
    assert grepped["ok"] is True
    assert "sub/b.py" in grepped["content"]

    listed = run("ls", {"path": ".", "include_hidden": True})
    names = {item["name"] for item in listed["entries"]}
    assert {"a.txt", "sub"} <= names
