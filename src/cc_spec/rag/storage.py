"""v0.1.5：KB 的文件存储（events/snapshot/manifest）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class KBPaths:
    """KB 相关路径（均位于 .cc-spec/ 下）。"""

    cc_spec_root: Path

    @property
    def vectordb_dir(self) -> Path:
        return self.cc_spec_root / "vectordb"

    @property
    def events_file(self) -> Path:
        return self.cc_spec_root / "kb.events.jsonl"

    @property
    def snapshot_file(self) -> Path:
        return self.cc_spec_root / "kb.snapshot.jsonl"

    @property
    def manifest_file(self) -> Path:
        return self.cc_spec_root / "kb.manifest.json"


class KBFileStore:
    """KB 的可提交文件：events（追加）/snapshot（compact 输出）/manifest（可追溯配置）。"""

    def __init__(self, paths: KBPaths) -> None:
        self.paths = paths
        self.paths.cc_spec_root.mkdir(parents=True, exist_ok=True)
        self.paths.vectordb_dir.mkdir(parents=True, exist_ok=True)
        self.paths.events_file.touch(exist_ok=True)
        self.paths.snapshot_file.touch(exist_ok=True)

    def append_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        with self.paths.events_file.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    def read_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.paths.events_file.exists():
            return events
        for raw in self.paths.events_file.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if isinstance(obj, dict):
                events.append(obj)
        return events

    def clear_events(self) -> None:
        self.paths.events_file.write_text("", encoding="utf-8")

    def write_snapshot(self, lines: Iterable[dict[str, Any]]) -> None:
        with self.paths.snapshot_file.open("w", encoding="utf-8") as f:
            for obj in lines:
                f.write(json.dumps(obj, ensure_ascii=False))
                f.write("\n")

    def load_manifest(self) -> dict[str, Any]:
        if not self.paths.manifest_file.exists():
            return {}
        try:
            data = json.loads(self.paths.manifest_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self.paths.manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

