"""本地 Embedding HTTP 服务（fastembed）。

v0.1.5 目标：
- Claude/cc-spec 通过 ensure_running 自动拉起服务
- Codex 在执行任务时也可以调用该服务（通过 `cc-spec kb ...`）

接口：
- GET  /health
- POST /embed   {"texts": [...], "model": "optional"} -> {"vectors": [[...]], "dim": N}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cc_spec.version import EMBEDDING_SERVER_VERSION


def _pick_fallback_model(text_embedding_cls: Any, preferred: str) -> str:
    """从 fastembed 支持列表中选择一个尽量接近的 multilingual small 模型。"""
    supported: list[str] = []
    try:
        raw = text_embedding_cls.list_supported_models()
    except Exception:
        raw = None

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                supported.append(item)
            elif isinstance(item, dict) and "model" in item:
                supported.append(str(item["model"]))
            elif hasattr(item, "model"):
                supported.append(str(getattr(item, "model")))
            elif hasattr(item, "name"):
                supported.append(str(getattr(item, "name")))

    preferred_l = preferred.lower()
    supported_l = [(name, name.lower()) for name in supported]

    # 1) 尝试精确包含匹配（最保守）
    for name, lower in supported_l:
        if lower == preferred_l:
            return name

    # 2) 优先 multilingual e5 small
    candidates = [name for name, lower in supported_l if "multilingual" in lower and "e5" in lower]
    small = [name for name in candidates if "small" in name.lower()]
    if small:
        return small[0]
    if candidates:
        return candidates[0]

    # 3) 次选：中文/多语的小模型
    candidates = [name for name, lower in supported_l if ("zh" in lower or "multi" in lower) and "small" in lower]
    if candidates:
        return candidates[0]

    # 4) 最后兜底：列表第一个
    if supported:
        return supported[0]

    raise RuntimeError(
        f"fastembed 无法加载模型 '{preferred}'，且无法获取支持模型列表；请更换 embedding 模型配置。"
    )


def _load_fastembed(model: str) -> tuple["_Embedder", str]:
    try:
        from fastembed import TextEmbedding  # type: ignore[import-not-found]
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "未安装 fastembed。请先安装依赖：pip/uv 安装 fastembed 后重试。"
        ) from e

    preferred = model
    try:
        return _Embedder(TextEmbedding(model_name=preferred)), preferred
    except Exception:
        fallback = _pick_fallback_model(TextEmbedding, preferred)
        return _Embedder(TextEmbedding(model_name=fallback)), fallback


@dataclass
class _Embedder:
    engine: Any
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed 内部可能使用 onnxruntime，多线程下用锁保证稳定
        with self._lock:
            vectors = list(self.engine.embed(texts))
        # numpy/array -> list[float]
        result: list[list[float]] = []
        for v in vectors:
            try:
                result.append([float(x) for x in v])
            except TypeError:
                # v 可能已经是 list[float]
                result.append([float(x) for x in list(v)])
        return result


class _Handler(BaseHTTPRequestHandler):
    server_version = EMBEDDING_SERVER_VERSION

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            embedder: _Embedder = self.server.embedder  # type: ignore[attr-defined]
            self._json_response(
                200,
                {
                    "status": "ok",
                    "pid": os.getpid(),
                    "model": self.server.model,  # type: ignore[attr-defined]
                    "version": self.server_version,
                },
            )
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/embed":
            self._json_response(404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response(400, {"error": "invalid_content_length"})
            return

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json_response(400, {"error": "invalid_json"})
            return

        texts = data.get("texts")
        if not isinstance(texts, list) or not all(isinstance(x, str) for x in texts):
            self._json_response(400, {"error": "texts_must_be_list_of_strings"})
            return

        # 目前服务端固定单模型；请求里 model 仅用于提示
        embedder: _Embedder = self.server.embedder  # type: ignore[attr-defined]
        try:
            vectors = embedder.embed(texts)
        except Exception as e:  # pragma: no cover
            self._json_response(500, {"error": "embed_failed", "message": str(e)})
            return

        dim = len(vectors[0]) if vectors else 0
        self._json_response(200, {"vectors": vectors, "dim": dim})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        # 默认不输出 http.server 的访问日志；由 manager 负责写 runtime log
        return


def run(host: str, port: int, *, model: str) -> None:
    embedder, actual_model = _load_fastembed(model)

    httpd = ThreadingHTTPServer((host, port), _Handler)
    # 动态属性（供 handler 读取）
    httpd.embedder = embedder  # type: ignore[attr-defined]
    httpd.model = actual_model  # type: ignore[attr-defined]

    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cc-spec embedding server (fastembed)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    args = parser.parse_args(argv)

    run(args.host, args.port, model=args.model)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
