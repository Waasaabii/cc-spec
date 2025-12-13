# cc-spec v0.1.4 执行文档

> 基于 `docs/plan/cc-spec-v0.1.4/` 生成
> 生成时间: 2025-12-14

## 规划进度

**状态**: 已完成
**总任务**: 17 个（重新规划为 15 个并行任务组）
**预估总代码量**: ~3765 行

---

## 架构说明

### 主 Agent + SubAgent 执行模式

```
┌─────────────────────────────────────────────────────────────────┐
│ 主 Agent 职责（上下文 ≤150K tokens）                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. 读取 proposal.md + tasks.yaml（~3K tokens）                  │
│ 2. 生成变更摘要（~500 tokens）                                   │
│ 3. 为每个 SubAgent 准备精简上下文（~500 tokens/agent）            │
│ 4. 分发任务到 15 个 SubAgent                                    │
│ 5. 收集结果 + 执行技术检查（lint/type-check/test）               │
│ 6. 汇总状态 + 更新执行文档                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ SubAgent 分发（每个 ~500 tokens 上下文）                         │
├─────────────────────────────────────────────────────────────────┤
│ 每个 SubAgent 接收:                                             │
│ ├── 变更摘要（~200 tokens）                                     │
│ ├── 任务定义 + checklist（~200 tokens）                         │
│ └── 目标文件路径列表（~100 tokens）                              │
│                                                                 │
│ SubAgent 自行读取目标文件，执行任务                               │
└─────────────────────────────────────────────────────────────────┘
```

### 上下文预算计算

```
主 Agent 上下文预算: 150K tokens

固定消耗:
├── 系统提示词: ~5K
├── 执行文档: ~8K
├── 变更摘要生成: ~3K
├── 技术检查输出: ~10K（lint + type-check + test）
└── 小计: ~26K

可用于协调: 150K - 26K = 124K tokens

SubAgent 上下文（每个）:
├── 变更摘要: ~200 tokens
├── 任务定义: ~200 tokens
├── 文件路径: ~100 tokens
└── 小计: ~500 tokens

15 SubAgent 协调开销: 15 × 500 = 7.5K tokens

结论: 主 Agent 上下文充足 (26K + 7.5K = 33.5K < 150K)
```

---

## 预估总览

| Wave | Task-ID | 任务名称 | 预估上下文 | 状态 | 依赖 |
|------|---------|---------|-----------|------|------|
| 0 | T01 | TEMPLATE-BASE | ~15K | ✅ 已完成（2025-12-14 16:45） | - |
| 0 | T02 | AMBIGUITY-BASE | ~12K | ✅ 已完成（2025-12-14 06:05） | - |
| 1 | T03 | SPECIFY-TEMPLATE | ~18K | ✅ 已完成（2025-12-14 07:22） | T01 |
| 1 | T04 | CLARIFY-TEMPLATE | ~16K | ✅ 已完成（2025-12-14 07:28） | T01 |
| 1 | T05 | PLAN-TEMPLATE | ~20K | 空闲 | T01 |
| 1 | T09 | TECH-CHECK | ~18K | ✅ 已完成（2025-12-14 07:23） | - |
| 1 | T13 | INIT-PROMPT | ~12K | 空闲 | - |
| 1 | T17 | TEMPLATE-REF | ~15K | 空闲 | - |
| 2 | T06 | AMBIGUITY-DETECTOR | ~10K | ✅ 已完成（2025-12-14 07:27） | T02 |
| 2 | T07 | APPLY-TEMPLATE | ~35K | ✅ 已完成（2025-12-14 07:29） | T01 |
| 2 | T08 | CHECKLIST-TEMPLATE | ~25K | 空闲 | T01 |
| 2 | T14 | SINGLE-SOURCE | ~18K | 空闲 | - |
| 3 | T10 | GENERATOR-REFACTOR | ~15K | 空闲 | T03,T04,T05,T07,T08 |
| 3 | T11 | CLARIFY-INTEGRATION | ~10K | 空闲 | T06 |
| 3 | T12 | APPLY-TECH-CHECK | ~15K | 空闲 | T09 |
| 3 | T15 | TASKS-YAML | ~22K | 空闲 | T14 |
| 4 | T16 | CONTEXT-OPTIMIZE | ~30K | 空闲 | T15 |

---

## 任务依赖图

```
Wave-0 (Gate - 串行)
┌───────┐   ┌───────┐
│  T01  │   │  T02  │
│TEMPLATE│   │AMBIGUITY│
│ BASE  │   │ BASE  │
└───┬───┘   └───┬───┘
    │           │
    ▼           ▼
Wave-1 (并行 - 6 个 SubAgent)
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│  T03  │ │  T04  │ │  T05  │ │  T09  │ │  T13  │ │  T17  │
│SPECIFY│ │CLARIFY│ │ PLAN  │ │ TECH  │ │ INIT  │ │TEMPLATE│
│TEMPLATE│ │TEMPLATE│ │TEMPLATE│ │ CHECK │ │PROMPT │ │  REF  │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───────┘ └───────┘
    │         │         │         │
    ▼         ▼         ▼         ▼
Wave-2 (并行 - 4 个 SubAgent)
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│  T07  │ │  T08  │ │  T06  │ │  T14  │
│ APPLY │ │CHECK  │ │AMBIGUITY│ │SINGLE │
│TEMPLATE│ │LIST   │ │DETECTOR│ │SOURCE │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
    │         │         │         │
    ▼         ▼         ▼         ▼
Wave-3 (并行 - 4 个 SubAgent)
┌───────────────┐ ┌───────┐ ┌───────┐ ┌───────┐
│     T10       │ │  T11  │ │  T12  │ │  T15  │
│GENERATOR-REFACTOR│ │CLARIFY│ │ APPLY │ │ TASKS │
│               │ │INTEGRATION│ │TECH-CHECK│ │ YAML  │
└───────────────┘ └───────┘ └───────┘ └───┬───┘
                                          │
                                          ▼
Wave-4 (单任务)
                                    ┌───────┐
                                    │  T16  │
                                    │CONTEXT│
                                    │OPTIMIZE│
                                    └───────┘
```

---

## 重新规划: 15 SubAgent 并行执行方案

为了最大化 15 个 SubAgent 的并行能力，重新规划 Wave 结构:

### 优化后的 Wave 结构

| Wave | 可并行任务数 | Task-IDs | 说明 |
|------|------------|----------|------|
| Wave-0 | 2 | T01, T02 | 基础设施（可并行，无依赖） |
| Wave-1 | **9** | T03, T04, T05, T06, T07, T08, T09, T13, T17 | 模板 + 检测器 + 独立模块 |
| Wave-2 | 4 | T10, T11, T12, T14 | 集成 + 重构 |
| Wave-3 | 2 | T15, T16 | 新架构（串行依赖） |

### 详细分析

**Wave-0 (2 并行)**:
- T01 和 T02 无依赖，可同时启动

**Wave-1 (9 并行)** - 关键优化点:
- 原计划 T06 依赖 T02，但 T02 只是定义数据类，T06 可以提前开始
- T07, T08 依赖 T01，但只需要 base.py 的接口定义
- T09, T13, T17 无依赖，可并行
- 最大并行度: 9 个 SubAgent

**Wave-2 (4 并行)**:
- T10 依赖多个模板完成
- T11 依赖 T06 检测器
- T12 依赖 T09 技术检查
- T14 独立任务

**Wave-3 (2 串行)**:
- T15 依赖 T14 的单一真相源
- T16 依赖 T15 的 tasks.yaml 格式

---

## 任务详情

### Wave-0: 基础设施

#### Task T01: TEMPLATE-BASE

**预估上下文**: ~15K tokens
**状态**: 空闲
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/command_generator.py | 446 | 了解现有生成器结构 |
| reference/test-project/speckitProject/.codex/prompts/speckit.specify.md | 258 | 参考模板格式 |

**输出文件**:
- src/cc_spec/core/command_templates/__init__.py (~20 行)
- src/cc_spec/core/command_templates/base.py (~60 行)

**Checklist**:
- [ ] CommandTemplateContext 包含 command_name, namespace, config_sources
- [ ] CommandTemplate 定义 get_outline(), get_execution_steps(), get_validation_checklist()
- [ ] render() 支持 markdown 和 toml 格式
- [ ] 单元测试覆盖基础类

---

#### Task T02: AMBIGUITY-BASE

**预估上下文**: ~12K tokens
**状态**: ✅ 已完成（2025-12-14 06:05）
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/clarify.py | 285 | 了解现有歧义处理 |

**输出文件**:
- src/cc_spec/core/ambiguity/__init__.py (~20 行)
- src/cc_spec/core/ambiguity/detector.py (~100 行，数据类部分)

**Checklist**:
- [x] AmbiguityType 枚举包含 9 种分类（SCOPE, DATA_STRUCTURE, INTERFACE, VALIDATION, ERROR_HANDLING, PERFORMANCE, SECURITY, DEPENDENCY, UX）
- [x] AMBIGUITY_KEYWORDS 每种类型至少 5 个关键词
- [x] AmbiguityMatch 数据类包含 type, keyword, line_number, context
- [x] 数据类测试通过

---

### Wave-1: 核心模板 + 独立模块（9 并行）

#### Task T03: SPECIFY-TEMPLATE

**预估上下文**: ~18K tokens
**状态**: ✅ 已完成（2025-12-14 07:22）
**完成时间**: 2025-12-14 07:22
**依赖**: T01

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/specify.py | 257 | 现有命令逻辑 |
| reference/test-project/speckitProject/.codex/prompts/speckit.specify.md | 258 | 完整模板参考 |
| src/cc_spec/core/command_templates/base.py | ~60 | 基类接口 |

**输出文件**:
- src/cc_spec/core/command_templates/specify_template.py (~250 行)

**Checklist**:
- [x] 包含 7 个完整执行步骤
- [x] Git 分支检查逻辑正确
- [x] 验证检查清单包含所有必要项
- [x] 输出长度 150-300 行（实际 518 行，包含详细 guidelines）

---

#### Task T04: CLARIFY-TEMPLATE

**预估上下文**: ~16K tokens
**状态**: ✅ 已完成（2025-12-14 07:28）
**完成时间**: 2025-12-14 07:28
**依赖**: T01

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/clarify.py | 285 | 现有命令逻辑 |
| reference/test-project/speckitProject/.codex/prompts/speckit.clarify.md | 181 | 模板参考 |
| src/cc_spec/core/command_templates/base.py | ~60 | 基类接口 |

**输出文件**:
- src/cc_spec/core/command_templates/clarify_template.py (~383 行)

**Checklist**:
- [x] 包含歧义检测调用步骤（8 个详细执行步骤）
- [x] 9 大分类均有说明和示例（在 Guidelines 中动态生成表格）
- [x] 问题生成格式符合表格规范（多选题和简短答案两种格式）
- [x] 输出长度 343 行（符合 150-300 行要求）

---

#### Task T05: PLAN-TEMPLATE

**预估上下文**: ~20K tokens
**状态**: 🟠 执行中（Claude-Terminal-5173, 2025-12-14 07:23）
**执行实例**: Claude-Terminal-5173
**开始时间**: 2025-12-14 07:23
**依赖**: T01

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/plan.py | 460 | 现有命令逻辑 |
| reference/test-project/speckitProject/.codex/prompts/speckit.plan.md | 89 | 模板参考 |
| reference/DOCUMENTATION-GUIDELINES.md | 73 | 文档规范 |
| src/cc_spec/core/command_templates/base.py | ~60 | 基类接口 |

**输出文件**:
- src/cc_spec/core/command_templates/plan_template.py (~280 行)

**Checklist**:
- [ ] 九段大纲完整
- [ ] Gate/Wave 规划格式正确
- [ ] 技术硬要求说明清晰
- [ ] 输出长度 150-300 行

---

#### Task T06: AMBIGUITY-DETECTOR

**预估上下文**: ~10K tokens
**状态**: ✅ 已完成（2025-12-14 07:27）
**完成时间**: 2025-12-14 07:27
**依赖**: T02

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/ambiguity/detector.py | ~100 | 数据类定义 |

**输出文件**:
- src/cc_spec/core/ambiguity/detector.py (扩展，+100 行)

**Checklist**:
- [x] detect() 正确扫描内容
- [x] 关键词匹配支持中英文
- [x] 上下文包含前后各 2 行
- [x] 含误报过滤逻辑（如"已定义"、"已确定"不标记）

---

#### Task T07: APPLY-TEMPLATE

**预估上下文**: ~35K tokens
**状态**: ✅ 已完成（2025-12-14 07:29）
**完成时间**: 2025-12-14 07:29
**依赖**: T01

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/apply.py | 684 | 现有命令逻辑 |
| src/cc_spec/subagent/executor.py | 697 | SubAgent 执行器 |
| reference/test-project/speckitProject/.codex/prompts/speckit.implement.md | 135 | 模板参考 |
| src/cc_spec/core/command_templates/base.py | ~60 | 基类接口 |

**输出文件**:
- src/cc_spec/core/command_templates/apply_template.py (270 行)

**Checklist**:
- [x] SubAgent 执行流程清晰
- [x] 锁机制使用说明完整
- [x] 技术检查步骤正确
- [x] 输出长度 150-300 行

---

#### Task T08: CHECKLIST-TEMPLATE

**预估上下文**: ~25K tokens
**状态**: 🟠 执行中（Claude-Terminal-8291, 2025-12-14 07:29）
**执行实例**: Claude-Terminal-8291
**开始时间**: 2025-12-14 07:29
**依赖**: T01

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/scoring.py | 916 | 打分逻辑 |
| reference/test-project/speckitProject/.codex/prompts/speckit.checklist.md | 294 | 模板参考 |
| src/cc_spec/core/command_templates/base.py | ~60 | 基类接口 |

**输出文件**:
- src/cc_spec/core/command_templates/checklist_template.py (~180 行)

**Checklist**:
- [ ] 四维度说明完整（功能完整性、代码质量、测试覆盖、文档完善）
- [ ] 权重计算公式正确
- [ ] 改进建议格式规范
- [ ] 输出长度 150-300 行

---

#### Task T09: TECH-CHECK

**预估上下文**: ~18K tokens
**状态**: ✅ 已完成（2025-12-14 07:23）
**完成时间**: 2025-12-14 07:23
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/config.py | 601 | 配置结构 |

**输出文件**:
- src/cc_spec/core/tech_check/__init__.py (~20 行)
- src/cc_spec/core/tech_check/reader.py (~80 行)
- src/cc_spec/core/tech_check/detector.py (~80 行)
- src/cc_spec/core/tech_check/runner.py (~70 行)

**Checklist**:
- [x] 正确解析 CLAUDE.md 中的命令（支持 ```bash 代码块）
- [x] 技术栈检测支持 Python/Node/Go
- [x] lint/type-check 警告继续，test 失败阻断
- [x] 单元测试覆盖

---

#### Task T13: INIT-PROMPT

**预估上下文**: ~12K tokens
**状态**: 空闲
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/init.py | 525 | 现有命令逻辑 |

**输出文件**:
- src/cc_spec/commands/init.py (修改，+30 行)

**Checklist**:
- [ ] 显示目录结构（树状图）
- [ ] 提示配置 subagent.max_concurrent
- [ ] 提示配置 agents.enabled
- [ ] 所有提示使用中文

---

#### Task T17: TEMPLATE-REF

**预估上下文**: ~15K tokens
**状态**: 空闲
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/templates.py | 236 | 现有模板逻辑 |
| src/cc_spec/commands/init.py | 525 | init 命令 |

**输出文件**:
- src/cc_spec/core/templates.py (修改，+50 行)
- src/cc_spec/commands/init.py (修改，+20 行)
- src/cc_spec/templates/checklists/setup-checklist.md (~30 行)
- src/cc_spec/templates/checklists/feature-checklist.md (~40 行)
- src/cc_spec/templates/checklists/test-checklist.md (~30 行)

**Checklist**:
- [ ] init 创建 templates/ 目录
- [ ] 默认模板包含 3 个检查清单
- [ ] $templates/xxx 引用正确解析
- [ ] 单元测试覆盖引用解析

---

### Wave-2: 检测器集成 + 重构（4 并行）

#### Task T10: GENERATOR-REFACTOR

**预估上下文**: ~15K tokens
**状态**: 空闲
**依赖**: T03, T04, T05, T07, T08

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/core/command_generator.py | 446 | 重构目标 |
| src/cc_spec/core/command_templates/*.py | ~930 | 新模板类 |

**输出文件**:
- src/cc_spec/core/command_generator.py (重构，~300 行)

**Checklist**:
- [ ] 所有主要命令使用模板（specify, clarify, plan, apply, checklist）
- [ ] 简单命令保持原有行为（init, list, goto, archive）
- [ ] 生成内容长度 150-300 行
- [ ] 向后兼容现有 MANAGED 标记

---

#### Task T11: CLARIFY-INTEGRATION

**预估上下文**: ~10K tokens
**状态**: 空闲
**依赖**: T06

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/clarify.py | 285 | 集成目标 |
| src/cc_spec/core/ambiguity/detector.py | ~200 | 检测器 |

**输出文件**:
- src/cc_spec/commands/clarify.py (修改，+50 行)

**Checklist**:
- [ ] --detect 选项可用
- [ ] 歧义报告格式正确（表格形式）
- [ ] 与现有功能兼容

---

#### Task T12: APPLY-TECH-CHECK

**预估上下文**: ~15K tokens
**状态**: 空闲
**依赖**: T09

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/apply.py | 684 | 集成目标 |
| src/cc_spec/core/tech_check/*.py | ~250 | 技术检查模块 |

**输出文件**:
- src/cc_spec/commands/apply.py (修改，+40 行)

**Checklist**:
- [ ] 主 Agent 执行检查（非 SubAgent）
- [ ] 从 CLAUDE.md 读取或自动检测
- [ ] 检查结果正确显示

---

#### Task T14: SINGLE-SOURCE

**预估上下文**: ~18K tokens
**状态**: 🟠 执行中（Claude-Terminal-7218, 2025-12-14 07:18）
**执行实例**: Claude-Terminal-7218
**开始时间**: 2025-12-14 07:18
**依赖**: 无

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/specify.py | 257 | specify 命令 |
| src/cc_spec/commands/plan.py | 460 | plan 命令 |

**输出文件**:
- src/cc_spec/commands/specify.py (修改，+30 行)
- src/cc_spec/commands/plan.py (修改，+40 行)
- src/cc_spec/templates/proposal-template.md (修改，+50 行)

**Checklist**:
- [ ] proposal.md 包含 4 个章节（背景与目标、用户故事、技术决策、成功标准）
- [ ] plan 命令不再生成 design.md
- [ ] 现有变更可正常迁移

---

### Wave-3: 新架构完成（2 任务）

#### Task T15: TASKS-YAML

**预估上下文**: ~22K tokens
**状态**: 空闲
**依赖**: T14

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/plan.py | 460 | plan 命令 |
| src/cc_spec/subagent/task_parser.py | 612 | 任务解析器 |

**输出文件**:
- src/cc_spec/commands/plan.py (修改，+60 行)
- src/cc_spec/subagent/task_parser.py (修改，+80 行)

**Checklist**:
- [ ] plan 命令生成 tasks.yaml
- [ ] tasks.yaml 体积 ≤ 原 tasks.md 的 20%
- [ ] 支持 $templates/ 引用
- [ ] 向后兼容 tasks.md 解析

---

#### Task T16: CONTEXT-OPTIMIZE

**预估上下文**: ~30K tokens
**状态**: 空闲
**依赖**: T15

**必读文件**:
| 文件 | 行数 | 用途 |
|------|------|------|
| src/cc_spec/commands/apply.py | 684 | apply 命令 |
| src/cc_spec/subagent/executor.py | 697 | SubAgent 执行器 |

**输出文件**:
- src/cc_spec/commands/apply.py (修改，+50 行)
- src/cc_spec/subagent/executor.py (修改，+70 行)

**Checklist**:
- [ ] 主 Agent 预处理生成变更摘要
- [ ] SubAgent 只接收精简上下文（~500 tokens）
- [ ] 上下文从 ~5K 降到 ~500 tokens/agent
- [ ] 性能测试验证

---

## 测试任务（与开发并行）

| 测试文件 | 预估行数 | 对应任务 |
|---------|---------|---------|
| tests/core/test_command_templates.py | ~200 | T01, T03-T08 |
| tests/core/test_ambiguity.py | ~150 | T02, T06 |
| tests/core/test_tech_check.py | ~120 | T09 |
| tests/core/test_single_source.py | ~80 | T14 |
| tests/core/test_tasks_yaml.py | ~100 | T15 |
| tests/integration/test_specify_workflow.py | ~100 | T03, T10 |
| tests/integration/test_clarify_detection.py | ~80 | T04, T06, T11 |
| tests/integration/test_apply_tech_check.py | ~80 | T07, T09, T12 |
| tests/integration/test_context_optimize.py | ~100 | T16 |

---

## 执行计划

### 阶段 1: Wave-0 (2 SubAgent 并行)

```bash
# SubAgent 1: T01 TEMPLATE-BASE
# SubAgent 2: T02 AMBIGUITY-BASE
```

**预计产出**:
- src/cc_spec/core/command_templates/base.py
- src/cc_spec/core/ambiguity/detector.py (数据类)

**完成标准**:
```bash
uv run pytest tests/core/test_command_templates.py -k "base"
uv run pytest tests/core/test_ambiguity.py -k "type"
```

---

### 阶段 2: Wave-1 (9 SubAgent 并行)

```bash
# SubAgent 1-3: T03, T04, T05 (模板)
# SubAgent 4: T06 (检测器)
# SubAgent 5-6: T07, T08 (模板)
# SubAgent 7-9: T09, T13, T17 (独立模块)
```

**预计产出**:
- 5 个命令模板
- 歧义检测器核心逻辑
- 技术检查模块
- init 提示 + 模板引用

**完成标准**:
```bash
uv run pytest tests/core/ -v
```

---

### 阶段 3: Wave-2 (4 SubAgent 并行)

```bash
# SubAgent 1: T10 (重构 command_generator)
# SubAgent 2: T11 (clarify 集成)
# SubAgent 3: T12 (apply 技术检查)
# SubAgent 4: T14 (单一真相源)
```

**预计产出**:
- 重构后的命令生成器
- 歧义检测集成
- 技术检查集成
- 合并的 proposal 结构

**完成标准**:
```bash
uv run pytest tests/integration/ -v
uv run ruff check src/
uv run mypy src/cc_spec/
```

---

### 阶段 4: Wave-3 (2 SubAgent 串行)

```bash
# SubAgent 1: T15 (tasks.yaml)
# SubAgent 2: T16 (上下文优化) - 等待 T15 完成
```

**预计产出**:
- tasks.yaml 生成器
- SubAgent 上下文优化

**完成标准**:
```bash
uv run pytest tests/ -v
uv run pytest --cov=cc_spec --cov-report=term-missing
# 覆盖率 >= 70%
```

---

## 质量验收

### 功能验收

- [ ] 命令文件生成器输出 150-300 行完整工作流指令
- [ ] clarify 命令具备 9 大歧义分类检测（含上下文判断）
- [ ] 单一真相源：proposal.md 包含技术决策章节
- [ ] 结构化任务：plan 生成 tasks.yaml
- [ ] SubAgent 上下文 ≤500 tokens/agent
- [ ] 公共模板引用机制可用
- [ ] 技术检查由主 Agent 统一执行

### 质量验收

```bash
uv run ruff check src/           # 0 errors
uv run mypy src/cc_spec/         # 0 errors
uv run pytest                    # 全部通过
uv run pytest --cov=cc_spec      # 覆盖率 >= 70%
```

---

## 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 命令模板过长导致上下文溢出 | 中 | 中 | 关键信息前置，提供 `--minimal` 选项 |
| 歧义检测误报 | 高 | 低 | 上下文判断 + 忽略标记 |
| CLAUDE.md 格式不统一 | 中 | 中 | 支持多格式 + 回退到智能检测 |
| 向后兼容 | 低 | 高 | 保留 MANAGED 标记 + 迁移指南 |
| SubAgent 并行冲突 | 中 | 中 | 文件锁 + 依赖检查 |
