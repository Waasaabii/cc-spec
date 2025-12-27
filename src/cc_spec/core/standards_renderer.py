"""Render standards artifacts (SKILL.md / AGENTS.md) from internal templates."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .standards_templates import (
    AGENTS_MD_TEMPLATE,
    CLAUDE_FORBIDDEN,
    CLAUDE_KB_WRITE_RULES,
    CLAUDE_OUTPUTS,
    CLAUDE_ROLE_RULES,
    CLAUDE_WORKFLOW_PHASES,
    CODEX_COMMANDS,
    CODEX_EXECUTION_RULES,
    CODEX_FORBIDDEN,
    CODEX_OUTPUTS,
    CODEX_ROLE_RULES,
    MANAGED_END,
    MANAGED_START,
    SKILL_MD_TEMPLATE,
    format_artifacts,
    format_commands,
    format_rules,
    format_workflow,
)


def _apply_template(template: str, mapping: dict[str, str]) -> str:
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered


def _render_project_rules(rules: Iterable[str] | None) -> str:
    return format_rules(rules or [])


def render_skill_md(*, project_coding_rules: Iterable[str] | None = None) -> str:
    mapping = {
        "claude.role.rules": format_rules(CLAUDE_ROLE_RULES),
        "claude.outputs.artifacts": format_artifacts(CLAUDE_OUTPUTS),
        "claude.outputs.forbidden": format_rules(CLAUDE_FORBIDDEN),
        "claude.workflow.phases": format_workflow(CLAUDE_WORKFLOW_PHASES),
        "project.coding_rules": _render_project_rules(project_coding_rules),
        "claude.kb_write_rules.rules": format_rules(CLAUDE_KB_WRITE_RULES),
    }
    return _apply_template(SKILL_MD_TEMPLATE, mapping).strip() + "\n"


def render_agents_md(*, project_coding_rules: Iterable[str] | None = None) -> str:
    mapping = {
        "codex.role.rules": format_rules(CODEX_ROLE_RULES),
        "codex.outputs.artifacts": format_artifacts(CODEX_OUTPUTS),
        "codex.outputs.forbidden": format_rules(CODEX_FORBIDDEN),
        "codex.execution_rules.rules": format_rules(CODEX_EXECUTION_RULES),
        "project.coding_rules": _render_project_rules(project_coding_rules),
        "codex.commands.list": format_commands(CODEX_COMMANDS),
    }
    return _apply_template(AGENTS_MD_TEMPLATE, mapping).strip() + "\n"


def render_claude_skill_frontmatter() -> str:
    """Render YAML frontmatter for `.claude/skills/cc-spec-standards/SKILL.md`.

    Claude Code 识别 Skill 依赖文件头部 frontmatter（name/description 等）。
    """
    return (
        "---\n"
        "name: cc-spec-standards\n"
        "description: \"cc-spec 工作流规范（Claude Code 编排层）。在 cc-spec 初始化过的项目中使用。\"\n"
        "allowed-tools: Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion\n"
        "---\n"
    )


def _strip_yaml_frontmatter(existing: str) -> str:
    """Remove a leading YAML frontmatter block (--- ... ---) if present."""
    text = existing.lstrip("\ufeff")  # tolerate BOM
    if not text.startswith("---"):
        return existing
    lines = text.splitlines(keepends=True)
    if not lines:
        return existing
    if lines[0].strip() != "---":
        return existing
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            remaining = "".join(lines[idx + 1 :])
            return remaining.lstrip("\r\n")
    return existing


def write_managed_file(path: Path, content: str, *, preamble: str | None = None) -> None:
    """Write or update a managed block while preserving user content.

    If `preamble` is provided, it is written at the top of file (outside managed block),
    and any existing YAML frontmatter is replaced.
    """
    managed_block = f"{MANAGED_START}\n{content.strip()}\n{MANAGED_END}\n"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if preamble:
            path.write_text(
                f"{preamble.strip()}\n\n{managed_block}".strip() + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(managed_block, encoding="utf-8")
        return

    existing = path.read_text(encoding="utf-8")
    working = _strip_yaml_frontmatter(existing) if preamble else existing

    if MANAGED_START in working and MANAGED_END in working:
        start = working.find(MANAGED_START)
        end = working.find(MANAGED_END)
        if start != -1 and end != -1 and end > start:
            updated = working[:start] + managed_block + working[end + len(MANAGED_END) :]
        else:
            updated = managed_block + "\n" + working
    else:
        updated = managed_block + "\n" + working

    if preamble:
        final = f"{preamble.strip()}\n\n{updated}".strip() + "\n"
    else:
        final = updated.strip() + "\n"
    path.write_text(final, encoding="utf-8")
