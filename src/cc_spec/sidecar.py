#!/usr/bin/env python3
"""
cc-spec sidecar entry point for Tauri bundling.

This module provides a minimal entry point that excludes heavy dependencies
like chromadb and fastembed to keep the bundle size small (~50MB target).

Included features:
- Core CLI commands (init, specify, plan, apply, etc.)
- SSE server for Codex streaming
- Basic RAG without vector store (file-based index)

Excluded features:
- ChromaDB vector store
- FastEmbed embeddings
- Heavy ML dependencies
"""

import sys
import os

# 设置环境变量标记为 sidecar 模式
os.environ["CC_SPEC_SIDECAR"] = "1"


def check_sidecar_mode() -> bool:
    """检查是否在 sidecar 模式下运行"""
    return os.environ.get("CC_SPEC_SIDECAR") == "1"


def main():
    """Sidecar 主入口"""
    # 延迟导入以减少启动时间
    from cc_spec import app

    # 运行 CLI
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
