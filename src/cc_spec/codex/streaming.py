"""Lightweight SSE streaming for Codex CLI output."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cc_spec.utils.files import get_cc_spec_dir

SSE_PATH = "/events"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 38888

_SERVER: "SSEServer | None" = None
_SERVER_LOCK = threading.Lock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _env_enabled() -> bool:
    raw = (os.environ.get("CC_SPEC_CODEX_SSE") or "").strip().lower()
    if not raw:
        return False
    return raw in {"1", "true", "yes", "on"}


def _env_host() -> str:
    raw = (os.environ.get("CC_SPEC_CODEX_SSE_HOST") or "").strip()
    return raw or DEFAULT_HOST


def _env_port() -> int:
    raw = (os.environ.get("CC_SPEC_CODEX_SSE_PORT") or "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def get_sse_server(project_root: Path) -> "SSEServer | None":
    """Return a shared SSE server if enabled; otherwise None."""
    if not _env_enabled():
        return None

    host = _env_host()
    port = _env_port()

    with _SERVER_LOCK:
        global _SERVER
        if _SERVER is None:
            server = SSEServer(host=host, port=port, path=SSE_PATH)
            if not server.start():
                return None
            _SERVER = server
        _SERVER.write_manifest(project_root)
        return _SERVER


@dataclass(frozen=True)
class StreamManifest:
    host: str
    port: int
    path: str
    started_at: str


class _Broadcaster:
    def __init__(self) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def add_client(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._clients.append(q)
        return q

    def remove_client(self, q: queue.Queue[str]) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def publish(self, payload: str) -> None:
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            q.put(payload)


class SSEServer:
    def __init__(self, *, host: str, port: int, path: str) -> None:
        self.host = host
        self.port = port
        self.path = path
        self.started_at = _now_iso()
        self._broadcaster = _Broadcaster()
        self._thread: threading.Thread | None = None
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> bool:
        try:
            handler = self._make_handler()
            server = ThreadingHTTPServer((self.host, self.port), handler)
            server.daemon_threads = True
            self._server = server
        except OSError:
            return False

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return True

    def publish_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "codex.stream")
        payload = json.dumps(event, ensure_ascii=False)
        message = f"event: {event_type}\ndata: {payload}\n\n"
        self._broadcaster.publish(message)

    def write_manifest(self, project_root: Path) -> None:
        runtime_dir = get_cc_spec_dir(project_root) / "runtime" / "codex"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        manifest = StreamManifest(
            host=self.host,
            port=self.port,
            path=self.path,
            started_at=self.started_at,
        )
        path = runtime_dir / "stream.json"
        try:
            path.write_text(json.dumps(manifest.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        broadcaster = self._broadcaster
        path = self.path

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                if self.path.split("?")[0] != path:
                    self.send_response(404)
                    self.end_headers()
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                client = broadcaster.add_client()
                try:
                    # Initial heartbeat to establish stream
                    self.wfile.write(b": ok\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            payload = client.get(timeout=1.0)
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                            continue

                        if payload is None:
                            break
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                except Exception:
                    return
                finally:
                    broadcaster.remove_client(client)

        return Handler
