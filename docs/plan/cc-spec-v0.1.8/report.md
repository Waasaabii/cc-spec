# cc-spec v0.1.8 Task Reports

## T01 DOCS-SCOPE (2025-12-21T01:53:07)
- Clarified docs/plan as human-only docs and template_mapping as implementation guidance in base-template.
- Added README section explaining SKILL.md/AGENTS outputs and non-runtime docs.
- Files: docs/plan/cc-spec-v0.1.8/base-template.yaml, README.md

## T02 AGENTS-GUIDE (2025-12-21T02:00:52)
- Updated init quick-start guidance to list the full 8-step workflow (including KB/checklist/archive).
- Files: src/cc_spec/commands/init.py

## T05 KB-CONFIG-WIRING (2025-12-21T01:01:42)
- Wired kb init/update to load chunking/retrieval config (with CLI override for strategy).
- Passed chunking config into pipeline to align Codex fallback/LLM limits with config.
- Expanded kb init/update outputs to include strategy + concise config summary (JSON + console).
- Files: src/cc_spec/commands/kb.py, src/cc_spec/rag/pipeline.py

## T05B WORKFLOW-KB-SYNC (2025-12-21T01:14:03)
- Added post-task KB sync helper honoring config (smart/full/skip) with git-change gating.
- apply: wave-level sync now respects config; strict-mode updates still force per-task sync.
- archive: KB sync now respects config; added config load warnings on failure.
- Files: src/cc_spec/rag/workflow.py, src/cc_spec/commands/apply.py, src/cc_spec/commands/archive.py

## T05C PROGRESS-REPORTING (2025-12-21T01:24:51)
- Added progress.yaml writer with v1.3 fields and non-blocking error handling.
- apply now updates docs/plan/<change>/progress.yaml per task completion.
- Files: src/cc_spec/commands/apply.py, src/cc_spec/subagent/result_collector.py, src/cc_spec/subagent/task_parser.py

## T06 SMART-CHUNKER (2025-12-21T01:29:00)
- Added line fallback for AST failures and unsupported extensions.
- SmartChunker now respects reference_mode and LLM limits.
- Added tree-sitter-language-pack dependency; provided SmartChunker factory in chunker module.
- Files: src/cc_spec/rag/ast_chunker.py, src/cc_spec/rag/smart_chunker.py, src/cc_spec/rag/chunker.py, pyproject.toml

## T07 PIPELINE-SELECTOR (2025-12-21T01:45:12)
- Pipeline now selects SmartChunker vs Codex based on config strategy and records per-strategy counts.
- KB manifest now records chunking strategy/version metadata on init/update.
- KB init/update outputs include AST/Line/LLM stats.
- Files: src/cc_spec/rag/pipeline.py, src/cc_spec/rag/knowledge_base.py, src/cc_spec/rag/smart_chunker.py, src/cc_spec/commands/kb.py

## T08 TESTS-DOCS (2025-12-21T01:49:58)
- Added SmartChunker strategy tests and KB config roundtrip tests; updated default version expectations.
- README updated to 8-step flow and Smart Chunking mention.
- Files: tests/rag/test_smart_chunking.py, tests/core/test_config.py, tests/test_config.py, tests/test_cmd_init.py, tests/test_cmd_goto.py, README.md
