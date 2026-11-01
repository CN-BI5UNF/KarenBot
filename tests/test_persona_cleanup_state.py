"""Cleanup marker and usage-import suppression."""

from __future__ import annotations

import json
import sqlite3

from core.knowledge import KnowledgeStore
from core.persona_cleanup_state import (
    cleanup_marker_path,
    legacy_usage_import_suppressed,
    read_cleanup_marker,
    write_cleanup_marker,
)
from memory.karen_importers import import_legacy_memory_files


def test_marker_is_hashed_and_readable(tmp_paths):
    path = write_cleanup_marker(tmp_paths, "小堡")
    assert path == cleanup_marker_path(tmp_paths, "小堡")
    assert path.name.endswith(".json")
    assert "小堡" not in path.name
    data = read_cleanup_marker(tmp_paths, "小堡")
    assert data["persona"] == "小堡"
    assert data["suppress_legacy_usage_import"] is True
    assert legacy_usage_import_suppressed(tmp_paths, "小堡") is True
    assert legacy_usage_import_suppressed(tmp_paths, "deepseek") is False


def test_usage_import_can_be_disabled_without_touching_other_domains(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    usage = source / "model_usage.jsonl"
    usage.write_text(
        json.dumps(
            {
                "ts": 1.0,
                "provider": "p",
                "model": "m",
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "total_tokens": 5,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "persona.db"
    result = import_legacy_memory_files(
        db_path,
        source,
        "小堡",
        usage_source_path=usage,
        import_usage=False,
    )
    assert result.usage.imported == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0] == 0


def test_private_knowledge_delete_keeps_shared_and_other_personas(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.json")
    private = store.add_manual(
        persona_id="小堡", kind="note", title="私有", content="x", shared=False
    )
    shared = store.add_manual(
        persona_id="小堡", kind="note", title="共享", content="y", shared=True
    )
    other = store.add_manual(
        persona_id="deepseek", kind="note", title="别人", content="z", shared=False
    )
    assert store.delete_private_persona_entries("小堡") == 1
    ids = {item["id"] for item in KnowledgeStore(tmp_path / "knowledge.json")._entries}
    assert private["id"] not in ids
    assert shared["id"] in ids
    assert other["id"] in ids


def test_private_knowledge_delete_is_noop_on_unwritable_store(tmp_path):
    path = tmp_path / "knowledge.json"
    path.write_text("{bad", encoding="utf-8")
    store = KnowledgeStore(path)
    assert store.writable is False
    # A corrupt store has no trusted private entries to delete.
    assert store.delete_private_persona_entries("小堡") == 0
