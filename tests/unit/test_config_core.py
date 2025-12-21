"""KB-related config tests."""

from pathlib import Path

from cc_spec.core.config import Config, load_config, save_config


def test_kb_config_defaults() -> None:
    config = Config()
    assert config.kb.chunking.strategy == "ast-only"
    assert ".py" in config.kb.chunking.ast.supported_extensions
    assert config.kb.update.post_task_sync.strategy == "smart"
    assert config.kb.retrieval.pre_execution.max_chunks == 10


def test_kb_config_roundtrip(tmp_path: Path) -> None:
    config = Config()
    config.kb.chunking.strategy = "smart"
    config.kb.chunking.ast.supported_extensions = [".py", ".ts"]
    config.kb.chunking.line.lines_per_chunk = 123
    config.kb.chunking.llm.priority_files = ["readme.md"]
    config.kb.update.post_task_sync.strategy = "full"
    config.kb.retrieval.pre_execution.max_chunks = 7
    config.kb.retrieval.pre_execution.max_tokens = 4096
    config.kb.retrieval.strategy.type = "semantic"

    path = tmp_path / "config.yaml"
    save_config(config, path)
    loaded = load_config(path)

    assert loaded.kb.chunking.strategy == "smart"
    assert loaded.kb.chunking.ast.supported_extensions == [".py", ".ts"]
    assert loaded.kb.chunking.line.lines_per_chunk == 123
    assert loaded.kb.chunking.llm.priority_files == ["readme.md"]
    assert loaded.kb.update.post_task_sync.strategy == "full"
    assert loaded.kb.retrieval.pre_execution.max_chunks == 7
    assert loaded.kb.retrieval.pre_execution.max_tokens == 4096
    assert loaded.kb.retrieval.strategy.type == "semantic"
