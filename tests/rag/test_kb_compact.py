"""Unit tests for KB events/snapshot/manifest compaction."""

from __future__ import annotations

import json

from cc_spec.rag.knowledge_base import KnowledgeBase


def test_kb_compact_writes_snapshot_and_clears_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cc_spec.rag.knowledge_base.ensure_running", lambda *_a, **_k: None)

    kb = KnowledgeBase(tmp_path, embedding_model="test-model")
    kb.store.append_event({"type": "record.add", "ts": "2025-01-01T00:00:00"})
    kb.store.append_event({"type": "chunks.upsert", "ts": "2025-01-01T00:00:01"})

    assert len(kb.store.read_events()) == 2

    kb.compact()

    assert kb.store.read_events() == []

    snapshot_lines = kb.paths.snapshot_file.read_text(encoding="utf-8").splitlines()
    assert len(snapshot_lines) == 3

    meta = json.loads(snapshot_lines[0])
    assert meta["type"] == "snapshot.meta"
    assert meta["events_count"] == 2
    assert meta["embedding_model"] == "test-model"

    manifest = kb.store.load_manifest()
    assert manifest["embedding"]["provider"] == "fastembed"
    assert manifest["embedding"]["model"] == "test-model"
    assert manifest["schema_version"] == "0.1.5-draft"
    assert isinstance(manifest.get("last_compact_at"), str)
    assert manifest.get("last_compact_at")


def test_kb_update_manifest_files_records_hashes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cc_spec.rag.knowledge_base.ensure_running", lambda *_a, **_k: None)

    kb = KnowledgeBase(tmp_path, embedding_model="test-model")
    kb.update_manifest_files({"b.txt": "222", "a.txt": "111"})

    manifest = kb.store.load_manifest()
    assert manifest["files"] == {"a.txt": "111", "b.txt": "222"}
    assert manifest["embedding"]["provider"] == "fastembed"
    assert manifest["embedding"]["model"] == "test-model"
    assert manifest["schema_version"] == "0.1.5-draft"
    assert isinstance(manifest.get("last_scan_at"), str)
    assert manifest.get("last_scan_at")

