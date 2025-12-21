# cc-spec v0.1.8 迁移上下文（handoff）

更新时间：2025-12-20T23:49:01

## 关键共识
- docs/plan/ 仅供人阅读，不作为运行时配置来源。
- SKILL.md / AGENTS.md 是 CLI/Agent 的规范产物，运行时模板内置（不读 docs/plan）。
- references.copy_files 只是实现指导，不是强约束。
- Smart Chunking 默认 strategy=ast-only（可切换 smart/codex-only）。
- outputs/forbidden 必须生成到 SKILL.md / AGENTS.md。
- 任务完成需更新 progress.yaml（结构对齐 status.yaml v1.3）。
- KB 同步：post_task_sync 支持 smart/full/skip，且 apply/archive 要遵守。

## 已完成/已落地（代码层）
- 新增内置模板与渲染器：
  - `src/cc_spec/core/standards_templates.py`
  - `src/cc_spec/core/standards_renderer.py`
- init 生成规范产物（托管区块）：
  - `src/cc_spec/commands/init.py`
  - 生成 `AGENTS.md` 与 `.claude/skills/cc-spec-standards/SKILL.md`
- KB 配置已写入 config（默认 ast-only）：
  - `src/cc_spec/core/config.py`
  - 新增 `kb.chunking/update/retrieval` 数据结构
- Smart Chunking 代码已引入（尚未接入 pipeline）：
  - `src/cc_spec/rag/ast_utils.py`
  - `src/cc_spec/rag/ast_chunker.py`
  - `src/cc_spec/rag/smart_chunker.py`
- pipeline 统计字段扩展：
  - `src/cc_spec/rag/models.py`（ChunkResult.strategy）
  - `src/cc_spec/rag/pipeline.py`（KBUpdateSummary: chunking_ast/line/llm）
- 版本常量补齐：
  - `src/cc_spec/version.py`（TEMPLATE_VERSION=1.0.8）
  - `src/cc_spec/__init__.py`（--version 输出 template/config/kb）
- 修复了 `src/cc_spec/rag/chunker.py` 中 reference 分支缩进错误。

## 已完成/已落地（计划文档）
- `docs/plan/cc-spec-v0.1.8/tasks.yaml` 已补充关键约束
- `docs/plan/cc-spec-v0.1.8/progress.yaml` 已记录进度

## 当前进度（progress.yaml）
- T02/T02B/T02C 已完成
- T03 已完成（版本输出）
- T04 已完成（KB config）
- T06 标记为 in_progress（Smart Chunker 仅代码未接入 pipeline）
- 其余 T05/T05B/T05C/T07/T08 未完成

## 待办关键点（接下来必须做）
1) **Pipeline 接入 SmartChunker + 统计**
   - `src/cc_spec/rag/pipeline.py` 当前仍用 `CodexChunker`。
   - 需要根据 `config.kb.chunking` 选择 `SmartChunker` 或 `CodexChunker`。
   - 统计 `chunking_ast/line/llm`，并在 manifest 写入策略与版本。

2) **KB 命令读取 config**
   - `src/cc_spec/commands/kb.py` 需读取 `config.kb.chunking/retrieval` 作为默认值。
   - CLI 参数仍可覆盖 config。
   - 输出中展示策略与关键配置摘要。

3) **workflow KB sync（apply/archive）**
   - 读取 `config.kb.update.post_task_sync`
   - smart: 有变更时增量 update
   - full: 走 init_kb
   - skip: 不自动同步
   - 需要在 `apply.py`/`archive.py`/`rag/workflow.py` 里实现

4) **progress.yaml 记录**
   - 在任务完成时写 `docs/plan/cc-spec-v0.1.8/progress.yaml`
   - schema 对齐 status.yaml v1.3：id/status/agent_id/started_at/completed_at/retry_count
   - 可选 changed_files / notes
   - 写入失败不阻断主流程

5) **依赖与测试**
   - `pyproject.toml` 增加 `tree-sitter-language-pack`
   - 新增 tests:
     - `tests/rag/test_smart_chunking.py`
     - `tests/core/test_config.py`（更新默认 version=1.4 + kb config）
   - README 更新 v0.1.8、8 步流程（包含 kb init/update）与 Smart Chunking 参考

## 重要文件索引
- 规范模板（运行时内置）：`src/cc_spec/core/standards_templates.py`
- 模板渲染器：`src/cc_spec/core/standards_renderer.py`
- KB config：`src/cc_spec/core/config.py`
- Smart Chunker：`src/cc_spec/rag/smart_chunker.py`
- pipeline：`src/cc_spec/rag/pipeline.py`
- KB 命令：`src/cc_spec/commands/kb.py`
- workflow helpers：`src/cc_spec/rag/workflow.py`
- apply/archive：`src/cc_spec/commands/apply.py`, `src/cc_spec/commands/archive.py`
