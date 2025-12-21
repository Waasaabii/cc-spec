"""AST-based chunker using tree-sitter-language-pack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_utils import finalize_chunk, infer_chunk_type, simple_text_chunks
from .models import ChunkResult, ChunkStatus, ScannedFile


@dataclass
class ASTChunkingOptions:
    max_chunk_chars: int = 2000
    chunk_overlap_nodes: int = 1
    supported_extensions: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.supported_extensions is None:
            self.supported_extensions = []


class ASTChunker:
    """Chunk files by AST node boundaries (best-effort)."""

    def __init__(
        self,
        *,
        max_chunk_chars: int = 2000,
        chunk_overlap_nodes: int = 1,
        supported_extensions: list[str] | None = None,
    ) -> None:
        self.options = ASTChunkingOptions(
            max_chunk_chars=max_chunk_chars,
            chunk_overlap_nodes=chunk_overlap_nodes,
            supported_extensions=supported_extensions or [],
        )

    def chunk_file(self, scanned: ScannedFile) -> ChunkResult:
        rel_path_str = scanned.rel_path.as_posix()

        if not scanned.is_text or scanned.sha256 is None:
            return ChunkResult(chunks=[], status=ChunkStatus.SUCCESS, source_path=rel_path_str)

        ext = scanned.rel_path.suffix.lower()
        if self.options.supported_extensions and ext not in self.options.supported_extensions:
            content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")
            dicts = simple_text_chunks(
                content,
                source_path=rel_path_str,
                source_sha256=scanned.sha256,
            )
            chunks = [
                finalize_chunk(
                    d,
                    chunk_type=infer_chunk_type(scanned.rel_path),
                    source_path=rel_path_str,
                    source_sha256=scanned.sha256,
                )
                for d in dicts
            ]
            return ChunkResult(chunks=chunks, status=ChunkStatus.FALLBACK_EMPTY, source_path=rel_path_str)

        content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return ChunkResult(chunks=[], status=ChunkStatus.FALLBACK_EMPTY, source_path=rel_path_str)

        def _line_fallback(message: str, status: ChunkStatus) -> ChunkResult:
            dicts = simple_text_chunks(
                content,
                source_path=rel_path_str,
                source_sha256=scanned.sha256,
            )
            chunks = [
                finalize_chunk(
                    d,
                    chunk_type=infer_chunk_type(scanned.rel_path),
                    source_path=rel_path_str,
                    source_sha256=scanned.sha256,
                )
                for d in dicts
            ]
            return ChunkResult(
                chunks=chunks,
                status=status,
                source_path=rel_path_str,
                error_message=message,
            )

        try:
            from tree_sitter_language_pack import get_parser  # type: ignore[import-not-found]
        except Exception as e:
            return _line_fallback(f"tree-sitter-language-pack unavailable: {e}", ChunkStatus.FALLBACK_EXEC)

        lang = _ext_to_language(ext)
        if not lang:
            return ChunkResult(chunks=[], status=ChunkStatus.FALLBACK_EMPTY, source_path=rel_path_str)

        try:
            parser = get_parser(lang)
        except Exception as e:
            return _line_fallback(f"parser init failed: {e}", ChunkStatus.FALLBACK_EXEC)

        try:
            tree = parser.parse(content.encode("utf-8"))
        except Exception as e:
            return _line_fallback(f"AST parse failed: {e}", ChunkStatus.FALLBACK_EXEC)

        nodes = [n for n in tree.root_node.children if n.is_named]
        if not nodes:
            # fallback to line-based chunking
            dicts = simple_text_chunks(
                content,
                source_path=rel_path_str,
                source_sha256=scanned.sha256,
            )
            chunks = [
                finalize_chunk(d, chunk_type=infer_chunk_type(scanned.rel_path), source_path=rel_path_str, source_sha256=scanned.sha256)
                for d in dicts
            ]
            return ChunkResult(chunks=chunks, status=ChunkStatus.FALLBACK_EMPTY, source_path=rel_path_str)

        chunks: list[dict[str, Any]] = []
        current_nodes: list[Any] = []
        current_len = 0

        def _node_text(node: Any) -> str:
            return content[node.start_byte : node.end_byte]

        def _non_ws_len(text: str) -> int:
            return sum(1 for c in text if not c.isspace())

        def _emit(nodes_group: list[Any], idx: int) -> None:
            if not nodes_group:
                return
            start_node = nodes_group[0]
            end_node = nodes_group[-1]
            chunk_text = "".join(_node_text(n) for n in nodes_group)
            chunks.append(
                {
                    "id": f"ast_{idx}",
                    "type": "ast",
                    "summary": f"AST chunk for {rel_path_str}",
                    "content": chunk_text[:4000],
                    "start_line": start_node.start_point[0] + 1,
                    "end_line": end_node.end_point[0] + 1,
                    "_idx": idx,
                    "_source_sha256": scanned.sha256,
                    "language": lang,
                }
            )

        idx = 0
        for node in nodes:
            text = _node_text(node)
            if not text.strip():
                continue
            node_len = _non_ws_len(text)
            if current_nodes and (current_len + node_len) > self.options.max_chunk_chars:
                _emit(current_nodes, idx)
                idx += 1
                # overlap last N nodes
                overlap = self.options.chunk_overlap_nodes
                current_nodes = current_nodes[-overlap:] if overlap > 0 else []
                current_len = sum(_non_ws_len(_node_text(n)) for n in current_nodes)
            current_nodes.append(node)
            current_len += node_len

        if current_nodes:
            _emit(current_nodes, idx)

        if not chunks:
            return ChunkResult(chunks=[], status=ChunkStatus.FALLBACK_EMPTY, source_path=rel_path_str)

        chunk_type = infer_chunk_type(scanned.rel_path)
        finalized = [
            finalize_chunk(
                c,
                chunk_type=chunk_type,
                source_path=rel_path_str,
                source_sha256=scanned.sha256,
                language=lang,
            )
            for c in chunks
        ]
        return ChunkResult(chunks=finalized, status=ChunkStatus.SUCCESS, source_path=rel_path_str)


def _ext_to_language(ext: str) -> str | None:
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".cs": "c_sharp",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".scala": "scala",
    }.get(ext)
