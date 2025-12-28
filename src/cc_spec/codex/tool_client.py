"""ToolClient: 通过 cc-spec-tool HTTP API 调用 Codex。

强制要求：
- 所有 Codex 调用必须通过 tool
- tool 未运行时直接报错退出
- 不提供任何 fallback 机制
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import httpx

from .models import CodexErrorType, CodexResult


def _get_tool_port() -> int:
    """获取 tool 的 HTTP 端口。"""
    # 1. 环境变量
    env_port = os.environ.get("CC_SPEC_TOOL_PORT", "").strip()
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass

    # 2. 配置文件
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    config_path = Path(home) / ".cc-spec" / "tools.json"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
                port = config.get("port")
                if isinstance(port, int) and port > 0:
                    return port
        except Exception:
            pass

    # 3. 默认端口
    return 38888


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检查端口是否开放。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


@dataclass
class ToolClient:
    """cc-spec-tool HTTP API 客户端。

    强制通过 tool 调用 Codex，不提供任何 fallback。
    """

    host: str = "127.0.0.1"
    port: int = field(default_factory=_get_tool_port)
    timeout_ms: int = 7_200_000  # 2h

    def is_available(self) -> bool:
        """检查 tool 是否可用。"""
        return _is_port_open(self.host, self.port)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def run_codex(
        self,
        project_path: str | Path,
        prompt: str,
        *,
        session_id: str | None = None,
        timeout_ms: int | None = None,
    ) -> CodexResult:
        """异步调用 Codex 并等待结果。

        1. 发送 POST /api/codex/run
        2. 订阅 SSE /events
        3. 等待 codex.completed 事件（匹配 request_id）
        4. 返回结果

        Args:
            project_path: 项目路径
            prompt: 任务描述
            session_id: 可选的会话 ID（用于 resume）
            timeout_ms: 超时时间（毫秒）

        Returns:
            CodexResult

        Raises:
            SystemExit: tool 不可用时
        """
        if not self.is_available():
            raise SystemExit(
                "❌ cc-spec-tool 未运行！\n"
                f"请先启动: cd apps/cc-spec-tool && bun run tauri dev\n"
                f"或运行已编译版本\n"
                f"（检测端口: {self.host}:{self.port}）"
            )

        effective_timeout_ms = timeout_ms if timeout_ms is not None else self.timeout_ms
        timeout_s = max(1.0, effective_timeout_ms / 1000.0)

        # 生成 request_id
        request_id = f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        # 准备请求体
        payload = {
            "project_path": str(project_path),
            "prompt": prompt,
            "request_id": request_id,
            "timeout_ms": effective_timeout_ms,
        }
        if session_id:
            payload["session_id"] = session_id

        started = time.time()

        # 创建结果队列
        result_queue: queue.Queue[dict] = queue.Queue()
        stop_event = threading.Event()

        # 启动 SSE 监听线程
        sse_thread = threading.Thread(
            target=self._sse_listener,
            args=(request_id, result_queue, stop_event),
            daemon=True,
        )
        sse_thread.start()

        # 等待 SSE 连接建立
        time.sleep(0.1)

        try:
            # 发送请求
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/api/codex/run",
                    json=payload,
                )
                if response.status_code != 202:
                    stop_event.set()
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_msg = error_data.get("error", response.text)
                    return CodexResult(
                        success=False,
                        exit_code=-1,
                        message=f"提交任务失败: {error_msg}",
                        session_id=None,
                        stderr="",
                        duration_seconds=time.time() - started,
                        error_type=CodexErrorType.EXEC_FAILED,
                    )

            # 等待结果
            try:
                result = result_queue.get(timeout=timeout_s + 30)  # 额外 30s 缓冲
            except queue.Empty:
                return CodexResult(
                    success=False,
                    exit_code=124,
                    message="等待结果超时",
                    session_id=session_id,
                    stderr="",
                    duration_seconds=time.time() - started,
                    error_type=CodexErrorType.TIMEOUT,
                )

            duration = time.time() - started
            success = result.get("success", False)
            exit_code = result.get("exit_code", -1)
            result_session_id = result.get("session_id") or session_id

            if success:
                error_type = CodexErrorType.NONE
            elif exit_code == 124:
                error_type = CodexErrorType.TIMEOUT
            else:
                error_type = CodexErrorType.EXEC_FAILED

            return CodexResult(
                success=success,
                exit_code=exit_code,
                message=result.get("message", ""),
                session_id=result_session_id,
                stderr="",
                duration_seconds=duration,
                error_type=error_type,
            )

        finally:
            stop_event.set()
            sse_thread.join(timeout=2)

    def _sse_listener(
        self,
        request_id: str,
        result_queue: queue.Queue,
        stop_event: threading.Event,
    ) -> None:
        """SSE 监听线程。"""
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", f"{self.base_url}/events") as response:
                    buffer = ""
                    for chunk in response.iter_text():
                        if stop_event.is_set():
                            break

                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            event = self._parse_sse_event(event_str)
                            if event is None:
                                continue

                            # 检查是否是我们等待的 codex.completed 事件
                            if (
                                event.get("type") == "codex.completed"
                                and event.get("request_id") == request_id
                            ):
                                result_queue.put(event)
                                return
        except Exception:
            pass  # 忽略 SSE 连接错误

    def _parse_sse_event(self, event_str: str) -> dict | None:
        """解析 SSE 事件。"""
        data = None
        for line in event_str.split("\n"):
            if line.startswith("data:"):
                data = line[5:].strip()

        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                pass
        return None

    def get_sessions(self, project_path: str | Path) -> dict:
        """获取会话列表。"""
        if not self.is_available():
            raise SystemExit(
                "❌ cc-spec-tool 未运行！\n"
                f"请先启动: cd apps/cc-spec-tool && bun run tauri dev\n"
                f"或运行已编译版本"
            )

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{self.base_url}/api/codex/sessions",
                params={"project_path": str(project_path)},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("sessions", {})
            return {}

    def pause_session(self, project_path: str | Path, session_id: str) -> bool:
        """暂停会话。"""
        if not self.is_available():
            raise SystemExit("❌ cc-spec-tool 未运行！")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/api/codex/pause",
                json={
                    "project_path": str(project_path),
                    "session_id": session_id,
                },
            )
            return response.status_code == 200

    def kill_session(self, project_path: str | Path, session_id: str) -> bool:
        """终止会话。"""
        if not self.is_available():
            raise SystemExit("❌ cc-spec-tool 未运行！")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/api/codex/kill",
                json={
                    "project_path": str(project_path),
                    "session_id": session_id,
                },
            )
            return response.status_code == 200


def get_tool_client() -> ToolClient:
    """获取 ToolClient 实例。

    如果 tool 不可用，直接报错退出。
    不提供任何 fallback 机制。
    """
    client = ToolClient()
    if not client.is_available():
        raise SystemExit(
            "❌ cc-spec-tool 未运行！\n"
            "请先启动: cd apps/cc-spec-tool && bun run tauri dev\n"
            "或运行已编译版本\n"
            "\n"
            "所有 Codex 调用必须通过 tool 进行。"
        )
    return client
