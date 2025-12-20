# CC-SPEC v0.1.6 - 智能上下文注入

## 📋 版本概览

- **版本号**: 0.1.6
- **代号**: Smart Context Injection
- **依赖版本**: v0.1.5 (RAG 基础设施)
- **目标**: 自动化 RAG 上下文注入，减少 70-80% AI 上下文消耗

## 🎯 背景与目标

### 当前痛点

**v0.1.5 实现了 RAG 基础设施，但存在问题：**

1. **手动检索** - AI 需要主动调用 `kb query`，增加思考负担
2. **关联缺失** - 向量库不知道"这段代码属于哪个需求/任务"
3. **上下文浪费** - AI 仍需大量试错式搜索（Glob/Grep/Read）
4. **更新成本高** - 每次代码改动都需完整重建向量库

**理想工作流：**

```
用户: "/cc-spec:apply W1-T1"

→ 系统自动：
  1. 读取 W1-T1 的 context_query 配置
  2. 从 KB 检索最相关的 10 个 chunks
  3. 注入到 AI 提示词中
  4. AI 直接基于精准上下文开始工作

→ 上下文消耗：8K tokens (vs 传统 40K)
→ 执行速度：提升 3-5 倍
```

### 核心目标

- ✅ **自动上下文注入** - 无需 AI 手动调用 KB
- ✅ **需求-代码关联追踪** - 记录代码变更归属
- ✅ **增量更新优化** - 仅更新变化文件的向量
- ✅ **上下文消耗可视化** - 显示节省的 tokens 数量

## 🏗️ 架构设计

### 1. 增强的 Tasks 格式

**现有格式 (v0.1.4):**

```yaml
waves:
  - wave: 1
    description: "核心功能实现"
    tasks:
      - id: W1-T1
        title: "实现查询过滤功能"
        status: pending
```

**新格式 (v0.1.6):**

```yaml
waves:
  - wave: 1
    description: "核心功能实现"
    tasks:
      - id: W1-T1
        title: "实现查询过滤功能"
        status: pending

        # 新增：上下文配置
        context:
          # 自动检索查询（支持多个）
          queries:
            - "KB query filter implementation"
            - "where clause filtering in ChromaDB"

          # 明确关联的文件（可选，手动标注）
          related_files:
            - src/cc_spec/rag/knowledge_base.py:140-152
            - src/cc_spec/commands/kb.py:419-430

          # 检索数量（默认 10）
          max_chunks: 10

          # 上下文模式
          mode: auto  # auto | manual | hybrid
```

### 2. 智能上下文提供者

**新增模块: `src/cc_spec/rag/context_provider.py`**

```python
@dataclass
class ContextConfig:
    """任务/变更的上下文配置"""
    queries: list[str]
    related_files: list[str] = field(default_factory=list)
    max_chunks: int = 10
    mode: Literal["auto", "manual", "hybrid"] = "auto"

@dataclass
class InjectedContext:
    """注入的上下文结果"""
    chunks: list[CodeChunk]
    total_tokens: int
    sources: list[str]  # 来源文件列表
    query_results: dict[str, list[CodeChunk]]  # 每个 query 的结果

class ContextProvider:
    """智能上下文提供者"""

    def get_context_for_task(
        self,
        task_id: str,
        config: ContextConfig | None = None
    ) -> InjectedContext:
        """
        为指定任务获取上下文

        工作流程：
        1. 读取 task 的 context 配置
        2. 执行多个向量检索查询
        3. 合并去重结果
        4. 按相关度排序
        5. 返回 top-N chunks
        """

    def get_context_for_change(
        self,
        change_name: str
    ) -> InjectedContext:
        """为变更获取上下文（基于 proposal 内容）"""
```

### 3. 自动注入机制

**修改: `src/cc_spec/commands/apply.py`**

```python
def apply_task(task_id: str):
    """执行任务（v0.1.6 增强版）"""

    # 1. 解析任务
    task = parse_task(task_id)

    # 2. 获取智能上下文（新增）
    provider = ContextProvider(project_root)
    context = provider.get_context_for_task(task_id, task.context)

    # 3. 构建增强的 Agent 提示词
    agent_prompt = f"""
# 任务：{task.title}

## 相关上下文（已自动检索）

{render_context_chunks(context.chunks)}

## 任务要求

{task.description}

## 执行指引

基于上述上下文执行任务。你无需手动搜索代码，相关代码已提供。

---
💡 上下文统计：{context.total_tokens} tokens，来源 {len(context.sources)} 个文件
"""

    # 4. 启动 SubAgent
    run_subagent(agent_prompt, task.profile)
```

### 4. 增量更新优化

**新增: `src/cc_spec/rag/incremental.py`**

```python
class IncrementalUpdater:
    """增量向量库更新器"""

    def update_changed_files_only(
        self,
        changed_files: list[Path]
    ) -> UpdateReport:
        """
        仅更新变化的文件

        优化策略：
        1. 读取 manifest，获取文件 hash
        2. 对比 git diff，识别变化文件
        3. 仅对变化文件调用 Codex 切片
        4. 更新向量库中对应的 chunks
        5. 增量写入 events（不需要 compact）
        """

    def smart_chunking(
        self,
        file_path: Path,
        old_chunks: list[CodeChunk] | None
    ) -> list[CodeChunk]:
        """
        智能切片（基于 diff）

        如果有旧 chunks：
        1. 计算文件 diff
        2. 仅对变化的函数/类重新切片
        3. 保留未变化的 chunks（复用向量）
        """
```

### 5. 需求-代码关联追踪

**新增字段到向量库 metadata:**

```python
@dataclass
class ChunkMetadata:
    file_path: str
    chunk_type: str  # function | class | doc
    language: str

    # v0.1.6 新增
    related_changes: list[str] = []  # ["C-001", "C-002"]
    related_tasks: list[str] = []    # ["W1-T1", "W2-T3"]
    created_by: str | None = None    # "C-001/W1-T1"
    modified_by: list[str] = []      # ["C-002/W1-T2"]
```

> ⚠️ 注意：ChromaDB 的 metadata 目前仅支持 primitive（str/int/float/bool/None），不支持 list。  
> 因此在**实际落库**时，`related_changes/related_tasks/modified_by` 会以 **JSON 字符串**形式保存，例如：  
> `modified_by = "[\"C-001/W1-T1\",\"C-002/W1-T2\"]"`  
> cc-spec 的命令输出（如 `kb blame --json`）会自动解码为列表，避免语义分歧。

> 📌 归属索引（`.cc-spec/kb.attribution.json`）
> - cc-spec 会维护一份**规范化**的归属索引文件：`.cc-spec/kb.attribution.json`，用于保存 `modified_by / related_changes / related_tasks` 的**列表语义**（真实 JSON 数组）。
> - 追加策略为：**去重 + 保序（first-seen order）**。
> - 建议将该文件**提交到 git**，以便团队共享与复现归属信息；同时它会被 `.cc-specignore` 排除，避免“索引入库索引”。

**在代码变更时自动记录：**

```python
def track_code_changes(
    task_id: str,
    modified_files: list[Path]
):
    """
    追踪代码变更归属

    执行流程：
    1. SubAgent 完成任务后，git diff 获取变化文件
    2. 为变化的文件重新生成 chunks
    3. 在 metadata 中标记 created_by/modified_by
    4. 写入向量库

    后续查询时可以：
    - 查看某个需求改了哪些代码
    - 查看某段代码被哪些需求修改过
    """
```

## 📝 数据流设计

### 完整工作流

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 用户触发                                                 │
│    /cc-spec:apply W1-T1                                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. 读取任务配置                                             │
│    tasks.md → W1-T1.context.queries                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 智能检索上下文                                           │
│    ContextProvider:                                         │
│      - query("KB query filter")  → 5 chunks                 │
│      - query("where clause")     → 5 chunks                 │
│      - 合并去重                   → 8 unique chunks         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 注入到 Agent 提示词                                      │
│    prompt = f"""                                            │
│      任务：{task}                                           │
│      相关代码：{chunks}                                     │
│      ...                                                    │
│    """                                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. SubAgent 执行                                            │
│    - 基于精准上下文开始工作                                 │
│    - 无需手动 Glob/Grep/Read                                │
│    - 直接修改相关文件                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 增量更新向量库                                           │
│    IncrementalUpdater:                                      │
│      - git diff → [file_a.py, file_b.py]                    │
│      - 仅对这 2 个文件重新切片                              │
│      - 更新 metadata: modified_by = ["W1-T1"]               │
│      - upsert 到向量库                                      │
└─────────────────────────────────────────────────────────────┘
```

### KB 更新模式（默认 vs `--kb-strict`）

cc-spec v0.1.6 的 `apply` 有两种“KB 更新粒度”策略：

#### ✅ 默认模式（Wave 级更新，尽力而为）

- 任务在同一 Wave 内可并发执行
- Wave 全部成功后，执行一次 `kb update`（增量）
- KB 更新失败**不阻断** apply（降级）
- 优点：快；适合大多数任务
- 缺点：归属只到 Wave 级，难以精确回答“哪个任务改了这段代码”

#### 🔒 严格模式（Task 级更新，可追溯归属）

启用方式：

```bash
cc-spec apply <change> --kb-strict
```

严格模式的语义（重点是避免理解分歧与归属污染）：

1) **基线同步（baseline sync）**
- 在执行任何任务之前先做一次 `kb update`，把 KB 同步到当前工作区
- 目的：
  - 避免把历史遗留的脏改动“错误归属”给第一个任务
  - 避免出现“git 工作区 clean，但 HEAD 变化导致 KB 滞后”的情况
 - 严格语义：baseline 会使用 `skip_list_fields=true`，**不修改** `modified_by / related_changes / related_tasks`（仅保留既有值），只写 `step="apply.baseline"` 等标量字段

2) **每任务增量入库（per-task update）**
- 每个任务完成后，立刻执行一次 `kb update`（增量）
- 这次更新会带上 task 归属信息，用于写入 chunk metadata：

```json
{
  "step": "apply",
  "by": "C-001/W1-T1",
  "change_id": "C-001",
  "change_name": "add-feature",
  "wave": 1,
  "task_id": "W1-T1"
}
```

- 目的：
  - 让 `modified_by / related_tasks / related_changes` 的“列表语义”可落库、可追溯
  - 让下一个任务开始前，KB 已包含上一个任务的最新代码（更快、更准地注入上下文）

3) **最终同步（final sync）**
- 全部任务完成且技术检查（tech-check）通过后，在 compact 前再做一次 `kb update`
- 目的：捕获 tech-check（或主 Agent）产生的代码/配置变更，避免漏入库

4) **并发约束（强制串行）**
- 严格模式会强制 `max_concurrent = 1`
- 原因：只有串行执行才能把“每个任务的 KB 变更”精确归属到该任务

5) **失败策略（可预期、可阻断）**
- 严格模式下：baseline / per-task / final 任一 `kb update` 失败都会**阻断 apply**（返回非 0）
- 目的：保证“可追溯性”不是随机的，而是可依赖的行为

## 🛠️ 实施计划

### Phase 1: 基础设施（3-5 天）

**任务：**

1. ✅ 设计并实现 `ContextProvider` 类
   - `get_context_for_task()`
   - `get_context_for_change()`
   - 多查询合并去重逻辑

2. ✅ 扩展 `tasks.yaml` schema
   - 添加 `context` 字段验证
   - 更新模板文件

3. ✅ 实现 `IncrementalUpdater`
   - `update_changed_files_only()`
   - diff 识别逻辑

**验收标准：**
- `ContextProvider` 单元测试覆盖率 > 90%
- 可以为 task 配置多个 context queries
- 增量更新速度比全量快 10 倍以上

### Phase 2: 集成到工作流（2-3 天）

**任务：**

1. ✅ 修改 `/cc-spec:apply` 命令
   - 自动调用 `ContextProvider`
   - 注入上下文到 Agent 提示词
   - 显示上下文统计信息

2. ✅ 修改 `/cc-spec:plan` 命令
   - 生成 tasks.md 时自动添加 context 配置
   - 基于 proposal 内容生成合理的 queries

3. ✅ Agent 提示词模板更新
   - 添加"相关上下文"章节
   - 明确告知 AI 无需手动搜索

**验收标准：**
- 执行 apply 时自动显示上下文统计
- AI 不再需要手动调用 kb query
- 上下文注入对用户透明（无感知）

### Phase 3: 代码关联追踪（2-3 天）

**任务：**

1. ✅ 扩展 ChromaDB metadata schema
   - 添加 `related_changes`, `related_tasks` 字段
   - 添加 `created_by`, `modified_by` 字段

2. ✅ 实现自动关联记录
   - SubAgent 完成后自动 git diff
   - 标记变化文件的归属
   - 更新向量库 metadata

3. ✅ 新增查询命令
   - `cc-spec kb trace --change C-001`: 查看需求改了哪些代码
   - `cc-spec kb blame <file>`: 查看文件被哪些需求修改

**验收标准：**
- 每个 chunk 都有归属信息
- 可以反向查询"某段代码属于哪个需求"
- trace 命令输出清晰易读

### Phase 4: 性能优化与监控（1-2 天）

**任务：**

1. ✅ 添加性能监控
   - 记录每次检索耗时
   - 记录上下文 token 消耗
   - 对比传统方式的节省比例

2. ✅ 优化向量检索
   - 缓存常用查询结果（5 分钟 TTL）
   - 批量检索优化
   - 并行查询多个 queries

3. ✅ 用户友好的报告
   - `cc-spec kb stats`: 显示统计信息
   - 上下文节省可视化

**验收标准：**
- 单次检索响应时间 < 500ms
- stats 命令显示清晰的节省对比
- 缓存命中率 > 60%

## 📊 预期效果

### 上下文消耗对比

| 场景 | 传统方式 | v0.1.6 方式 | 节省比例 |
|------|---------|------------|---------|
| 小任务 (修改单个函数) | 15-20K tokens | 4-6K tokens | **70%** |
| 中等任务 (跨文件修改) | 30-40K tokens | 8-12K tokens | **75%** |
| 大任务 (重构模块) | 50-80K tokens | 15-25K tokens | **70%** |

### 执行速度提升

| 指标 | v0.1.5 | v0.1.6 | 提升 |
|------|--------|--------|------|
| 上下文准备时间 | 30-60s (多次 Read) | 2-5s (单次检索) | **10x** |
| AI 理解时间 | 长（需处理大量代码） | 短（精准上下文） | **3x** |
| 总执行时间 | 5-10 分钟 | 2-3 分钟 | **3-4x** |

### 向量库更新速度

| 操作 | v0.1.5 | v0.1.6 | 提升 |
|------|--------|--------|------|
| 修改 1 个文件后更新 | 60-90s (全量) | 5-10s (增量) | **10x** |
| 修改 5 个文件后更新 | 60-90s (全量) | 15-25s (增量) | **3x** |

## 🎨 用户体验示例

### 示例 1：执行任务（自动上下文）

```bash
$ cc-spec apply W1-T1

┌──────────────────────────────────────────────────────────┐
│ 任务：W1-T1 - 实现查询过滤功能                           │
├──────────────────────────────────────────────────────────┤
│ 🔍 智能上下文检索中...                                   │
│                                                          │
│   Query 1: "KB query filter implementation"              │
│   → 找到 5 个相关代码块                                  │
│                                                          │
│   Query 2: "where clause filtering"                      │
│   → 找到 4 个相关代码块                                  │
│                                                          │
│   📦 合并去重 → 8 个唯一代码块                           │
│   📊 总计：6,247 tokens                                  │
│   💾 节省：~75% 上下文消耗 (vs 传统 25K)                 │
│                                                          │
│   📁 来源文件：                                          │
│     - src/cc_spec/rag/knowledge_base.py                  │
│     - src/cc_spec/commands/kb.py                         │
│     - tests/rag/test_kb_query.py                         │
└──────────────────────────────────────────────────────────┘

🚀 启动 SubAgent (sonnet, 5min timeout)...

[SubAgent 基于精准上下文开始工作，无需手动搜索]
```

### 示例 2：增量更新（快速）

```bash
$ git diff --name-only
src/cc_spec/rag/knowledge_base.py
src/cc_spec/commands/kb.py

$ cc-spec kb update

┌──────────────────────────────────────────────────────────┐
│ 🔄 增量更新向量库                                        │
├──────────────────────────────────────────────────────────┤
│ 检测到 2 个文件变化：                                    │
│   - src/cc_spec/rag/knowledge_base.py                    │
│   - src/cc_spec/commands/kb.py                           │
│                                                          │
│ ⚡ 增量处理：                                            │
│   [████████████████████████] 100% (2/2)                  │
│                                                          │
│ ✅ 更新完成                                              │
│   - 重新切片：2 个文件                                   │
│   - 更新向量：15 个 chunks                               │
│   - 耗时：8.3 秒                                         │
│   - 节省：~85% 时间 (vs 全量 60s)                        │
└──────────────────────────────────────────────────────────┘
```

### 示例 3：追踪代码归属

```bash
$ cc-spec kb trace --change C-001

┌──────────────────────────────────────────────────────────┐
│ 变更 C-001: 添加 RAG 知识库支持                         │
├──────────────────────────────────────────────────────────┤
│ 📝 创建的文件 (created_by = C-001):                      │
│   - src/cc_spec/rag/knowledge_base.py      (45 chunks)   │
│   - src/cc_spec/rag/chunker.py             (23 chunks)   │
│   - src/cc_spec/commands/kb.py             (18 chunks)   │
│                                                          │
│ ✏️  修改的文件 (modified_by includes C-001):            │
│   - src/cc_spec/core/config.py             (3 chunks)    │
│   - pyproject.toml                          (1 chunk)    │
│                                                          │
│ 📊 统计：                                                │
│   - 总计 5 个文件                                        │
│   - 90 个代码块受影响                                    │
│   - 代码行数：~2,300 行                                  │
└──────────────────────────────────────────────────────────┘

$ cc-spec kb blame src/cc_spec/rag/knowledge_base.py:140-152

📄 src/cc_spec/rag/knowledge_base.py:140-152
└─ query() 方法

🏷️  归属历史：
  - 创建于：C-001 (2025-12-17, W1-T1)
    描述：初始实现 KB 查询功能

  - 修改于：C-002 (2025-12-18, W1-T3)
    描述：添加 where 过滤条件支持

  - 修改于：C-003 (2025-12-19, W2-T1)
    描述：修复 ChromaDB API 兼容性
```

## 🧪 测试策略

### 单元测试

```python
# tests/rag/test_context_provider.py

def test_get_context_for_task_with_multiple_queries():
    """测试多查询合并"""
    provider = ContextProvider(project_root)
    context = provider.get_context_for_task(
        "W1-T1",
        ContextConfig(
            queries=["query filter", "where clause"],
            max_chunks=10
        )
    )
    assert len(context.chunks) <= 10
    assert context.total_tokens > 0
    assert len(context.sources) > 0

def test_incremental_update_only_changed_files():
    """测试增量更新"""
    updater = IncrementalUpdater(project_root)

    # 模拟修改 2 个文件
    changed = [Path("src/file_a.py"), Path("src/file_b.py")]

    report = updater.update_changed_files_only(changed)

    assert report.updated_files == 2
    assert report.time_saved > 0.5  # 节省至少 50% 时间
```

### 集成测试

```python
# tests/integration/test_smart_context_workflow.py

def test_apply_with_auto_context():
    """测试 apply 命令自动注入上下文"""
    # 1. 创建测试任务
    task_yaml = """
    waves:
      - wave: 1
        tasks:
          - id: W1-T1
            context:
              queries: ["test query"]
              max_chunks: 5
    """

    # 2. 执行 apply
    result = run_cli("cc-spec apply W1-T1")

    # 3. 验证上下文注入
    assert "智能上下文检索中" in result.output
    assert "找到 5 个相关代码块" in result.output
    assert "节省" in result.output
```

## 📋 配置文件更新

### .cc-spec/config.yaml

```yaml
version: '1.3'
project_name: cc-spec

# v0.1.6 新增：智能上下文配置
smart_context:
  enabled: true

  # 默认检索配置
  default_max_chunks: 10
  default_mode: auto  # auto | manual | hybrid

  # 缓存配置
  cache:
    enabled: true
    ttl_seconds: 300  # 5 分钟

  # 增量更新配置
  incremental:
    enabled: true
    batch_size: 5  # 每批处理 5 个文件

  # 性能监控
  monitoring:
    enabled: true
    log_slow_queries: true  # 记录慢查询 (> 1s)
    report_savings: true    # 显示节省统计

kb:
  embedding_model: BAAI/bge-small-en-v1.5
  max_file_bytes: 524288
  reference_mode: index
```

## 🔄 迁移指南

### 从 v0.1.5 升级到 v0.1.6

**步骤：**

1. **更新配置文件**
   ```bash
   cc-spec update --version 1.3
   ```

2. **重建向量库（添加 metadata 字段）**
   ```bash
   # 备份现有向量库
   cp -r .cc-spec/vectordb .cc-spec/vectordb.backup

   # 重建（会自动添加新字段）
   cc-spec kb rebuild
   ```

3. **更新现有 tasks.yaml**
   ```bash
   # 自动添加 context 配置
   cc-spec migrate tasks --add-context
   ```

4. **验证迁移**
   ```bash
   cc-spec kb stats
   # 应该显示：
   # - 智能上下文：已启用
   # - 代码追踪：已启用
   ```

**兼容性：**
- ❌ **不保证向后兼容**：v0.1.6 以“可追溯/可注入”为目标，允许打破旧行为
- ✅ 渐进式启用：可以逐步为任务添加 `context` 配置（未配置时使用最小 query 兜底）
- ✅ 可选严格：默认仍是 Wave 级更新；需要 task 级归属时使用 `--kb-strict`

## 📖 文档更新

### 需要更新的文档

1. **用户指南**
   - `docs/cc-spec/workflow.md`: 添加智能上下文章节
   - `docs/cc-spec/commands.md`: 更新 apply/kb 命令说明

2. **开发者指南**
   - 新增：`docs/dev/smart-context-architecture.md`
   - 新增：`docs/dev/context-provider-api.md`

3. **最佳实践**
   - 新增：`docs/best-practices/writing-context-queries.md`
   - 新增：`docs/best-practices/optimizing-context-injection.md`

## 🚀 发布计划

### Alpha 测试（内部）

- **时间**: 实施完成后 1 周
- **范围**: cc-spec 自身开发
- **目标**: 验证核心功能，收集性能数据

### Beta 测试（小范围）

- **时间**: Alpha 后 1-2 周
- **范围**: 3-5 个外部测试项目
- **目标**: 验证通用性，优化用户体验

### 正式发布

- **时间**: Beta 稳定后
- **版本号**: v0.1.6
- **发布渠道**: PyPI, GitHub Release

## 🎯 成功指标

### 定量指标

- ✅ 上下文消耗减少 **> 70%**
- ✅ 任务执行速度提升 **> 3x**
- ✅ 增量更新速度提升 **> 10x**
- ✅ 用户满意度 **> 8/10**

### 定性指标

- ✅ AI 无需手动调用 kb query
- ✅ 用户感知"更智能"、"更快"
- ✅ 上下文注入对用户透明
- ✅ 代码归属可追踪

## 🐛 已知限制与未来优化

### 当前限制

1. **查询质量依赖配置** - 需要手动编写好的 context queries
2. **向量模型固定** - 暂不支持动态切换 embedding 模型
3. **跨变更关联弱** - 无法自动识别"这个需求依赖那个需求的代码"

### v0.1.7 可能的方向

- **自动生成 context queries** - 基于 proposal 内容自动生成
- **跨变更依赖分析** - "C-002 依赖 C-001 的代码"
- **多模态检索** - 支持代码 + 文档 + 注释联合检索
- **实时向量更新** - 保存文件时自动增量更新（file watcher）

---

**文档版本**: 1.0
**创建日期**: 2025-12-17
**作者**: 喵娘工程师 幽浮喵 (Anthropic Claude Sonnet 4.5)
**审核状态**: Draft - 待主人审核喵～ ฅ'ω'ฅ
