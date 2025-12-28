# cc-spec

**Spec-Driven AI-Assisted Development Workflow Tool**

English | [中文](../README.md)

[![Version](https://img.shields.io/badge/version-0.2.2-blue.svg)](https://github.com/Waasaabii/cc-spec)

---

## Introduction

cc-spec is a spec-driven development tool designed for a **Claude Code orchestration + Codex execution** workflow.

The project consists of two main modules:

| Module | Path | Tech Stack | Description |
|--------|------|------------|-------------|
| **CLI Tool** | `src/cc_spec/` | Python (uv + Typer + Rich) | Command-line workflow tool |
| **Desktop App** | `apps/cc-spec-tool/` | Tauri + React + Rust | GUI visualization & session management |

### Key Features

- **8-Step Workflow**: `init → init-index/update-index → specify → clarify → plan → apply → accept → archive`
- **SubAgent Concurrent Execution**: Up to 10 SubAgents in parallel during apply phase (Claude Code only)
- **Multi-AI Tool Support**: Command integration for 17+ AI tools (Claude, Cursor, Gemini, Copilot, etc.)
- **Delta Change Tracking**: ADDED / MODIFIED / REMOVED / RENAMED format
- **End-to-End Acceptance**: `accept` stage runs lint/test/build/type-check and generates a report
- **Quick Mode**: `quick-delta` for one-step small changes

---

## Desktop App (cc-spec-tool)

`apps/cc-spec-tool/` is a desktop GUI application built with Tauri, providing a visual interface for managing Codex/Claude sessions.

### Features

- **Project Management**: Import, switch, and remove projects
- **Codex Session Management**: Terminal relay mode with session monitoring and auto-retry
- **Claude Integration**: Start and manage Claude CLI sessions
- **Task Scheduling**: Concurrency control and queue management
- **Real-time Status**: SSE event stream + sessions.json dual-track synchronization

### Development

```bash
cd apps/cc-spec-tool

# Install dependencies
bun install

# Development mode
bun run tauri dev

# Build release
bun run tauri build

# Build Sidecar (package cc-spec CLI)
pwsh scripts/build-sidecar.ps1
```

---

## CLI Tool Installation

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
# 1. Initialize project
cc-spec init

# 2. (Recommended) initialize project index (L1 + L2)
cc-spec init-index --level l1 --level l2
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

# 7. End-to-end acceptance
cc-spec accept

# 8. Archive changes
cc-spec archive
```

### Quick Mode

```bash
# Small changes, hotfixes: one-step recording
cc-spec quick-delta "Fix login page styling issue"
```

Notes:
- quick-delta simplifies docs, but you should still run `cc-spec accept` for basic validation.

---

## Workflow (Detailed)

> Core principle: **Claude orchestrates/reviews, Codex implements**.

| Step | Purpose | Command | Key Output |
|------|---------|---------|-----------|
| 1. init | Project setup & config | `cc-spec init` | `.cc-spec/`, `config.yaml`, AI tool commands |
| 2. init-index/update-index | Build/update index (recommended) | `cc-spec init-index` / `cc-spec update-index` | `PROJECT_INDEX.md`, `FOLDER_INDEX.md`, `.cc-spec/index/status.json` |
| 3. specify | Define scope & success criteria | `cc-spec specify <change>` | `.cc-spec/changes/<change>/proposal.md` |
| 4. clarify | Resolve ambiguity or mark rework | `cc-spec clarify [task-id]` | Rework markers / detect output |
| 5. plan | Generate executable plan | `cc-spec plan` | `.cc-spec/changes/<change>/tasks.yaml` |
| 6. apply | Run tasks concurrently | `cc-spec apply` | Task status updates & execution records |
| 7. accept | End-to-end validation | `cc-spec accept` | `acceptance.md`, `acceptance-report.md` |
| 8. archive | Archive the change | `cc-spec archive` | `.cc-spec/archive/...` |

---

## Testing

Layered runs (integration is opt-in):

```bash
pytest -m unit
pytest -m cli
pytest -m codex
```

Integration tests (explicit only):

```bash
pytest -m integration
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

## Documentation

- CLI docs: `docs/cc-spec/README.md`
- Commands: `docs/cc-spec/commands.md`
- Workflow: `docs/cc-spec/workflow.md`
