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
from .session_state import SessionStateManager
from .streaming import get_sse_client


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


def _env_idle_timeout_s(default_s: int = 300) -> int:
    """获取 idle 超时时间（秒），用于检测 Codex 是否卡住。

    默认 300 秒（5分钟），因为 Codex 执行任务通常需要较长时间。
    可通过 CC_SPEC_CODEX_IDLE_TIMEOUT 环境变量覆盖。
    """
    raw = (os.environ.get("CC_SPEC_CODEX_IDLE_TIMEOUT") or "").strip()
    if not raw:
        return default_s
    try:
        return int(raw)
    except ValueError:
        return default_s


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


def _summarize_task(task: str, limit: int = 200) -> str:
    summary = " ".join(line.strip() for line in task.strip().splitlines() if line.strip())
    if not summary:
        summary = task.strip()
    if len(summary) > limit:
        return summary[:limit].rstrip() + "..."
    return summary


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
        return self._run(cmd, task, workdir, timeout_ms=timeout_ms, known_session_id=session_id)

    def _run(
        self,
        cmd: list[str],
        task: str,
        workdir: Path,
        *,
        timeout_ms: int | None = None,
        known_session_id: str | None = None,
    ) -> CodexResult:
        effective_timeout_ms = timeout_ms if timeout_ms is not None else _env_timeout_ms(self.timeout_ms)
        timeout_s = max(1.0, effective_timeout_ms / 1000.0)

        runtime_dir = get_cc_spec_dir(workdir) / "runtime" / "codex"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        log_path = runtime_dir / f"codex-{int(time.time())}.log"
        session_state = SessionStateManager(runtime_dir)
        task_summary = _summarize_task(task)

        started = time.time()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        exit_code = 1

        run_id = f"run_{int(started * 1000)}_{uuid.uuid4().hex[:8]}"
        output_mode = _get_output_mode()
        viewer = get_sse_client(workdir)
        session_id: str | None = known_session_id  # resume 时使用已知的 session_id
        session_registered = False
        process_pid: int | None = None
        seq = 0
        seq_lock = threading.Lock()

        # idle 检测：如果长时间无输出，打印警告
        idle_timeout_s = _env_idle_timeout_s(60)
        last_activity_time = time.time()
        activity_lock = threading.Lock()
        idle_warned = False
        stop_idle_monitor = threading.Event()

        # 创建进度指示器（仅 progress 模式）
        progress: CodexProgressIndicator | None = None
        if output_mode == OutputMode.PROGRESS:
            progress = CodexProgressIndicator()
            progress.start()

        def _register_session_if_needed() -> None:
            nonlocal session_registered
            if session_id and not session_registered:
                session_state.register_session(session_id, task_summary, process_pid)
                session_registered = True

        def _next_seq() -> int:
            nonlocal seq
            with seq_lock:
                seq += 1
                return seq

        def _emit_event(stream: str, line: str) -> None:
            nonlocal session_id, last_activity_time, idle_warned
            if not line:
                return

            # 更新活跃时间
            with activity_lock:
                last_activity_time = time.time()
                idle_warned = False  # 收到输出后重置警告状态

            if stream == "stdout":
                sid = _extract_session_id(line)
                if sid and session_id is None:
                    session_id = sid
                    _register_session_if_needed()

                # 进度模式：更新进度指示器
                if progress is not None:
                    progress.process_line(line)

            # stream 模式：打印所有输出
            if output_mode == OutputMode.STREAM:
                if stream == "stdout":
                    print(line, flush=True)
                else:
                    print(line, file=sys.stderr, flush=True)

            if viewer is not None:
                viewer.publish_event(
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

        def _idle_monitor() -> None:
            """监控线程：检测 Codex 是否长时间无输出。"""
            nonlocal idle_warned
            while not stop_idle_monitor.is_set():
                stop_idle_monitor.wait(10)  # 每 10 秒检查一次
                if stop_idle_monitor.is_set():
                    break
                with activity_lock:
                    idle_duration = time.time() - last_activity_time
                    if idle_duration >= idle_timeout_s and not idle_warned:
                        idle_warned = True
                        elapsed = time.time() - started
                        print(
                            f"[cc-spec] ⚠️ Codex 已 {int(idle_duration)}s 无输出 "
                            f"(总耗时 {int(elapsed)}s)，可能卡住或正在思考...",
                            file=sys.stderr,
                            flush=True,
                        )
                        if viewer is not None:
                            viewer.publish_event(
                                {
                                    "type": "codex.idle_warning",
                                    "ts": _now_iso(),
                                    "run_id": run_id,
                                    "session_id": session_id,
                                    "idle_seconds": int(idle_duration),
                                    "total_seconds": int(elapsed),
                                }
                            )
                        _register_session_if_needed()
                        if session_id:
                            session_state.update_session(
                                session_id,
                                state="idle",
                                message=f"idle warning: no output for {int(idle_duration)}s",
                                exit_code=None,
                                elapsed_s=elapsed,
                            )

        # 注意：codex.started 事件移到进程启动后发送（包含 pid）

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
            if viewer is not None:
                viewer.publish_event(
                    {
                        "type": "codex.error",
                        "ts": _now_iso(),
                        "run_id": run_id,
                        "session_id": None,
                        "error_type": CodexErrorType.NOT_FOUND.value,
                        "message": f"未找到 Codex CLI：{self.codex_bin}",
                    }
                )
                viewer.publish_event(
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
            _register_session_if_needed()
            if session_id:
                session_state.update_session(
                    session_id,
                    state="failed",
                    message=f"FileNotFoundError: {self.codex_bin}",
                    exit_code=127,
                    elapsed_s=duration,
                    pid=None,
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

        process_pid = process.pid
        _register_session_if_needed()

        # 发送 codex.started 事件（包含 pid）
        if viewer is not None:
            viewer.publish_event(
                {
                    "type": "codex.started",
                    "ts": _now_iso(),
                    "run_id": run_id,
                    "session_id": session_id,  # resume 时会有已知的 session_id
                    "pid": process_pid,
                    "project_root": str(workdir),
                }
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
        idle_thread = threading.Thread(target=_idle_monitor, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        idle_thread.start()

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

        # 停止 idle 监控线程
        stop_idle_monitor.set()
        idle_thread.join(timeout=2)

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

        _register_session_if_needed()
        if session_id:
            session_state.update_session(
                session_id,
                state="done" if success else "failed",
                message=parsed.message,
                exit_code=exit_code,
                elapsed_s=duration,
                pid=None,
            )

        # 停止进度指示器并显示摘要
        if progress is not None:
            progress.stop(success=success, duration=duration, message=parsed.message)

        if viewer is not None:
            viewer.publish_event(
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
