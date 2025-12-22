"""Session state persistence for Codex runs."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_UNSET = object()


class SessionStateManager:
    """Persist and update Codex session states in a JSON file."""

    def __init__(self, runtime_dir: Path) -> None:
        """Initialize manager and set sessions file path."""
        self._runtime_dir = runtime_dir
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_path = self._runtime_dir / "sessions.json"
        self._lock_path = self._runtime_dir / "sessions.lock"

    def register_session(self, session_id: str, task_summary: str, pid: int | None) -> None:
        """Register a new session with state=running."""
        now = _now_iso()
        with self._file_lock():
            data = self._load_unlocked()
            sessions = data.setdefault("sessions", {})
            record = sessions.get(session_id)
            if not isinstance(record, dict):
                record = {}
            created_at = str(record.get("created_at") or now)
            sessions[session_id] = {
                "session_id": session_id,
                "state": "running",
                "task_summary": task_summary,
                "message": None,
                "exit_code": None,
                "elapsed_s": None,
                "pid": int(pid) if pid is not None else None,
                "created_at": created_at,
                "updated_at": now,
            }
            self._save_unlocked(data)

    def update_session(
        self,
        session_id: str,
        state: str | None,
        message: str | None,
        exit_code: int | None,
        elapsed_s: float | None,
        pid: int | None | object = _UNSET,
    ) -> None:
        """Update session state and metadata."""
        now = _now_iso()
        with self._file_lock():
            data = self._load_unlocked()
            sessions = data.setdefault("sessions", {})
            record = sessions.get(session_id)
            if not isinstance(record, dict):
                record = {"session_id": session_id}
            record.setdefault("created_at", now)
            if state is not None:
                record["state"] = state
            if message is not None:
                record["message"] = message
            if exit_code is not None:
                record["exit_code"] = int(exit_code)
            if elapsed_s is not None:
                record["elapsed_s"] = float(elapsed_s)
            if pid is not _UNSET:
                record["pid"] = int(pid) if pid is not None else None
            record["updated_at"] = now
            sessions[session_id] = record
            self._save_unlocked(data)

    def _load(self) -> dict[str, Any]:
        """Load JSON data with file lock."""
        with self._file_lock():
            return self._load_unlocked()

    def _save(self, data: dict[str, Any]) -> None:
        """Save JSON data with file lock."""
        with self._file_lock():
            self._save_unlocked(data)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self._sessions_path.exists():
            return {"schema_version": 1, "updated_at": "", "sessions": {}}
        try:
            raw = self._sessions_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            return {"schema_version": 1, "updated_at": "", "sessions": {}}

        if isinstance(data, dict):
            if "sessions" in data and isinstance(data.get("sessions"), dict):
                return {
                    "schema_version": int(data.get("schema_version") or 1),
                    "updated_at": str(data.get("updated_at") or ""),
                    "sessions": data.get("sessions", {}),
                }
            # Backward/alternate format: plain mapping of session_id -> record
            sessions = {k: v for k, v in data.items() if isinstance(v, dict)}
            return {"schema_version": 1, "updated_at": "", "sessions": sessions}

        return {"schema_version": 1, "updated_at": "", "sessions": {}}

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        payload = dict(data)
        payload["schema_version"] = int(payload.get("schema_version") or 1)
        payload["updated_at"] = _now_iso()
        payload.setdefault("sessions", {})
        tmp = self._sessions_path.with_suffix(self._sessions_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._sessions_path)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Cross-platform file lock using a lock file."""
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+b") as lock_file:
            _acquire_lock(lock_file)
            try:
                yield
            finally:
                _release_lock(lock_file)


def _acquire_lock(lock_file: Any) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        while True:
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    else:
        import fcntl  # type: ignore[import-not-found]

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _release_lock(lock_file: Any) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl  # type: ignore[import-not-found]

        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
