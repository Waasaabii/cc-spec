"""cc-spec 版本常量（集中管理）。"""

from __future__ import annotations

from functools import lru_cache
import re

__version__ = "0.1.8"
PACKAGE_VERSION = __version__
TASKS_YAML_VERSION = "1.6"
CONFIG_VERSION = "1.4"
KB_SCHEMA_VERSION = "0.1.8"
TEMPLATE_VERSION = "1.0.8"

EMBEDDING_SERVER_VERSION = f"cc-spec-embedding/{PACKAGE_VERSION}"
UI_VERSION_INFO = f"v{PACKAGE_VERSION}"

_VERSION_PART_RE = re.compile(r"\d+")


@lru_cache(maxsize=None)
def parse_version(version: str | None) -> tuple[int, ...]:
    """Parse a semantic-like version string into a tuple of ints."""
    if version is None:
        return tuple()
    value = str(version).strip()
    if not value:
        return tuple()
    if value.startswith(("v", "V")):
        value = value[1:]
    parts: list[int] = []
    for part in value.split("."):
        match = _VERSION_PART_RE.match(part)
        if not match:
            break
        parts.append(int(match.group(0)))
    return tuple(parts)


def is_version_gte(version: str | None, minimum: str | None) -> bool:
    """Return True if version >= minimum using semantic-ish comparison."""
    left = parse_version(version)
    right = parse_version(minimum)
    length = max(len(left), len(right))
    if length:
        left = left + (0,) * (length - len(left))
        right = right + (0,) * (length - len(right))
    return left >= right
