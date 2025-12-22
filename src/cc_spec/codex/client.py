"""Codex CLI 调用封装（支持 exec/resume + JSONL 解析）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cc_spec.utils.files import get_cc_spec_dir

from .models import CodexErrorType, CodexResult
from .parser import parse_codex_jsonl
from .progress import CodexProgressIndicator, OutputMode
from .streaming import get_sse_server


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


def _env_bool(name: str, *, default: bool | None = None) -> bool | None:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _get_output_mode() -> OutputMode:
    """获取 Codex 输出模式。

    优先级:
    1. CC_SPEC_CODEX_OUTPUT 环境变量（推荐）
    2. CC_SPEC_CODEX_STREAM 环境变量（兼容旧版，已弃用）
    3. 根据终端环境自动检测（TTY -> progress，非 TTY -> quiet）
    """
    # 优先检查新变量
    raw = (os.environ.get("CC_SPEC_CODEX_OUTPUT") or "").strip().lower()
    if raw:
        if raw == "stream":
            return OutputMode.STREAM
        if raw == "progress":
            return OutputMode.PROGRESS
        if raw == "quiet":
            return OutputMode.QUIET
        # 无效值视为未设置

    # 兼容旧变量 CC_SPEC_CODEX_STREAM（已弃用）
    stream_override = _env_bool("CC_SPEC_CODEX_STREAM")
    if stream_override is True:
        return OutputMode.STREAM
    if stream_override is False:
        return OutputMode.QUIET

    # 根据终端环境自动检测
    if sys.stdout.isatty():
        return OutputMode.PROGRESS  # 终端环境默认使用进度模式
    return OutputMode.QUIET  # 非终端环境默认静默


def _should_stream_to_terminal() -> bool:
    """是否应该流式输出到终端（兼容函数）。"""
    mode = _get_output_mode()
    return mode == OutputMode.STREAM


def _extract_session_id(line: str) -> str | None:
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("type") == "thread.started":
        thread_id = obj.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
    return None


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
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        exit_code = 1

        run_id = f"run_{int(started * 1000)}_{uuid.uuid4().hex[:8]}"
        output_mode = _get_output_mode()
        sse = get_sse_server(workdir)
        session_id: str | None = None
        seq = 0
        seq_lock = threading.Lock()

        # 创建进度指示器（仅 progress 模式）
        progress: CodexProgressIndicator | None = None
        if output_mode == OutputMode.PROGRESS:
            progress = CodexProgressIndicator()
            progress.start()

        def _next_seq() -> int:
            nonlocal seq
            with seq_lock:
                seq += 1
                return seq

        def _emit_event(stream: str, line: str) -> None:
            nonlocal session_id
            if not line:
                return
            if stream == "stdout":
                sid = _extract_session_id(line)
                if sid and session_id is None:
                    session_id = sid

                # 进度模式：更新进度指示器
                if progress is not None:
                    progress.process_line(line)

            # stream 模式：打印所有输出
            if output_mode == OutputMode.STREAM:
                if stream == "stdout":
                    print(line, flush=True)
                else:
                    print(line, file=sys.stderr, flush=True)

            if sse is not None:
                sse.publish_event(
                    {
                        "type": "codex.stream",
                        "ts": _now_iso(),
                        "run_id": run_id,
                        "session_id": session_id,
                        "stream": stream,
                        "seq": _next_seq(),
                        "text": line,
                    }
                )

        if sse is not None:
            sse.publish_event(
                {
                    "type": "codex.started",
                    "ts": _now_iso(),
                    "run_id": run_id,
                    "session_id": None,
                }
            )

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(workdir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            duration = time.time() - started
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
            if sse is not None:
                sse.publish_event(
                    {
                        "type": "codex.error",
                        "ts": _now_iso(),
                        "run_id": run_id,
                        "session_id": None,
                        "error_type": CodexErrorType.NOT_FOUND.value,
                        "message": f"未找到 Codex CLI：{self.codex_bin}",
                    }
                )
                sse.publish_event(
                    {
                        "type": "codex.completed",
                        "ts": _now_iso(),
                        "run_id": run_id,
                        "session_id": None,
                        "success": False,
                        "exit_code": 127,
                        "error_type": CodexErrorType.NOT_FOUND.value,
                        "duration_s": round(duration, 2),
                    }
                )
            return CodexResult(
                success=False,
                exit_code=127,
                message=f"未找到 Codex CLI：{self.codex_bin}",
                session_id=None,
                stderr="",
                duration_seconds=duration,
                error_type=CodexErrorType.NOT_FOUND,
            )

        if process.stdin is not None:
            try:
                process.stdin.write(task)
                process.stdin.flush()
            except Exception:
                pass
            finally:
                try:
                    process.stdin.close()
                except Exception:
                    pass

        def _read_stdout() -> None:
            if process.stdout is None:
                return
            for raw in iter(process.stdout.readline, ""):
                line = raw.rstrip("\n")
                stdout_lines.append(line)
                _emit_event("stdout", line)
            process.stdout.close()

        def _read_stderr() -> None:
            if process.stderr is None:
                return
            for raw in iter(process.stderr.readline, ""):
                line = raw.rstrip("\n")
                stderr_lines.append(line)
                _emit_event("stderr", line)
            process.stderr.close()

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except Exception:
                    pass
        else:
            exit_code = process.returncode if process.returncode is not None else exit_code

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        stdout_text = "\n".join(stdout_lines)
        stderr_text = "\n".join(stderr_lines)

        parsed = parse_codex_jsonl(stdout_lines)
        if parsed.session_id and session_id is None:
            session_id = parsed.session_id

        duration = time.time() - started

        log_data = {
            "ts": _now_iso(),
            "cmd": cmd,
            "exit_code": exit_code,
            "duration_s": round(duration, 2),
            "timeout_s": timeout_s,
            "events_parsed": parsed.events_parsed,
            "stdout_lines": len(stdout_lines),
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

        success = exit_code == 0 and not timed_out
        if success:
            error_type = CodexErrorType.NONE
        elif exit_code == 124:
            error_type = CodexErrorType.TIMEOUT
        else:
            error_type = CodexErrorType.EXEC_FAILED

        # 停止进度指示器并显示摘要
        if progress is not None:
            progress.stop(success=success, duration=duration, message=parsed.message)

        if sse is not None:
            sse.publish_event(
                {
                    "type": "codex.completed",
                    "ts": _now_iso(),
                    "run_id": run_id,
                    "session_id": session_id,
                    "success": success,
                    "exit_code": exit_code,
                    "error_type": error_type.value,
                    "duration_s": round(duration, 2),
                }
            )

        return CodexResult(
            success=success,
            exit_code=exit_code,
            message=parsed.message,
            session_id=session_id,
            stderr=stderr_text,
            duration_seconds=duration,
            events_parsed=parsed.events_parsed,
            error_type=error_type,
        )
