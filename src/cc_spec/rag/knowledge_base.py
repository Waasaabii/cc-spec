"""v0.1.5：KnowledgeBase（ChromaDB + fastembed embeddings + events/snapshot/manifest）。

设计原则：
- 向量库（Chroma）用于高效检索
- events（jsonl）用于过程追溯（追加写）
- snapshot（jsonl）用于“定期 compact”的可审阅快照（覆盖写）
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from cc_spec.embedding.manager import embed_texts, ensure_running
from cc_spec.utils.files import get_cc_spec_dir

from .models import Chunk, WorkflowRecord
from .storage import KBFileStore, KBPaths


class KnowledgeBase:
    """项目级知识库。"""

    def __init__(
        self,
        project_root: Path,
        *,
        embedding_model: str = "intfloat/multilingual-e5-small",
        collection_chunks: str = "chunks",
        collection_records: str = "records",
    ) -> None:
        self.project_root = project_root
        self.embedding_model = embedding_model
        self.cc_spec_root = get_cc_spec_dir(project_root)
        self.paths = KBPaths(cc_spec_root=self.cc_spec_root)
        self.store = KBFileStore(self.paths)
        self.collection_chunks = collection_chunks
        self.collection_records = collection_records

        # 按需拉起 embedding 服务（确保后续 query/add 可用）
        ensure_running(project_root, model=self.embedding_model)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return

        by_source: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_source.setdefault(c.source_path, []).append(c)

        col = self._get_collection(self.collection_chunks)

        # 先按文件删除旧切片（保证增量更新可追溯）
        for source_path in by_source.keys():
            self._delete_by_source(col, source_path)

        # 再 add 新切片
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []

        for c in chunks:
            chunk_id, doc, meta = c.to_chroma()
            ids.append(chunk_id)
            docs.append(doc)
            metas.append(meta)

        vectors = embed_texts(self.project_root, docs, model=self.embedding_model)

        self._collection_add(col, ids=ids, documents=docs, metadatas=metas, embeddings=vectors)

        self.store.append_event(
            {
                "type": "chunks.upsert",
                "ts": _now_iso(),
                "count": len(chunks),
                "sources": sorted(by_source.keys()),
            }
        )

    def delete_chunks_for_file(self, source_path: str) -> None:
        """删除某个文件对应的所有 chunks。"""
        col = self._get_collection(self.collection_chunks)
        self._delete_by_source(col, source_path)
        self.store.append_event(
            {
                "type": "chunks.delete",
                "ts": _now_iso(),
                "source_path": source_path,
            }
        )

    def add_record(self, record: WorkflowRecord) -> None:
        col = self._get_collection(self.collection_records)

        doc = json.dumps(record.to_json(), ensure_ascii=False)
        meta: dict[str, Any] = {
            "step": record.step.value,
            "change_name": record.change_name,
            "created_at": record.created_at,
        }
        if record.task_id:
            meta["task_id"] = record.task_id
        if record.session_id:
            meta["session_id"] = record.session_id

        vectors = embed_texts(self.project_root, [doc], model=self.embedding_model)
        self._collection_add(
            col,
            ids=[record.record_id],
            documents=[doc],
            metadatas=[meta],
            embeddings=vectors,
        )

        self.store.append_event(
            {
                "type": "record.add",
                "ts": _now_iso(),
                "record_id": record.record_id,
                "step": record.step.value,
                "change_name": record.change_name,
                "task_id": record.task_id,
                "session_id": record.session_id,
            }
        )

    def query(
        self,
        text: str,
        *,
        n: int = 5,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
        collection: str = "chunks",
    ) -> dict[str, Any]:
        col = self._get_collection(collection)
        vectors = embed_texts(self.project_root, [text], model=self.embedding_model)
        include_list = include or ["documents", "metadatas", "distances", "ids"]
        return col.query(  # type: ignore[no-any-return]
            query_embeddings=vectors,
            n_results=n,
            where=where,
            include=include_list,
        )

    def compact(self) -> None:
        """将 events 合并到 snapshot，并写入 manifest。"""
        events = self.store.read_events()

        # snapshot 是可审阅快照：写入 meta + 最近 events（不强制包含全部 chunks 内容）
        snapshot_lines: list[dict[str, Any]] = [
            {
                "type": "snapshot.meta",
                "ts": _now_iso(),
                "embedding_model": self.embedding_model,
                "events_count": len(events),
            }
        ]
        snapshot_lines.extend(events)

        self.store.write_snapshot(snapshot_lines)
        self.store.clear_events()

        manifest = self.store.load_manifest()
        manifest.setdefault("schema_version", "0.1.5-draft")
        manifest["last_compact_at"] = _now_iso()
        manifest.setdefault("embedding", {})
        manifest["embedding"]["provider"] = "fastembed"
        manifest["embedding"]["model"] = self.embedding_model
        self.store.save_manifest(manifest)

    def update_manifest_files(self, file_hashes: dict[str, str]) -> None:
        """更新 manifest 中的文件 hash 映射（用于增量更新）。"""
        manifest = self.store.load_manifest()
        manifest.setdefault("schema_version", "0.1.5-draft")
        manifest.setdefault("files", {})
        manifest["files"] = dict(sorted(file_hashes.items(), key=lambda x: x[0]))
        manifest["last_scan_at"] = _now_iso()
        manifest.setdefault("embedding", {})
        manifest["embedding"]["provider"] = "fastembed"
        manifest["embedding"]["model"] = self.embedding_model
        self.store.save_manifest(manifest)

    # ---------------------------------------------------------------------
    # Internal helpers (Chroma)
    # ---------------------------------------------------------------------

    def _get_collection(self, name: str) -> Any:
        try:
            import chromadb  # type: ignore[import-not-found]
        except Exception as e:  # pragma: no cover
            raise RuntimeError("未安装 chromadb。请先安装依赖后重试。") from e

        client = chromadb.PersistentClient(path=str(self.paths.vectordb_dir))
        return client.get_or_create_collection(name)

    def _collection_add(
        self,
        collection: Any,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        # chromadb 新版本支持 upsert；若不存在则用 delete+add
        if hasattr(collection, "upsert"):
            collection.upsert(  # type: ignore[attr-defined]
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            return
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def _delete_by_source(self, collection: Any, source_path: str) -> None:
        # where 删除需要 chromadb 支持；若不支持则跳过（会导致重复）
        if hasattr(collection, "delete"):
            try:
                collection.delete(where={"source_path": source_path})
            except Exception:
                return


def new_record_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
