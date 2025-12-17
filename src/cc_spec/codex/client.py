"""Codex CLI 调用封装（支持 exec/resume + JSONL 解析）。"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from cc_spec.utils.files import get_cc_spec_dir

from .models import CodexResult
from .parser import parse_codex_jsonl


def _env_timeout_ms(default_ms: int) -> int:
    raw = (os.environ.get("CODEX_TIMEOUT") or "").strip()
    if not raw:
        return default_ms
    try:
        return int(raw)
    except ValueError:
        return default_ms


@dataclass(frozen=True)
class CodexClient:
    codex_bin: str = "codex"
    timeout_ms: int = 7_200_000  # 2h

    def execute(self, task: str, workdir: Path, *, timeout_ms: int | None = None) -> CodexResult:
        cmd = [
            self.codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(workdir),
            "--json",
            "-",
        ]
        return self._run(cmd, task, workdir, timeout_ms=timeout_ms)

    def resume(
        self, session_id: str, task: str, workdir: Path, *, timeout_ms: int | None = None
    ) -> CodexResult:
        cmd = [
            self.codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(workdir),
            "--json",
            "resume",
            session_id,
            "-",
        ]
        return self._run(cmd, task, workdir, timeout_ms=timeout_ms)

    def _run(
        self, cmd: list[str], task: str, workdir: Path, *, timeout_ms: int | None = None
    ) -> CodexResult:
        effective_timeout_ms = timeout_ms if timeout_ms is not None else _env_timeout_ms(self.timeout_ms)
        timeout_s = max(1.0, effective_timeout_ms / 1000.0)

        runtime_dir = get_cc_spec_dir(workdir) / "runtime" / "codex"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        log_path = runtime_dir / f"codex-{int(time.time())}.log"

        started = time.time()
        stdout_text = ""
        stderr_text = ""
        exit_code = 1

        try:
            completed = subprocess.run(
                cmd,
                cwd=str(workdir),
                input=task,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
            exit_code = completed.returncode
            stdout_text = completed.stdout
            stderr_text = completed.stderr
        except FileNotFoundError:
            return CodexResult(
                success=False,
                exit_code=127,
                message=f"未找到 Codex CLI：{self.codex_bin}",
                session_id=None,
                stderr="",
                duration_seconds=time.time() - started,
            )
        except subprocess.TimeoutExpired as e:
            exit_code = 124
            stdout_text = e.stdout or ""
            stderr_text = e.stderr or ""

        parsed = parse_codex_jsonl(stdout_text.splitlines())

        duration = time.time() - started

        # 写入 runtime log（便于定位 codex 行为）
        try:
            log_path.write_text(stderr_text, encoding="utf-8")
        except Exception:
            pass

        success = exit_code == 0
        return CodexResult(
            success=success,
            exit_code=exit_code,
            message=parsed.message,
            session_id=parsed.session_id,
            stderr=stderr_text,
            duration_seconds=duration,
            events_parsed=parsed.events_parsed,
        )
