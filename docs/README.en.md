# cc-spec

**Spec-Driven AI-Assisted Development Workflow CLI Tool**

English | [中文](../README.md)

---

## Introduction

cc-spec is a spec-driven development CLI tool that combines the best of [OpenSpec](https://github.com/hannesrudolph/openspec) and [Spec-Kit](https://github.com/github/spec-kit), designed specifically for Claude Code's SubAgent concurrent execution capabilities.

### Key Features

- **8-Step Standard Workflow**: `init → kb init/update → specify → clarify → plan → apply → checklist → archive`
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

# 2. (Recommended) build/update KB
cc-spec kb init
# or in Claude Code:
# /cc-spec:init

# 3. Create change specification
cc-spec specify add-user-auth

# 4. Clarify requirements or rework tasks
cc-spec clarify

# 5. Generate execution plan
cc-spec plan

# 6. Execute tasks (SubAgent concurrent, Claude Code only)
cc-spec apply

# 7. Acceptance scoring
cc-spec checklist

# 8. Archive changes
cc-spec archive
```

### Quick Mode

```bash
# Small changes, hotfixes: one-step recording
cc-spec quick-delta "Fix login page styling issue"
```

Notes:
- quick-delta only simplifies docs; the system still writes KB records
- Minimum info set: Why / What / Impact / Success Criteria

---

## Workflow (Detailed)

> Core principle: **Claude orchestrates/reviews, Codex implements**; KB bridges context.

| Step | Purpose | Command | Key Output |
|------|---------|---------|-----------|
| 1. init | Project setup & config | `cc-spec init` | `.cc-spec/`, `config.yaml` |
| 2. kb init/update | Build/update KB (recommended) | `cc-spec kb init` / `cc-spec kb update` | `.cc-spec/vectordb/`, workflow records |
| 3. specify | Define scope & success criteria | `cc-spec specify <change>` | `.cc-spec/changes/<change>/proposal.md` |
| 4. clarify | Resolve ambiguity or mark rework | `cc-spec clarify [task-id]` | Clarifications / rework markers |
| 5. plan | Generate executable plan | `cc-spec plan` | `.cc-spec/changes/<change>/tasks.yaml` |
| 6. apply | Run tasks concurrently | `cc-spec apply` | Task status updates & execution records |
| 7. checklist | Acceptance scoring (default ≥80) | `cc-spec checklist` | KB checklist record (optional checklist-result.md with --write-report) |
| 8. archive | Merge Delta specs & archive | `cc-spec archive` | `.cc-spec/changes/archive/...` |

### Step Notes

- **init**: Prepares local structure only (no KB write).
- **kb init/update**: Use `kb preview` before indexing if needed.
- **specify**: Capture Why / What Changes / Impact / Success Criteria (avoid implementation details).
- **clarify**: Ask high-impact questions and write back to proposal; or mark tasks for rework.
- **plan**: Outputs `tasks.yaml` (Gate-0 + Wave, deps, checklist).
- **apply**: Runs Wave-by-Wave; retry failures with `--resume`.
- **checklist**: Weighted scoring across Functionality/Quality/Tests/Docs; default writes to KB, use `--write-report` for `checklist-result.md`.
- **archive**: Merges Delta specs into main specs and archives the change.

### Human vs System KB Flow

| Human Step | System KB Action (must run) |
|---|---|
| init | Create project structure; mark KB pending if not built |
| kb init/update | Build/update code chunks and workflow records |
| specify | `kb record`: Why/What/Impact/Success Criteria |
| clarify | `kb record`: rework reasons, ambiguity findings, requirement clarifications |
| plan | `kb record`: task breakdown summary, dependencies, acceptance points |
| apply | `kb record`: execution context + change summary; `kb update` to ingest changes |
| checklist | `kb record`: score, failed items, recommendations |
| archive | `kb update/compact`: ensure KB is current before archive |

> Review baseline is **KB records**; proposal/tasks are for human reading only.

## Testing

Layered runs (integration is opt-in):

```bash
pytest -m unit
pytest -m cli
pytest -m rag
pytest -m codex
```

Integration tests (explicit only):

```bash
pytest -m integration
```

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
