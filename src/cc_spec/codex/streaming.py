"""Send Codex events to the external viewer (fixed port ingest)."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cc_spec.utils.files import find_project_root

INGEST_PATH = "/ingest"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 38888
CONFIG_RELATIVE_PATH = Path(".cc-spec") / "viewer.json"


def _env_enabled() -> bool:
    """Check if viewer ingest is enabled (default: on unless explicitly disabled)."""
    raw = (os.environ.get("CC_SPEC_CODEX_SSE") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _load_config() -> dict[str, Any] | None:
    config_path = Path.home() / CONFIG_RELATIVE_PATH
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def _config_host() -> str | None:
    data = _load_config()
    if not data:
        return None
    host = data.get("host")
    if isinstance(host, str) and host:
        return host
    return None


def _config_port() -> int | None:
    data = _load_config()
    if not data:
        return None
    port = data.get("port")
    if isinstance(port, int) and 1 <= port <= 65535:
        return port
    return None


def _env_host() -> str:
    raw = (os.environ.get("CC_SPEC_CODEX_SSE_HOST") or "").strip()
    if raw:
        return raw
    return _config_host() or DEFAULT_HOST


def _env_port() -> int:
    raw = (os.environ.get("CC_SPEC_CODEX_SSE_PORT") or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = DEFAULT_PORT
        else:
            if 1 <= value <= 65535:
                return value
        return DEFAULT_PORT
    return _config_port() or DEFAULT_PORT


@dataclass(frozen=True)
class ViewerClient:
    host: str
    port: int
    project_root: Path

    def publish_event(self, event: dict[str, Any]) -> None:
        event.setdefault("project_root", str(self.project_root))
        payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
        url = f"http://{self.host}:{self.port}{INGEST_PATH}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=0.5):
                return
        except Exception:
            return


def get_sse_client(project_root: Path) -> ViewerClient | None:
    """Return viewer ingest client if enabled; otherwise None."""
    if not _env_enabled():
        return None
    root = find_project_root(project_root) or project_root
    return ViewerClient(host=_env_host(), port=_env_port(), project_root=root)
