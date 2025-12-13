# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

cc-spec 是一个规范驱动的 AI 辅助开发工作流 CLI 工具，整合了 OpenSpec 和 Spec-Kit 的设计精华。提供 7 步标准工作流，支持 SubAgent 并发执行（Claude Code 中最多 10 个并发）。

## 开发命令

```bash
# 安装依赖（使用 uv）
uv sync
uv sync --dev  # 包含开发依赖

# 运行 CLI
uv run cc-spec --help
uv run cc-spec <command>

# 运行测试
uv run pytest                           # 全部测试
uv run pytest tests/test_config.py      # 单个文件
uv run pytest -k "test_name"            # 按名称运行单个测试
uv run pytest tests/integration/        # 仅集成测试

# 代码检查
uv run ruff check src/                  # lint 检查
uv run ruff check --fix src/            # lint 自动修复
uv run mypy src/cc_spec/                # 类型检查
```

## 架构

### 源码结构 (`src/cc_spec/`)

- **`__init__.py`** - Typer CLI 应用入口，注册所有命令
- **`commands/`** - 命令实现（init, specify, clarify, plan, apply, checklist, archive, quick-delta, list, goto, update）
- **`core/`** - 核心业务逻辑：
  - `config.py` - 配置管理（Config, SubAgentProfile, AgentsConfig 数据类）
  - `state.py` - 工作流状态持久化
  - `delta.py` - Delta 变更追踪（ADDED/MODIFIED/REMOVED/RENAMED）
  - `scoring.py` - 检查清单打分（≥80 分通过）
  - `id_manager.py` - ID 系统（C-001, S-001, A-001 格式）
  - `templates.py` - 模板加载
  - `command_generator.py` - AI 工具命令文件生成
- **`subagent/`** - SubAgent 执行系统：
  - `executor.py` - 并行任务执行
  - `task_parser.py` - Wave/Task-ID 格式解析
  - `result_collector.py` - 执行结果聚合
- **`ui/`** - Rich 控制台 UI 组件（display, prompts, progress）
- **`utils/`** - 工具函数（files, download）
- **`templates/`** - 内置模板文件

### 工作流数据 (`/.cc-spec/`)

```
.cc-spec/
├── config.yaml           # 项目配置
├── changes/              # 活跃变更（C-xxx ID）
│   └── <change-name>/
│       ├── proposal.md   # 变更提案
│       ├── plan.md       # 执行计划
│       └── tasks.md      # Wave/Task 定义
└── archive/              # 已完成变更（A-xxx ID）
```

### 多 AI 工具支持

工具为 17+ AI 工具（Claude, Cursor, Gemini, Copilot 等）生成命令文件。配置在 `config.yaml` 的 `agents.enabled[]` 中。

## 关键约定

- 所有命令使用 Typer + Rich 构建 CLI 界面
- 配置文件格式为 YAML，支持版本迁移（v1.0 → v1.2）
- Delta 格式：`ADDED:`、`MODIFIED:`、`REMOVED:`、`RENAMED: old → new`
- 任务 ID 遵循 `W<wave>-T<task>` 格式（如 W1-T1, W2-T3）
- 检查清单通过阈值：80 分（可配置）
