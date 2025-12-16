# CC-SPEC V0.1.5 - Codex Integration

## 1. 概述

### 1.1 核心改动

v0.1.5 版本的核心改动是将 SubAgentExecutor 的**模拟执行**替换为**真实调用 Codex CLI**。

| 版本 | SubAgent 执行方式 |
|------|-------------------|
| v0.1.4 | 模拟执行（80% 随机成功） |
| v0.1.5 | 真实调用 Codex CLI |

### 1.2 设计哲学

**分工协作模式**：Claude Code 负责编排思考，Codex 负责执行干活。

- **Claude Code**：纯编排层，不产出任何文件
- **Codex**：执行层，按照 cc-spec 规范产出所有文件

用户只需安装 Claude Code 和 Codex CLI 即可完成整个开发流程。

---

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户                                  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Claude Code (cc-spec)                       │
│                                                          │
│  职责：                                                  │
│  ├─ 需求澄清 (clarify)                                  │
│  ├─ 任务规划 (plan)                                     │
│  ├─ 任务分解 (Wave 编排)                                │
│  ├─ 调度执行 (调用 Codex)                               │
│  ├─ 结果验证 (覆盖率检查)                               │
│  └─ 流程控制 (重试、降级)                               │
│                                                          │
│  不做：                                                  │
│  ├─ 不写代码                                            │
│  ├─ 不写测试                                            │
│  └─ 不写文档                                            │
└─────────────────────────┬───────────────────────────────┘
                          │ subprocess 调用
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Codex CLI                             │
│                                                          │
│  职责（按 cc-spec 规范产出）：                           │
│  ├─ 写 dev-plan.md                                      │
│  ├─ 写代码文件                                          │
│  ├─ 写测试文件                                          │
│  ├─ 写文档                                              │
│  └─ 执行任何实际产出工作                                │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    产出物                                │
│  (符合 cc-spec 规范的文件)                              │
└─────────────────────────────────────────────────────────┘
```

### 2.2 调用流程

```
cc-spec 7步工作流
    │
    ├─ init      → Claude Code 初始化项目结构
    ├─ specify   → Codex 生成需求文档
    ├─ clarify   → Claude Code 澄清需求
    ├─ plan      → Codex 生成开发计划
    ├─ apply     → Codex 执行开发任务 (Wave 并行)
    ├─ checklist → Claude Code 验证结果
    └─ archive   → Codex 生成归档文档
```

---

## 3. 实现计划

### Phase 1: 移植 Codex 调用能力

**目标**：从 myclaude/codeagent-wrapper 提取核心调用逻辑，用 Python 实现。

**任务清单**：

- [ ] 创建 `src/cc_spec/codex/` 模块
- [ ] 实现 `CodexClient` 类
  - [ ] `execute(task: str, workdir: str) -> CodexResult`
  - [ ] `resume(session_id: str, task: str) -> CodexResult`
- [ ] 实现命令构建
  - [ ] 构建 `codex e --skip-git-repo-check -C {workdir} --json -` 命令
  - [ ] stdin 输入任务内容
- [ ] 实现输出解析
  - [ ] 解析 JSON stream 输出
  - [ ] 提取 message 和 SESSION_ID
- [ ] 实现超时控制
  - [ ] 默认 2 小时超时
  - [ ] 支持环境变量 `CODEX_TIMEOUT` 覆盖

**参考文件**：
- `reference/myclaude/codeagent-wrapper/executor.go` - 执行逻辑
- `reference/myclaude/codeagent-wrapper/backend.go` - 后端定义
- `reference/myclaude/codeagent-wrapper/parser.go` - 输出解析

### Phase 2: 集成到 SubAgentExecutor

**目标**：将 CodexClient 集成到现有的 SubAgentExecutor。

**任务清单**：

- [ ] 修改 `SubAgentExecutor.execute_task()`
  - [ ] 删除模拟执行逻辑
  - [ ] 调用 `CodexClient.execute()`
- [ ] 任务格式转换
  - [ ] cc-spec Task → Codex 输入格式
- [ ] 结果处理
  - [ ] CodexResult → cc-spec TaskResult
  - [ ] 保存 SESSION_ID 用于 resume
- [ ] 错误处理
  - [ ] Codex CLI 不存在时的提示
  - [ ] 执行失败时的重试策略

### Phase 3: 端到端验证

**目标**：验证完整流程可用。

**任务清单**：

- [ ] 单任务执行测试
- [ ] Wave 并行执行测试
- [ ] 错误恢复测试
- [ ] 覆盖率验证测试

---

## 4. 技术细节

### 4.1 Codex CLI 调用命令

**单任务模式**：
```bash
codex e --skip-git-repo-check -C {workdir} --json - <<'EOF'
{task_content}
EOF
```

**Resume 模式**：
```bash
codex e --skip-git-repo-check --json resume {session_id} - <<'EOF'
{follow_up_task}
EOF
```

### 4.2 任务输入格式

cc-spec 任务需转换为以下格式传给 Codex：

```
Task: {task_id}
Reference: @{spec_file_path}
Scope: {file_scope}
Test: {test_command}
Deliverables: code + unit tests + coverage ≥{coverage_threshold}%

---
{task_description}
```

### 4.3 输出解析

Codex 输出 JSON stream，需要解析：

```python
@dataclass
class CodexResult:
    success: bool
    message: str          # agent 输出内容
    session_id: str       # 用于 resume
    exit_code: int
    error: Optional[str]
```

**SESSION_ID 格式**：`019a7247-ac9d-71f3-89e2-a823dbd8fd14`

### 4.4 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CODEX_TIMEOUT` | 7200000 (2h) | 执行超时时间（毫秒） |

---

## 5. 依赖要求

### 5.1 系统依赖

| 工具 | 用途 | 安装方式 |
|------|------|----------|
| Claude Code | 编排层 | `npm install -g @anthropic-ai/claude-code` |
| Codex CLI | 执行层 | `npm install -g @openai/codex` |

### 5.2 验证安装

```bash
# 验证 Claude Code
claude --version

# 验证 Codex
codex --version
```

---

## 6. 文件变更清单

```
src/cc_spec/
├── codex/                    # 新增
│   ├── __init__.py
│   ├── client.py            # CodexClient 实现
│   ├── parser.py            # JSON stream 解析
│   └── models.py            # CodexResult 等数据模型
└── subagent/
    └── executor.py          # 修改：集成 CodexClient
```

---

## 7. 里程碑

| Phase | 目标 | 状态 |
|-------|------|------|
| Phase 1 | Codex 调用能力 | 待开始 |
| Phase 2 | SubAgent 集成 | 待开始 |
| Phase 3 | 端到端验证 | 待开始 |

---

*文档版本：v0.1.5-draft*
*创建日期：2025-12-16*
