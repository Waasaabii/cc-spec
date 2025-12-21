"""Smart chunking strategy (AST / line / LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ast_chunker import ASTChunker
from .ast_utils import finalize_chunk, infer_chunk_type, simple_text_chunks
from .chunker import ChunkingOptions, CodexChunker
from .models import ChunkResult, ChunkStatus, ScannedFile


@dataclass
class SmartChunkingOptions:
    strategy: str = "ast-only"  # ast-only | smart | codex-only
    reference_mode: str = "index"  # index | full
    ast_max_chunk_chars: int = 2000
    ast_chunk_overlap_nodes: int = 1
    ast_supported_extensions: list[str] | None = None
    line_lines_per_chunk: int = 100
    line_overlap_lines: int = 10
    llm_enabled: bool = True
    llm_priority_files: list[str] | None = None
    llm_max_content_chars: int = 120_000


class SmartChunker:
    def __init__(
        self,
        codex: CodexChunker,
        project_root: Path,
        *,
        options: SmartChunkingOptions | None = None,
    ) -> None:
        self.project_root = project_root
        self.options = options or SmartChunkingOptions()
        self.codex_chunker = codex
        self.ast_chunker = ASTChunker(
            max_chunk_chars=self.options.ast_max_chunk_chars,
            chunk_overlap_nodes=self.options.ast_chunk_overlap_nodes,
            supported_extensions=self.options.ast_supported_extensions or [],
        )

    def chunk_file(self, scanned: ScannedFile) -> ChunkResult:
        rel_path_str = scanned.rel_path.as_posix()

        if not scanned.is_text or scanned.sha256 is None:
            return ChunkResult(chunks=[], status=ChunkStatus.SUCCESS, source_path=rel_path_str)

        # reference 模式：默认仅做索引级入库（保持与 CodexChunker 一致）
        if scanned.is_reference and self.options.reference_mode == "index":
            options = ChunkingOptions(
                reference_mode="index",
                max_content_chars=self.options.llm_max_content_chars,
            )
            return self._with_strategy(self.codex_chunker.chunk_file(scanned, options=options), "llm")

        strategy = self._select_strategy(scanned)

        if strategy == "llm":
            options = ChunkingOptions(
                reference_mode=self.options.reference_mode,
                max_content_chars=self.options.llm_max_content_chars,
            )
            return self._with_strategy(self.codex_chunker.chunk_file(scanned, options=options), "llm")

        if strategy == "ast":
            res = self.ast_chunker.chunk_file(scanned)
            if res.status != ChunkStatus.SUCCESS:
                return self._with_strategy(res, "line")
            return self._with_strategy(res, "ast")

        # line strategy
        content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")
        dicts = simple_text_chunks(
            content,
            source_path=rel_path_str,
            source_sha256=scanned.sha256,
            lines_per_chunk=self.options.line_lines_per_chunk,
            overlap_lines=self.options.line_overlap_lines,
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
        return self._with_strategy(
            ChunkResult(chunks=chunks, status=ChunkStatus.SUCCESS, source_path=rel_path_str),
            "line",
        )

    def chunk_files(self, scanned_files: list[ScannedFile]) -> list[ChunkResult]:
        return [self.chunk_file(sf) for sf in scanned_files]

    def _select_strategy(self, scanned: ScannedFile) -> str:
        strategy = (self.options.strategy or "ast-only").lower().strip()

        if strategy == "codex-only":
            return "llm"

        # smart or ast-only
        name = scanned.rel_path.name.lower()
        ext = scanned.rel_path.suffix.lower()

        if strategy == "smart" and self.options.llm_enabled:
            priority = set((self.options.llm_priority_files or []))
            if name in priority:
                return "llm"

        ast_supported = set(self.options.ast_supported_extensions or [])
        if ast_supported and ext in ast_supported:
            return "ast"

        return "line"

    def _with_strategy(self, result: ChunkResult, strategy: str) -> ChunkResult:
        return ChunkResult(
            chunks=result.chunks,
            status=result.status,
            source_path=result.source_path,
            error_message=result.error_message,
            codex_exit_code=result.codex_exit_code,
            strategy=strategy,
        )
