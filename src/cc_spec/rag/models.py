"""v0.1.5 RAG 知识库的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChunkType(str, Enum):
    """向量库中切片的类型。"""

    CODE = "code"
    DOC = "doc"
    SPEC = "spec"
    CONFIG = "config"
    REFERENCE = "reference"


class ChunkStatus(str, Enum):
    """切片操作的状态。"""

    SUCCESS = "success"              # Codex 成功，JSON 解析成功
    FALLBACK_EXEC = "fallback_exec"  # Codex 执行失败
    FALLBACK_PARSE = "fallback_parse"  # JSON 解析失败
    FALLBACK_EMPTY = "fallback_empty"  # 解析成功但结果为空


class WorkflowStep(str, Enum):
    """工作流步骤，用于 records 可追溯。"""

    INIT = "init"
    SPECIFY = "specify"
    CLARIFY = "clarify"
    PLAN = "plan"
    APPLY = "apply"
    CHECKLIST = "checklist"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class ScannedFile:
    """一次扫描得到的文件信息（不含内容）。"""

    abs_path: Path
    rel_path: Path
    size_bytes: int
    sha256: str | None
    is_text: bool
    is_reference: bool
    reason: str | None = None


@dataclass(frozen=True)
class Chunk:
    """向量库切片。"""

    chunk_id: str
    text: str
    summary: str
    chunk_type: ChunkType
    source_path: str
    source_sha256: str
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_chroma(self) -> tuple[str, str, dict[str, Any]]:
        """转换为 Chroma 所需的 (id, document, metadata)。"""
        metadata: dict[str, Any] = {
            "type": self.chunk_type.value,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
        }
        if self.start_line is not None:
            metadata["start_line"] = self.start_line
        if self.end_line is not None:
            metadata["end_line"] = self.end_line
        if self.language:
            metadata["language"] = self.language
        if self.summary:
            metadata["summary"] = self.summary
        if self.extra:
            metadata.update(self.extra)
        return (self.chunk_id, self.text, metadata)


@dataclass
class ChunkResult:
    """切片操作的结果（包含状态和错误信息）。"""

    chunks: list[Chunk]
    status: ChunkStatus
    source_path: str
    error_message: str | None = None
    codex_exit_code: int | None = None
    strategy: str | None = None


@dataclass(frozen=True)
class WorkflowRecord:
    """工作流记录（强结构化，可追溯）。"""

    record_id: str
    step: WorkflowStep
    change_name: str
    created_at: str
    task_id: str | None = None
    session_id: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "step": self.step.value,
            "change_name": self.change_name,
            "created_at": self.created_at,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "changed_files": self.changed_files,
            "notes": self.notes,
        }
