# CC-SPEC V0.1.5 - Codex Integration + RAG

## 1. 概述

### 1.1 核心改动

v0.1.5 版本有两个核心改动：

| 改动 | v0.1.4 | v0.1.5 |
|------|--------|--------|
| SubAgent 执行 | 模拟执行（80% 随机成功） | **真实调用 Codex CLI** |
| 上下文管理 | 每次读大量文档 | **RAG 向量检索** |

**核心理念**：
- **RAG 是主角**：上下文通过向量检索获取，精准高效
- **文档是配角**：只记录变更，不作为上下文来源

### 1.2 设计哲学

**分工协作模式**：Claude Code 负责编排思考，Codex 负责执行干活。

- **Claude Code**：纯编排层，不产出任何文件
- **Codex**：执行层，按照 cc-spec 规范产出所有文件

用户只需安装 Claude Code 和 Codex CLI 即可完成整个开发流程。

### 1.3 方案选型：Python 核心 + Codex 执行

**问题**：如何保证每次产出符合 cc-spec 规范？

**选择方案 B**：保留 cc-spec Python 核心，只改执行层。

```
┌─────────────────────────────────────────────────────────┐
│              cc-spec Python 核心（保留）                 │
│                                                          │
│  ├─ 规范定义 (schema)      → 定义文档结构标准            │
│  ├─ 模板管理 (templates)   → 提供标准模板                │
│  ├─ 验证逻辑 (validation)  → 检查产出是否合规            │
│  ├─ 进度追踪 (tracking)    → Wave/Task 状态管理          │
│  └─ 评分系统 (scoring)     → 4维度质量评估               │
│                                                          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              SubAgentExecutor（修改）                    │
│                                                          │
│  v0.1.4: 模拟执行 (80% 随机成功)                        │
│                    ↓                                     │
│  v0.1.5: 调用 Codex CLI (真实执行)                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**为什么选方案 B**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 纯 Command | 轻量 | 无法强制规范，产出不稳定 |
| **B: Python + Codex** | **强制规范、可验证** | 需保留 Python 代码 |
| C: Command + Hooks | 中等 | 验证逻辑分散 |

**方案 B 的验证流程**：

```
Python 生成标准化 prompt（含规范要求）
    ↓
调用 Codex 执行
    ↓
Python 验证产出是否符合规范
    ↓
├─ 符合 → 继续下一步
└─ 不符合 → 重试/报错
```

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

### 2.3 Claude Code 能力使用

cc-spec 利用 Claude Code 原生能力进行编排：

| Claude Code 能力 | cc-spec 用途 | 阶段 |
|------------------|--------------|------|
| **AskUserQuestion** | 澄清需求、确认方案 | clarify |
| **Bash** | 调用 Codex CLI | specify, plan, apply, archive |
| **Read** | 读取文件验证结果 | checklist |
| **Glob/Grep** | 搜索文件、验证产出 | checklist |
| **TodoWrite** | 任务管理、进度追踪 | 全流程 |

**不使用的能力**（产出交给 Codex）：

| 能力 | 原因 |
|------|------|
| Write | 所有文件产出由 Codex 完成 |
| Edit | 所有文件修改由 Codex 完成 |

### 2.4 执行流程详解

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: init                                                     │
│   cc-spec Python 初始化项目结构                                  │
│   创建 .cc-spec/ 目录和配置文件                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: specify                                                  │
│   Python 生成 prompt (含模板规范)                                │
│       ↓                                                          │
│   Bash(codex ...) 生成需求文档                                   │
│       ↓                                                          │
│   Python 验证文档格式                                            │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: clarify                                                  │
│   AskUserQuestion 澄清需求                                       │
│   2-3轮问答直到需求清晰                                          │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: plan                                                     │
│   Python 生成 prompt (含任务模板)                                │
│       ↓                                                          │
│   Bash(codex ...) 生成开发计划 dev-plan.md                       │
│       ↓                                                          │
│   Python 验证计划格式，提取 Task 列表                            │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: apply                                                    │
│   Python 编排 Wave 并行执行                                      │
│       ↓                                                          │
│   对每个 Task: Bash(codex ...) 执行开发                          │
│       ↓                                                          │
│   Python 收集结果，处理依赖                                      │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: checklist                                                │
│   Bash(pytest ...) 运行测试                                      │
│   Read/Grep 验证文件产出                                         │
│   Python 4维度评分                                               │
│       ↓                                                          │
│   覆盖率 <90%? → 重试 apply (最多2轮)                            │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: archive                                                  │
│   Python 生成 prompt (含归档模板)                                │
│       ↓                                                          │
│   Bash(codex ...) 生成归档文档                                   │
│       ↓                                                          │
│   Python 验证并移动到 archive/                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. RAG 知识库设计

### 3.1 设计目标

**减少上下文 Token 消耗**：

```
传统方式：
├─ 读完整 spec.md (1000+ tokens)
├─ 读完整 dev-plan.md (500+ tokens)
├─ 读相关代码文件 (2000+ tokens)
└─ 总计: 3500+ tokens

RAG 方式：
├─ 向量检索相关片段 (500 tokens)
└─ 总计: 500 tokens

节省 85%+
```

### 3.2 两阶段 init

**阶段 1：终端 `cc-spec init`（准备工作）**

```bash
$ cc-spec init

固定流程（无选项）：
├─ 创建 .cc-spec/ 目录
├─ 创建 config.yaml（配置）
├─ 创建模板文件
└─ 创建 changelog.md

不做：
├─ 不扫描代码
├─ 不调用 AI
└─ 不写向量数据库
```

**定位**：纯本地准备工作，不涉及任何 AI 调用。

**阶段 2：Claude Code 内 `/cc-spec init`（知识库构建）**

```
Claude Code 内执行：
> /cc-spec init

执行：
├─ 扫描项目代码、文档、配置
├─ 调用 Codex 切片 + 生成摘要
├─ Claude Code 存入向量数据库
├─ 加载规范存入向量数据库
└─ 大模型现在"理解"了项目

可重复执行（更新知识库）：
├─ 代码大改后 → /cc-spec init
└─ 新增模块后 → /cc-spec init
```

**定位**：需要 AI 参与的知识库构建工作。

### 3.3 知识库存储内容

```
.cc-spec/vectordb/
├─ 代码片段（Codex 切片）
├─ 文档片段（Codex 切片）
└─ 规范片段（cc-spec 规范）
```

| 类型 | 来源 | 示例 |
|------|------|------|
| 代码 | 项目 src/ | 函数、类、模块 |
| 文档 | 项目 docs/ | 设计文档、README |
| 规范 | cc-spec | 模板格式、验证规则、覆盖率要求 |

### 3.4 切片流程（Codex 执行）

```
┌─────────────────────────────────────────────────────────┐
│ Claude Code 扫描文件列表                                 │
│   files = ["src/auth.py", "src/user.py", ...]          │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────┐
│ 调用 Codex 切片                                          │
│                                                          │
│   Prompt: "把这个文件切成有意义的片段，返回 JSON"        │
│                                                          │
│   Codex 返回:                                            │
│   [                                                      │
│     {                                                    │
│       "id": "auth_login",                               │
│       "type": "function",                               │
│       "summary": "用户登录验证，检查密码并生成JWT",      │
│       "content": "def login(email, password): ..."      │
│     },                                                   │
│     ...                                                  │
│   ]                                                      │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────┐
│ Claude Code 存入向量数据库                               │
│   vectordb.add(chunks)                                  │
└─────────────────────────────────────────────────────────┘
```

**Codex 切片的优势**：
- 理解代码语义，切分更合理
- 自动生成摘要，检索更精准
- 标记类型（function/class/config），方便过滤
- 无需 AST 解析，支持任意语言

### 3.5 检索流程

```
┌─────────────────────────────────────────────────────────┐
│ 用户需求: "给登录功能加上记住我"                         │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────┐
│ Claude Code 向量检索                                     │
│                                                          │
│   results = vectordb.query(                             │
│     query="登录 记住我",                                │
│     n_results=5,                                        │
│     where={"type": {"$in": ["code", "spec"]}}          │
│   )                                                      │
│                                                          │
│   返回:                                                  │
│   ├─ auth_login (代码): 用户登录验证函数                │
│   ├─ jwt_util (代码): JWT Token 生成                    │
│   ├─ spec_task_format (规范): Task 格式要求             │
│   └─ spec_coverage (规范): 覆盖率 ≥90%                  │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────┐
│ 构建 Codex Prompt                                        │
│                                                          │
│   "需求：给登录功能加上记住我                            │
│                                                          │
│    相关代码：                                            │
│    [检索到的代码片段]                                    │
│                                                          │
│    规范要求：                                            │
│    [检索到的规范片段]                                    │
│                                                          │
│    请实现..."                                            │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────┐
│ 调用 Codex 执行                                          │
└─────────────────────────────────────────────────────────┘
```

### 3.6 向量库更新（Claude Code 执行）

**更新时机**：
- `/cc-spec init`：全量更新
- `apply` 完成后：增量更新变更的文件

**增量更新流程**：
```
Codex 完成任务
    ↓
Claude Code 检测变更的文件
    ↓
对变更文件调用 Codex 重新切片
    ↓
Claude Code 更新向量库（删除旧片段，添加新片段）
    ↓
追加 changelog.md 变更记录
```

### 3.7 存储结构

```
.cc-spec/
├── vectordb/              # 向量数据库（项目级）
│   ├── chroma.sqlite3     # ChromaDB 数据
│   └── ...
├── config.yaml            # 配置
├── changelog.md           # 变更记录（给人看）
└── templates/             # 模板
```

### 3.8 向量数据库选型

使用 **ChromaDB**（项目级，无需服务）：

```python
import chromadb

# 项目级存储
client = chromadb.PersistentClient(path=".cc-spec/vectordb")
collection = client.get_or_create_collection("knowledge")

# 存储
collection.add(
    documents=["代码内容...", "规范内容..."],
    metadatas=[{"type": "code"}, {"type": "spec"}],
    ids=["chunk_1", "chunk_2"]
)

# 检索
results = collection.query(
    query_texts=["登录功能"],
    n_results=5
)
```

---

## 4. 实现计划

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

### Phase 3: RAG 知识库集成

**目标**：实现向量数据库存储和检索。

**任务清单**：

- [ ] 创建 `src/cc_spec/rag/` 模块
- [ ] 实现 `KnowledgeBase` 类
  - [ ] `init_vectordb()` 初始化 ChromaDB
  - [ ] `add_chunks(chunks)` 存储切片
  - [ ] `query(text, n=5)` 检索相关内容
  - [ ] `update_file(filepath)` 增量更新
- [ ] 实现切片 Prompt 模板
- [ ] 实现规范加载
  - [ ] 加载 cc-spec 内置规范
  - [ ] 加载项目自定义规范
- [ ] 集成到工作流
  - [ ] `/cc-spec init` 扫描 + 切片 + 存储
  - [ ] `apply` 前检索上下文
  - [ ] `apply` 后增量更新

### Phase 4: 端到端验证

**目标**：验证完整流程可用。

**任务清单**：

- [ ] 单任务执行测试
- [ ] Wave 并行执行测试
- [ ] RAG 检索质量测试
- [ ] 错误恢复测试
- [ ] 覆盖率验证测试

---

## 5. 技术细节

### 5.1 Codex CLI 调用命令

**通过 codeagent-wrapper 调用**：

```bash
# 单任务模式（推荐 stdin）
codeagent-wrapper --backend codex - ./project <<'EOF'
Task: task-1
Reference: @dev-plan.md
Scope: src/auth/
Test: pytest tests/test_auth.py
Deliverables: code + tests + coverage ≥90%

实现用户登录功能
EOF

# Resume 模式
codeagent-wrapper --backend codex resume {session_id} - <<'EOF'
覆盖率不够，请补充测试
EOF

# 并行模式
codeagent-wrapper --parallel <<'EOF'
---TASK---
id: task-1
backend: codex
workdir: ./project
---CONTENT---
实现登录 API
---TASK---
id: task-2
backend: codex
dependencies: task-1
---CONTENT---
实现登录测试
EOF
```

**实际调用的 Codex 命令**：
```bash
codex e --skip-git-repo-check -C {workdir} --json -
```

### 5.2 输出格式

**stdout（成功时）**：
```
这是 Codex 的回复内容...
已完成登录功能实现...

---
SESSION_ID: 019a7247-ac9d-71f3-89e2-a823dbd8fd14
```

**stderr（启动信息）**：
```
[codeagent-wrapper]
  Backend: codex
  Command: codex e --skip-git-repo-check -C ./project --json -
  PID: 12345
  Log: /tmp/codeagent-xxx.log
```

### 5.3 JSON Stream 事件

Codex 输出 JSON stream，关键事件：

| 事件类型 | 作用 |
|----------|------|
| `thread.started` | 获取 SESSION_ID |
| `item.completed` + `agent_message` | 获取最终回复 |

```json
{"type": "thread.started", "thread_id": "019a7247-..."}
{"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
```

### 5.4 Exit Code

| Code | 含义 |
|------|------|
| 0 | 成功 |
| 1 | 一般错误 |
| 124 | 超时 |
| 127 | codex 命令不存在 |
| 130 | 被中断 (Ctrl+C) |

### 5.5 Python 实现示例

```python
import subprocess

def call_codex(task: str, workdir: str, timeout: int = 7200) -> dict:
    """调用 Codex CLI"""

    result = subprocess.run(
        ["codeagent-wrapper", "--backend", "codex", "-", workdir],
        input=task,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    # 解析输出
    stdout = result.stdout
    session_id = None
    message = stdout

    if "\n---\nSESSION_ID:" in stdout:
        parts = stdout.rsplit("\n---\nSESSION_ID:", 1)
        message = parts[0].strip()
        session_id = parts[1].strip()

    return {
        "success": result.returncode == 0,
        "message": message,
        "session_id": session_id,
        "exit_code": result.returncode,
        "stderr": result.stderr
    }
```

### 5.6 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CODEX_TIMEOUT` | 7200000 (2h) | 执行超时时间（毫秒） |
| `CODEAGENT_MAX_PARALLEL_WORKERS` | 无限制 | 并行 worker 数量限制 |

---

## 6. 依赖要求

### 6.1 系统依赖

| 工具 | 用途 | 安装方式 |
|------|------|----------|
| Claude Code | 编排层 | `npm install -g @anthropic-ai/claude-code` |
| Codex CLI | 执行层 | `npm install -g @openai/codex` |
| codeagent-wrapper | Codex 包装器 | 从 myclaude 构建 |

### 6.2 Python 依赖

```
chromadb>=0.4.0      # 向量数据库
```

### 6.3 验证安装

```bash
# 验证 Claude Code
claude --version

# 验证 Codex
codex --version

# 验证 codeagent-wrapper
codeagent-wrapper --version
```

---

## 7. 文件变更清单

```
src/cc_spec/
├── codex/                    # 新增
│   ├── __init__.py
│   ├── client.py            # CodexClient 实现
│   ├── parser.py            # 输出解析
│   └── models.py            # CodexResult 等数据模型
├── rag/                      # 新增
│   ├── __init__.py
│   ├── knowledge_base.py    # KnowledgeBase 实现
│   ├── chunker.py           # 切片逻辑（调用 Codex）
│   └── prompts.py           # 切片 Prompt 模板
└── subagent/
    └── executor.py          # 修改：集成 CodexClient + RAG
```

---

## 8. 里程碑

| Phase | 目标 | 状态 |
|-------|------|------|
| Phase 1 | Codex 调用能力 | 待开始 |
| Phase 2 | SubAgent 集成 | 待开始 |
| Phase 3 | RAG 知识库集成 | 待开始 |
| Phase 4 | 端到端验证 | 待开始 |

---

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 向量库过时 | 检测文件 mtime，提示用户更新 |
| Codex 切片不稳定 | 定义明确的切片 Prompt + JSON schema |
| 检索不准 | 增加检索数量，Codex 二次筛选 |
| init 成本高 | 增量更新，.cc-specignore 排除文件 |
| 调试困难 | 详细日志，检索预览功能 |

---

*文档版本：v0.1.5-draft*
*创建日期：2025-12-16*
*更新日期：2025-12-16*
