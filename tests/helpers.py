"""Test helper utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


def assert_contains_any(text: str, candidates: Iterable[str]) -> None:
    """Assert that at least one candidate substring exists in text."""
    if not any(candidate in text for candidate in candidates):
        raise AssertionError(f"Expected one of {list(candidates)} to be in text, got: {text}")


def read_yaml(path: Path) -> Any:
    """Read YAML content from a path."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, data: Any) -> None:
    """Write YAML content to a path."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
