"""Codex CLI 调用封装（支持 exec/resume + JSONL 解析）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cc_spec.utils.files import get_cc_spec_dir

from .models import CodexErrorType, CodexResult
from .parser import parse_codex_jsonl


def _now_iso() -> str:
    """返回当前时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_bin(name: str) -> str:
    """解析可执行文件的完整路径。

    Windows 上 subprocess.run 无法自动找到 .cmd/.bat 扩展名的可执行文件，
    需要使用 shutil.which() 来解析完整路径。

    Args:
        name: 可执行文件名（如 "codex"）

    Returns:
        完整路径（如果找到）或原始名称（如果未找到）
    """
    resolved = shutil.which(name)
    return resolved if resolved else name


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
        # 解析可执行文件完整路径（Windows 兼容）
        resolved_bin = _resolve_bin(self.codex_bin)
        cmd = [
            resolved_bin,
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
        # 解析可执行文件完整路径（Windows 兼容）
        resolved_bin = _resolve_bin(self.codex_bin)
        cmd = [
            resolved_bin,
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
            duration = time.time() - started
            # 记录 FileNotFoundError 到日志
            log_data = {
                "ts": _now_iso(),
                "cmd": cmd,
                "exit_code": 127,
                "duration_s": round(duration, 2),
                "timeout_s": timeout_s,
                "error": f"FileNotFoundError: {self.codex_bin}",
            }
            try:
                log_path.write_text(
                    json.dumps(log_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[cc-spec] warning: failed to write codex log to {log_path}: {e}", file=sys.stderr)
            return CodexResult(
                success=False,
                exit_code=127,
                message=f"未找到 Codex CLI：{self.codex_bin}",
                session_id=None,
                stderr="",
                duration_seconds=duration,
                error_type=CodexErrorType.NOT_FOUND,
            )
        except subprocess.TimeoutExpired as e:
            exit_code = 124
            stdout_text = e.stdout or ""
            stderr_text = e.stderr or ""

        parsed = parse_codex_jsonl(stdout_text.splitlines())

        duration = time.time() - started

        # 写入结构化 JSON 日志（便于调试 codex 行为）
        log_data = {
            "ts": _now_iso(),
            "cmd": cmd,
            "exit_code": exit_code,
            "duration_s": round(duration, 2),
            "timeout_s": timeout_s,
            "events_parsed": parsed.events_parsed,
            "stdout_lines": len(stdout_text.splitlines()),
            "stderr": stderr_text[:2000] if stderr_text else "",
            "stdout_preview": stdout_text[:1000] if stdout_text else "",
        }
        try:
            log_path.write_text(
                json.dumps(log_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[cc-spec] warning: failed to write codex log to {log_path}: {e}", file=sys.stderr)

        success = exit_code == 0

        # 根据 exit_code 判断错误类型
        if success:
            error_type = CodexErrorType.NONE
        elif exit_code == 124:
            error_type = CodexErrorType.TIMEOUT
        else:
            error_type = CodexErrorType.EXEC_FAILED

        return CodexResult(
            success=success,
            exit_code=exit_code,
            message=parsed.message,
            session_id=parsed.session_id,
            stderr=stderr_text,
            duration_seconds=duration,
            events_parsed=parsed.events_parsed,
            error_type=error_type,
        )
