# cc-spec

**Spec-Driven AI-Assisted Development Workflow CLI Tool**

English | [中文](../README.md)

---

## Introduction

cc-spec is a spec-driven development CLI tool that combines the best of [OpenSpec](https://github.com/hannesrudolph/openspec) and [Spec-Kit](https://github.com/github/spec-kit), designed specifically for Claude Code's SubAgent concurrent execution capabilities.

### Key Features

- **7-Step Standard Workflow**: `init → specify → clarify → plan → apply → checklist → archive`
- **SubAgent Concurrent Execution**: Up to 10 SubAgents in parallel during apply phase (Claude Code only)
- **Multi-AI Tool Support**: Command integration for 17+ AI tools (Claude, Cursor, Gemini, Copilot, etc.)
- **Delta Change Tracking**: ADDED / MODIFIED / REMOVED / RENAMED format
- **Scoring Acceptance**: Checklist score ≥80 to pass, otherwise returns to apply
- **Quick Mode**: `quick-delta` for one-step change recording

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) to be installed first.

```bash
# Option 1: One-shot execution (recommended)
uvx --from git+https://github.com/Waasaabii/cc-spec.git cc-spec init

# Option 2: Global installation
uv tool install cc-spec --from git+https://github.com/Waasaabii/cc-spec.git

# Upgrade to latest version
uv tool install cc-spec --force --from git+https://github.com/Waasaabii/cc-spec.git
```

---

## Quick Start

```bash
# 1. Initialize project (select AI tools to support)
cc-spec init --ai claude,cursor

# 2. Create change specification
cc-spec specify add-user-auth

# 3. Clarify requirements
cc-spec clarify

# 4. Generate execution plan
cc-spec plan

# 5. Execute tasks (SubAgent concurrent, Claude Code only)
cc-spec apply

# 6. Acceptance scoring
cc-spec checklist

# 7. Archive changes
cc-spec archive
```

### Quick Mode

```bash
# Small changes, hotfixes: one-step recording
cc-spec quick-delta "Fix login page styling issue"
```

---

## Using in AI Tools

cc-spec init generates command files for selected AI tools, allowing users to invoke commands directly in each tool's input box:

| Tool | Invocation | Example |
|------|------------|---------|
| Claude Code | `/cc-spec:specify` | `/cc-spec:specify add-oauth` |
| Cursor | `/cc-spec-specify` | `/cc-spec-specify add-oauth` |
| Gemini CLI | `/cc-spec:specify` | `/cc-spec:specify add-oauth` |
| GitHub Copilot | Prompt library | Select "cc-spec-specify" |
| Amazon Q | `@cc-spec-specify` | `@cc-spec-specify add-oauth` |
| Other tools | Natural language | "Help me run cc-spec specify" |

---

## Workflow Design Origins

cc-spec integrates design elements from the following projects:

| Source | Contribution |
|--------|--------------|
| **[OpenSpec](https://github.com/hannesrudolph/openspec)** | Delta change tracking, archive workflow, multi-AI tool configuration, AGENTS.md standard |
| **[Spec-Kit](https://github.com/github/spec-kit)** | CLI tech stack (uv + typer + rich), template system, clarify workflow, scoring mechanism |
| **auto-dev** | SubAgent concurrent execution, Wave task planning format |

### Template Sources

Templates used in cc-spec are based on OpenSpec and Spec-Kit template designs:

- **Spec Template (spec-template.md)**: Based on Spec-Kit's User Story + Given/When/Then format
- **Plan Template (plan-template.md)**: Based on Spec-Kit's Phase-based design
- **Tasks Template (tasks-template.md)**: Based on auto-dev's Wave/Task-ID format
- **Delta Format**: Based on OpenSpec's ADDED/MODIFIED/REMOVED/RENAMED specification
- **Command Files**: Based on OpenSpec's multi-tool adapter pattern

---

## Documentation

For detailed design documentation, see [docs/plan/cc-spec/](./plan/cc-spec/README.md).

---

## Acknowledgements

This project is heavily influenced by and based on the work and research of **[John Lam](https://github.com/jflam)**.

Special thanks to:

- **[OpenSpec](https://github.com/hannesrudolph/openspec)** - A spec-driven development framework created by Hannes Rudolph, providing excellent Delta change tracking and multi-tool support design
- **[Spec-Kit](https://github.com/github/spec-kit)** - A spec-driven development toolkit created by the GitHub team (Den Delimarsky, John Lam, and others), providing a mature CLI framework and template system

---

## License

MIT License
