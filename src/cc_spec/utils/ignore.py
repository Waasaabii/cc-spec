"""cc-spec 的忽略规则（类似 .gitignore 的简化版）。

v0.1.5：用于 KB 扫描时的 include/exclude 控制。

设计目标：
- 简单可控：支持注释、空行、目录规则（以 / 结尾）、以及 ! 反选。
- 语义稳定：在 Windows/Linux 上都使用 posix 风格相对路径匹配。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DEFAULT_KB_IGNORE_PATTERNS: list[str] = [
    # VCS / IDE / caches
    ".git/",
    ".idea/",
    ".vscode/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".tox/",
    ".nox/",
    # Virtual env / deps
    ".venv/",
    "venv/",
    "ENV/",
    "env/",
    "node_modules/",
    # Build outputs
    "dist/",
    "build/",
    # cc-spec runtime / derived artifacts
    ".cc-spec/runtime/",
    ".cc-spec/vectordb/",
    ".cc-spec/kb.events.jsonl",
    ".cc-spec/kb.snapshot.jsonl",
    ".cc-spec/kb.manifest.json",
]


@dataclass(frozen=True)
class IgnorePattern:
    """单条忽略规则。"""

    raw: str
    pattern: str
    negated: bool
    directory_only: bool

    @classmethod
    def parse(cls, raw: str) -> "IgnorePattern | None":
        line = raw.strip()
        if not line or line.startswith("#"):
            return None

        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
            if not line:
                return None

        directory_only = line.endswith("/")
        pattern = line.rstrip("/")
        # 统一去掉开头的 ./ 与 /
        if pattern.startswith("./"):
            pattern = pattern[2:]
        pattern = pattern.lstrip("/")

        if not pattern:
            return None

        return cls(
            raw=raw,
            pattern=pattern,
            negated=negated,
            directory_only=directory_only,
        )


class IgnoreRules:
    """一组忽略规则，按顺序应用（后规则可覆盖前规则）。"""

    def __init__(self, patterns: list[IgnorePattern]) -> None:
        self._patterns = patterns

    @classmethod
    def from_lines(cls, lines: list[str]) -> "IgnoreRules":
        patterns: list[IgnorePattern] = []
        for line in lines:
            parsed = IgnorePattern.parse(line)
            if parsed is not None:
                patterns.append(parsed)
        return cls(patterns)

    @classmethod
    def from_file(
        cls,
        ignore_file: Path,
        *,
        extra_patterns: list[str] | None = None,
    ) -> "IgnoreRules":
        lines: list[str] = []
        if ignore_file.exists():
            lines.extend(ignore_file.read_text(encoding="utf-8").splitlines())
        if extra_patterns:
            lines.extend(extra_patterns)
        return cls.from_lines(lines)

    def is_ignored(self, rel_path: PurePosixPath, *, is_dir: bool) -> bool:
        """判断相对路径是否被忽略。

        参数：
            rel_path：相对项目根目录的 posix 路径（不以 / 开头）
            is_dir：该路径是否为目录
        """
        # 规则按顺序生效：匹配到则覆盖当前状态
        ignored = False
        rel_str = rel_path.as_posix()

        for rule in self._patterns:
            if rule.directory_only and not is_dir:
                # 目录规则对文件：依然需要匹配其父目录前缀
                if rel_str.startswith(f"{rule.pattern}/"):
                    ignored = not rule.negated
                continue

            if _match_path(rel_path, rel_str, rule.pattern):
                ignored = not rule.negated

        return ignored

    def should_prune_dir(self, rel_dir: PurePosixPath) -> bool:
        """判断目录是否可以被剪枝（不进入遍历）。

        为了支持 `!` 反选规则，我们不能简单地对“被忽略的目录”一律剪枝，
        否则 `src/` + `!src/keep.txt` 这种常见写法会失效。

        规则：
        - 目录未被忽略：不剪枝
        - 目录被忽略：如果存在可能匹配该目录下任意路径的 negated 规则 → 不剪枝
          否则可安全剪枝（提升扫描性能）
        """
        if not self.is_ignored(rel_dir, is_dir=True):
            return False

        rel_str = rel_dir.as_posix().rstrip("/")
        prefix = f"{rel_str}/" if rel_str else ""

        for rule in self._patterns:
            if not rule.negated:
                continue

            pat = rule.pattern

            # 1) 明确前缀：!src/keep.txt 或 !src/**/*.py
            if rel_str and (pat == rel_str or pat.startswith(prefix)):
                return False

            # 2) 无 / 的 pattern（如 !*.md / !README.md）可能匹配任意目录下文件名
            # 保守处理：不剪枝，保证语义正确
            if "/" not in pat:
                return False

            # 3) 以通配开头的跨目录规则（如 !**/*.md）
            if pat.startswith("**/"):
                return False

        return True


def _match_path(rel_path: PurePosixPath, rel_str: str, pattern: str) -> bool:
    # 1) 目录前缀：在 IgnorePattern.parse 已处理 directory_only 的尾部 /
    if rel_str == pattern or rel_str.startswith(f"{pattern}/"):
        return True

    # 2) PurePath.match 支持 ** 语义（相对匹配）
    try:
        if rel_path.match(pattern):
            return True
    except Exception:
        # 保守：pattern 语法异常时视为不匹配
        return False

    return False
