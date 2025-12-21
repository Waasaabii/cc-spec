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


def write_managed_file(path: Path, content: str) -> None:
    """Write or update a managed block while preserving user content."""
    body = f"{MANAGED_START}\n{content.strip()}\n{MANAGED_END}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return

    existing = path.read_text(encoding="utf-8")
    if MANAGED_START in existing and MANAGED_END in existing:
        start = existing.find(MANAGED_START)
        end = existing.find(MANAGED_END)
        if start != -1 and end != -1 and end > start:
            updated = existing[:start] + body + existing[end + len(MANAGED_END) :]
            path.write_text(updated.strip() + "\n", encoding="utf-8")
            return

    # No managed block: prepend managed content, keep existing text.
    updated = body + "\n" + existing
    path.write_text(updated.strip() + "\n", encoding="utf-8")
