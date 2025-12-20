"""Unit tests for KB attribution metadata (v0.1.6)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cc_spec.rag.knowledge_base import KnowledgeBase
from cc_spec.rag.models import Chunk, ChunkType


@dataclass
class _FakeCollection:
    """Minimal fake Chroma collection for unit tests."""

    metadatas_by_source: dict[str, dict[str, Any]]
    get_calls: list[dict[str, Any]]
    delete_calls: list[dict[str, Any]]
    upsert_calls: list[dict[str, Any]]

    def __init__(self) -> None:
        self.metadatas_by_source = {}
        self.get_calls = []
        self.delete_calls = []
        self.upsert_calls = []

    def get(self, *, where: dict[str, Any], include: list[str]) -> dict[str, Any]:
        _ = include
        self.get_calls.append(where)

        source_filter = where.get("source_path")
        sources: list[str] = []
        if isinstance(source_filter, dict) and "$in" in source_filter:
            sources = [str(x) for x in source_filter.get("$in") or []]
        elif source_filter is not None:
            sources = [str(source_filter)]

        metas: list[dict[str, Any]] = []
        ids: list[str] = []
        for sp in sources:
            meta = self.metadatas_by_source.get(sp)
            if meta:
                metas.append(meta)
                ids.append(f"id:{sp}")

        return {"ids": ids, "metadatas": metas}

    def delete(self, *, where: dict[str, Any]) -> None:
        self.delete_calls.append(where)
        sp = where.get("source_path")
        if isinstance(sp, str):
            self.metadatas_by_source.pop(sp, None)

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        self.upsert_calls.append(
            {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "embeddings": embeddings,
            }
        )
        # Store a representative metadata per source_path for subsequent get()
        for meta in metadatas:
            sp = meta.get("source_path")
            if isinstance(sp, str) and sp:
                self.metadatas_by_source[sp] = dict(meta)


def _chunk(*, source_path: str) -> Chunk:
    return Chunk(
        chunk_id=f"test:{source_path}",
        text="hello",
        summary="sum",
        chunk_type=ChunkType.CODE,
        source_path=source_path,
        source_sha256="deadbeef",
        start_line=1,
        end_line=2,
        language="py",
    )


def test_upsert_chunks_writes_json_list_fields_and_preserves_created_by(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cc_spec.rag.knowledge_base.ensure_running", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "cc_spec.rag.knowledge_base.embed_texts",
        lambda _root, texts, *, model: [[0.0, 0.0, 0.0] for _ in texts],
    )

    fake = _FakeCollection()
    monkeypatch.setattr(KnowledgeBase, "_get_collection", lambda _self, _name: fake)

    kb = KnowledgeBase(tmp_path, embedding_model="test-model")

    source = "src/a.py"
    kb.upsert_chunks(
        [_chunk(source_path=source)],
        attribution={"by": "C-001/W1-T1", "change_id": "C-001", "task_id": "W1-T1"},
    )

    assert fake.upsert_calls, "expected a collection upsert"
    meta0 = fake.upsert_calls[-1]["metadatas"][0]
    assert meta0["created_by"] == "C-001/W1-T1"
    assert json.loads(meta0["modified_by"]) == ["C-001/W1-T1"]
    assert json.loads(meta0["related_changes"]) == ["C-001"]
    assert json.loads(meta0["related_tasks"]) == ["W1-T1"]

    # second write should preserve created_by and append modified_by / related lists
    kb.upsert_chunks(
        [_chunk(source_path=source)],
        attribution={"by": "C-002/W2-T3", "change_id": "C-002", "task_id": "W2-T3"},
    )
    meta1 = fake.upsert_calls[-1]["metadatas"][0]
    assert meta1["created_by"] == "C-001/W1-T1"
    assert json.loads(meta1["modified_by"]) == ["C-001/W1-T1", "C-002/W2-T3"]
    assert json.loads(meta1["related_changes"]) == ["C-001", "C-002"]
    assert json.loads(meta1["related_tasks"]) == ["W1-T1", "W2-T3"]

    # attribution index file should persist list semantics (not JSON strings)
    attr_path = tmp_path / ".cc-spec" / "kb.attribution.json"
    data = json.loads(attr_path.read_text(encoding="utf-8"))
    files = data["files"]
    assert files[source]["created_by"] == "C-001/W1-T1"
    assert files[source]["modified_by"] == ["C-001/W1-T1", "C-002/W2-T3"]
    assert files[source]["related_changes"] == ["C-001", "C-002"]
    assert files[source]["related_tasks"] == ["W1-T1", "W2-T3"]
