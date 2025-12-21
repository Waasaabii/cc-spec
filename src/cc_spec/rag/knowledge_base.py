"""v0.1.5：KnowledgeBase（ChromaDB + fastembed embeddings + events/snapshot/manifest）。

设计原则：
- 向量库（Chroma）用于高效检索
- events（jsonl）用于过程追溯（追加写）
- snapshot（jsonl）用于“定期 compact”的可审阅快照（覆盖写）
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from cc_spec.embedding.manager import embed_texts, ensure_running
from cc_spec.utils.files import get_cc_spec_dir
from cc_spec.version import KB_SCHEMA_VERSION

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

        # v0.1.6：归属/追踪索引（用于避免频繁查询向量库元数据）
        self._attr_index_loaded = False
        self._attr_index: dict[str, dict[str, Any]] = {}
        self._attr_index_warned = False

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        *,
        attribution: dict[str, Any] | None = None,
        skip_list_fields: bool = False,
    ) -> None:
        if not chunks:
            return

        by_source: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_source.setdefault(c.source_path, []).append(c)

        col = self._get_collection(self.collection_chunks)
        attr = attribution or {}

        # v0.1.6：为每个 source_path 计算要写入的归属/追踪元数据
        meta_by_source: dict[str, dict[str, Any]] = {}
        # 1) 尽量从本地索引读取（避免 N 次向量库 get）
        index = self._load_attr_index()

        # 2) 若索引缺失，批量从向量库拉取一次元数据作为兜底（只查需要的文件）
        missing_sources = [p for p in by_source.keys() if p not in index]
        existing_meta = self._get_existing_attribution_bulk(col, missing_sources) if missing_sources else {}

        # 3) 生成本次写入使用的 meta，并在成功写入后更新索引
        index_updates: dict[str, dict[str, Any]] = {}
        for source_path in by_source.keys():
            extra_meta: dict[str, Any] = {}

            by = str(attr.get("by") or "").strip()
            if not by:
                change_id = str(attr.get("change_id") or "").strip()
                task_id = str(attr.get("task_id") or "").strip()
                if change_id and task_id:
                    by = f"{change_id}/{task_id}"

            # 归属索引（优先本地索引；不存在则用向量库兜底）
            existing = index.get(source_path) or existing_meta.get(source_path) or {}
            existing_created_by = str(existing.get("created_by") or "").strip()
            existing_modified_by = _coerce_str_list(existing.get("modified_by"))
            existing_related_changes = _coerce_str_list(existing.get("related_changes"))
            existing_related_tasks = _coerce_str_list(existing.get("related_tasks"))

            # created_by：首次归属优先，不可覆盖
            created_by = str(attr.get("created_by") or "").strip() or by
            if existing_created_by:
                created_by = existing_created_by
            if created_by:
                extra_meta["created_by"] = created_by

            # modified_by：追加写（列表语义 → JSON 字符串存入 metadata）
            modifier = str(attr.get("modified_by") or "").strip() or by
            modified_list = list(existing_modified_by)
            if not skip_list_fields:
                if modifier and modifier not in modified_list:
                    modified_list.append(modifier)
            if modified_list:
                extra_meta["modified_by"] = _dump_json_list(modified_list)

            # related_changes / related_tasks：列表语义 → JSON 字符串
            related_changes = list(existing_related_changes)
            change_id = str(attr.get("change_id") or "").strip()
            if not skip_list_fields:
                if change_id and change_id not in related_changes:
                    related_changes.append(change_id)
            if related_changes:
                extra_meta["related_changes"] = _dump_json_list(related_changes)

            related_tasks = list(existing_related_tasks)
            task_id = str(attr.get("task_id") or "").strip()
            if not skip_list_fields:
                if task_id and task_id not in related_tasks:
                    related_tasks.append(task_id)
            if related_tasks:
                extra_meta["related_tasks"] = _dump_json_list(related_tasks)

            # 常用追踪字段（最后一次写入为准）
            for key in ("step", "change_id", "change_name", "task_id"):
                val = attr.get(key)
                if val is None:
                    continue
                extra_meta[key] = str(val)
            wave = attr.get("wave")
            if wave is not None:
                try:
                    extra_meta["wave"] = int(wave)
                except Exception:
                    extra_meta["wave"] = str(wave)

            meta_by_source[source_path] = extra_meta
            index_updates[source_path] = {
                "created_by": created_by or None,
                "modified_by": modified_list,
                "related_changes": related_changes,
                "related_tasks": related_tasks,
            }

        # 再 add 新切片
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []

        for c in chunks:
            chunk_id, doc, meta = c.to_chroma()
            if c.source_path in meta_by_source:
                meta.update(meta_by_source[c.source_path])
            ids.append(chunk_id)
            docs.append(doc)
            metas.append(meta)

        # 数据风险修复：先准备 embeddings，成功后再 delete+add
        vectors = embed_texts(self.project_root, docs, model=self.embedding_model)

        for source_path in by_source.keys():
            self._delete_by_source(col, source_path)

        self._collection_add(col, ids=ids, documents=docs, metadatas=metas, embeddings=vectors)

        # 写入成功后更新本地索引（用于后续追加/保留 created_by）
        if index_updates:
            index.update(index_updates)
            self._save_attr_index(index)

        event: dict[str, Any] = {
            "type": "chunks.upsert",
            "ts": _now_iso(),
            "count": len(chunks),
            "sources": sorted(by_source.keys()),
        }
        if attr:
            event["attribution"] = attr
        self.store.append_event(event)

    def delete_chunks_for_file(self, source_path: str, *, attribution: dict[str, Any] | None = None) -> None:
        """删除某个文件对应的所有 chunks。"""
        col = self._get_collection(self.collection_chunks)
        self._delete_by_source(col, source_path)

        # 同步清理本地索引（失败不阻断）
        try:
            index = self._load_attr_index()
            if source_path in index:
                index.pop(source_path, None)
                self._save_attr_index(index)
        except Exception:
            pass

        event: dict[str, Any] = {
            "type": "chunks.delete",
            "ts": _now_iso(),
            "source_path": source_path,
        }
        if attribution:
            event["attribution"] = attribution
        self.store.append_event(event)

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
        include_list = include or ["documents", "metadatas", "distances"]
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
        manifest.setdefault("schema_version", KB_SCHEMA_VERSION)
        manifest["last_compact_at"] = _now_iso()
        manifest.setdefault("embedding", {})
        manifest["embedding"]["provider"] = "fastembed"
        manifest["embedding"]["model"] = self.embedding_model
        self.store.save_manifest(manifest)

    def update_manifest_files(
        self,
        file_hashes: dict[str, str],
        *,
        git_head: str | None = None,
        git_dirty: bool | None = None,
        chunking_meta: dict[str, Any] | None = None,
    ) -> None:
        """更新 manifest 中的文件 hash 映射（用于增量更新）。"""
        manifest = self.store.load_manifest()
        manifest.setdefault("schema_version", KB_SCHEMA_VERSION)
        manifest.setdefault("files", {})
        manifest["files"] = dict(sorted(file_hashes.items(), key=lambda x: x[0]))
        manifest["last_scan_at"] = _now_iso()

        # v0.1.6：记录 git 状态（用于判断“工作区 clean 时是否可跳过更新”）
        if git_head is not None or git_dirty is not None:
            if not isinstance(manifest.get("git"), dict):
                manifest["git"] = {}
            if git_head is not None:
                manifest["git"]["head"] = str(git_head)
            if git_dirty is not None:
                manifest["git"]["dirty"] = bool(git_dirty)
            manifest["git"]["updated_at"] = _now_iso()

        if chunking_meta:
            meta = dict(chunking_meta)
            meta.setdefault("updated_at", _now_iso())
            manifest["chunking"] = meta

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

    def _load_attr_index(self) -> dict[str, dict[str, Any]]:
        if self._attr_index_loaded:
            return self._attr_index

        self._attr_index_loaded = True
        self._attr_index = {}

        path = self.paths.attribution_file
        if not path.exists():
            return self._attr_index

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # 索引损坏：备份并重新开始（避免静默丢失归属）
            backup = self._backup_corrupt_attr_index(path)
            if not self._attr_index_warned:
                msg = f"[cc-spec] warning: failed to parse {path.name}; "
                if backup is not None:
                    msg += f"moved to {backup.name}"
                else:
                    msg += "keeping original file"
                print(msg, file=sys.stderr)
                self._attr_index_warned = True
            return self._attr_index

        files = data.get("files") if isinstance(data, dict) else None
        if isinstance(files, dict):
            raw = files
        elif isinstance(data, dict):
            # 容错：允许直接将 mapping 作为顶层结构
            raw = data
        else:
            raw = {}

        for source_path, entry in raw.items():
            if not isinstance(source_path, str) or not isinstance(entry, dict):
                continue
            self._attr_index[source_path] = {
                "created_by": str(entry.get("created_by") or "").strip() or None,
                "modified_by": _coerce_str_list(entry.get("modified_by")),
                "related_changes": _coerce_str_list(entry.get("related_changes")),
                "related_tasks": _coerce_str_list(entry.get("related_tasks")),
            }
        return self._attr_index

    def _save_attr_index(self, index: dict[str, dict[str, Any]]) -> None:
        self._attr_index = index
        self._attr_index_loaded = True
        payload = {
            "schema_version": KB_SCHEMA_VERSION,
            "updated_at": _now_iso(),
            "files": index,
        }
        path = self.paths.attribution_file
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _backup_corrupt_attr_index(self, path: Path) -> Path | None:
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        backup = path.with_name(f"{path.name}.bad.{ts}.{uuid.uuid4().hex[:8]}")
        try:
            os.replace(path, backup)
            return backup
        except Exception:
            return None

    def _get_existing_attribution_bulk(self, collection: Any, source_paths: list[str]) -> dict[str, dict[str, Any]]:
        """从现有 chunks 中批量读取归属信息（用于索引缺失时的兜底）。"""
        if not source_paths or not hasattr(collection, "get"):
            return {}

        # chromadb where 支持 $in；若失败则回退到逐个查询（但仍只对缺失项）
        metas: list[dict[str, Any]] = []
        try:
            res = collection.get(
                where={"source_path": {"$in": source_paths}},
                include=["metadatas"],
            )  # type: ignore[attr-defined]
            raw_metas = res.get("metadatas") if isinstance(res, dict) else None
            if isinstance(raw_metas, list):
                metas = [m for m in raw_metas if isinstance(m, dict)]
        except Exception:
            metas = []
            for sp in source_paths:
                try:
                    res = collection.get(where={"source_path": sp}, include=["metadatas"])  # type: ignore[attr-defined]
                except Exception:
                    continue
                raw_metas = res.get("metadatas") if isinstance(res, dict) else None
                if isinstance(raw_metas, list):
                    metas.extend([m for m in raw_metas if isinstance(m, dict)])

        by_source: dict[str, dict[str, Any]] = {}
        for meta in metas:
            sp = meta.get("source_path")
            if not sp:
                continue
            source = str(sp)
            if source in by_source:
                continue
            by_source[source] = {
                "created_by": str(meta.get("created_by") or "").strip() or None,
                "modified_by": _coerce_str_list(meta.get("modified_by")),
                "related_changes": _coerce_str_list(meta.get("related_changes")),
                "related_tasks": _coerce_str_list(meta.get("related_tasks")),
            }
        return by_source


def _coerce_str_list(value: Any) -> list[str]:
    """将 value 归一为 list[str]。

    支持：
    - list[Any] → list[str]
    - JSON 字符串（数组）→ list[str]
    - 普通字符串 → [string]
    - None/空字符串 → []
    """
    if value is None:
        return []

    if isinstance(value, list):
        items: list[str] = []
        for x in value:
            s = str(x).strip()
            if s:
                items.append(s)
        return items

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # JSON array
        if s.startswith("[") and s.endswith("]"):
            try:
                obj = json.loads(s)
            except Exception:
                obj = None
            if isinstance(obj, list):
                items: list[str] = []
                for x in obj:
                    sx = str(x).strip()
                    if sx:
                        items.append(sx)
                return items
        return [s]

    s = str(value).strip()
    return [s] if s else []


def _dump_json_list(items: list[str]) -> str:
    cleaned = [str(x).strip() for x in items if str(x).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def new_record_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
