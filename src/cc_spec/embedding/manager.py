"""Embedding 服务管理（按需拉起 + pid/port 管理）。"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from cc_spec.utils.files import get_cc_spec_dir


@dataclass(frozen=True)
class EmbeddingServiceInfo:
    host: str
    port: int
    pid: int
    model: str
    started_at: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def ensure_running(
    project_root: Path,
    *,
    model: str = "intfloat/multilingual-e5-small",
    host: str = "127.0.0.1",
    port: int | None = None,
    startup_timeout_s: float = 20.0,
) -> EmbeddingServiceInfo:
    """确保 embedding 服务可用；若不可用则自动启动。"""
    runtime_dir = _runtime_dir(project_root)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = runtime_dir / "embedding.json"

    existing = _load_runtime(runtime_file)
    if existing and _is_healthy(existing):
        return existing

    chosen_port = port if port is not None else _pick_free_port(host)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    log_path = runtime_dir / "embedding.log"

    with log_path.open("ab") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "cc_spec.embedding.server",
                "--host",
                host,
                "--port",
                str(chosen_port),
                "--model",
                model,
            ],
            cwd=str(project_root),
            stdout=log,
            stderr=log,
        )

    info = EmbeddingServiceInfo(
        host=host,
        port=chosen_port,
        pid=proc.pid,
        model=model,
        started_at=started_at,
    )
    _save_runtime(runtime_file, info)

    deadline = time.time() + startup_timeout_s
    while time.time() < deadline:
        if _is_healthy(info):
            actual_model = _get_health_model(info)
            if actual_model and actual_model != info.model:
                info = EmbeddingServiceInfo(
                    host=info.host,
                    port=info.port,
                    pid=info.pid,
                    model=actual_model,
                    started_at=info.started_at,
                )
                _save_runtime(runtime_file, info)
            return info
        time.sleep(0.2)

    raise RuntimeError(
        "Embedding 服务启动超时。请检查 `.cc-spec/runtime/embedding.log` 以定位原因。"
    )


def embed_texts(
    project_root: Path,
    texts: list[str],
    *,
    model: str = "intfloat/multilingual-e5-small",
) -> list[list[float]]:
    """批量获取 embeddings（自动确保服务在线）。"""
    info = ensure_running(project_root, model=model)
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{info.base_url}/embed", json={"texts": texts})
        resp.raise_for_status()
        data = resp.json()
    vectors = data.get("vectors")
    if not isinstance(vectors, list):
        raise RuntimeError("Embedding 服务返回格式异常：缺少 vectors")
    # 运行时校验：每个向量必须是 list[float]
    result: list[list[float]] = []
    for v in vectors:
        if not isinstance(v, list):
            raise RuntimeError("Embedding 服务返回格式异常：vectors 维度错误")
        result.append([float(x) for x in v])
    return result


def _runtime_dir(project_root: Path) -> Path:
    return get_cc_spec_dir(project_root) / "runtime"


def _pick_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _load_runtime(runtime_file: Path) -> EmbeddingServiceInfo | None:
    if not runtime_file.exists():
        return None
    try:
        data = json.loads(runtime_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        return EmbeddingServiceInfo(
            host=str(data["host"]),
            port=int(data["port"]),
            pid=int(data["pid"]),
            model=str(data["model"]),
            started_at=str(data.get("started_at", "")),
        )
    except Exception:
        return None


def _save_runtime(runtime_file: Path, info: EmbeddingServiceInfo) -> None:
    payload = {
        "host": info.host,
        "port": info.port,
        "pid": info.pid,
        "model": info.model,
        "started_at": info.started_at,
    }
    runtime_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_healthy(info: EmbeddingServiceInfo) -> bool:
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{info.base_url}/health")
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("status") == "ok"
    except Exception:
        return False


def _get_health_model(info: EmbeddingServiceInfo) -> str | None:
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{info.base_url}/health")
            if resp.status_code != 200:
                return None
            data = resp.json()
            model = data.get("model")
            return str(model) if model else None
    except Exception:
        return None
