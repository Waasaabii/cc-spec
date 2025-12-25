# tools.yaml 配置结构设计

> 版本: 0.2.1
> 日期: 2025-12-24
> 状态: 设计中

---

## 一、设计目标

1. **统一管理** - Skills 和 Commands 在同一配置文件中管理
2. **分层架构** - builtin（内置只读）+ user（用户可编辑）
3. **跨项目复用** - 用户 Skills 可在多个项目间共享
4. **渐进式加载** - 支持 Progressive Disclosure 三层加载
5. **触发规则配置** - 支持 keywords + intentPatterns 自动触发

---

## 二、文件位置

```
~/.cc-spec/
├── tools.yaml              # 主配置文件
├── skills/                 # 用户 Skills 存储
│   ├── my-skill-1/
│   │   ├── SKILL.md
│   │   └── scripts/
│   └── my-skill-2/
│       └── SKILL.md
└── cache/                  # 缓存目录
    └── skill-index.json    # Skills 索引缓存
```

---

## 三、tools.yaml 完整结构

```yaml
# ~/.cc-spec/tools.yaml
# cc-spec Tools 配置文件

version: "0.2.1"
updated_at: "2025-12-24T10:00:00Z"

# ============================================
# Skills 配置
# ============================================
skills:
  # 全局设置
  settings:
    auto_suggest: true              # 是否自动建议匹配的 Skills
    max_concurrent_skills: 3        # 同时激活的最大 Skills 数
    progressive_loading: true       # 启用渐进式加载

  # 内置 Skills（只读，随工具版本更新）
  builtin:
    - name: cc-spec-workflow
      version: "1.0.0"
      type: workflow
      description: |
        cc-spec 7步工作流指导。在用户讨论需求变更、
        功能开发、代码重构时自动激活。
      enabled: true
      triggers:
        keywords:
          - "cc-spec"
          - "变更流程"
          - "需求分析"
          - "proposal"
          - "clarify"
        patterns:
          - "(specify|plan|apply|checklist|archive)"
          - "变更.*流程"

    - name: subagent-coordinator
      version: "1.0.0"
      type: execution
      description: |
        SubAgent 并发协调器。在执行多任务 Wave/Task
        时自动激活，协调最多10个并发 SubAgent。
      enabled: true
      triggers:
        keywords:
          - "subagent"
          - "并发执行"
          - "wave"
          - "task"
        patterns:
          - "W\\d+-T\\d+"
          - "(parallel|concurrent).*task"

    - name: delta-tracker
      version: "1.0.0"
      type: domain
      description: |
        Delta 变更追踪专家。在讨论代码变更、
        文件修改时激活，确保 Delta 格式规范。
      enabled: true
      triggers:
        keywords:
          - "delta"
          - "变更记录"
          - "ADDED"
          - "MODIFIED"
          - "REMOVED"
        patterns:
          - "(ADDED|MODIFIED|REMOVED|RENAMED):"

  # 用户 Skills（可编辑，跨项目复用）
  user: []
  # 示例:
  # - name: my-code-review
  #   version: "1.0.0"
  #   type: domain
  #   source: "~/.cc-spec/skills/my-code-review"
  #   description: 自定义代码审查流程
  #   enabled: true
  #   imported_from: "project-name"
  #   imported_at: "2025-12-24T10:00:00Z"
  #   triggers:
  #     keywords: ["review", "代码审查"]
  #     patterns: ["(code|pr).*review"]

# ============================================
# Commands 配置
# ============================================
commands:
  # 全局设置
  settings:
    namespace: "cc-spec"            # 命令前缀命名空间
    auto_install: true              # 项目初始化时自动安装

  # 内置 Commands（cc-spec 工作流命令）
  builtin:
    - name: cc-spec-specify
      version: "1.0.0"
      stage: 1
      description: "specify 阶段，与用户确认需求，输出 proposal.md"
      icon: "📝"

    - name: cc-spec-clarify
      version: "1.0.0"
      stage: 2
      description: "clarify 阶段，CC↔CX 讨论或用户审查"
      icon: "🔍"

    - name: cc-spec-plan
      version: "1.0.0"
      stage: 3
      description: "plan 阶段，用户确认后生成 tasks.yaml"
      icon: "📋"

    - name: cc-spec-apply
      version: "1.0.0"
      stage: 4
      description: "apply 阶段，使用 SubAgent 执行任务"
      icon: "🚀"

    - name: cc-spec-accept
      version: "1.0.0"
      stage: 5
      description: "accept 阶段，端到端验收"
      icon: "✅"

    - name: cc-spec-archive
      version: "1.0.0"
      stage: 6
      description: "archive 阶段，归档变更"
      icon: "📦"

  # 辅助 Commands
  auxiliary:
    - name: cc-spec:init
      version: "1.0.0"
      description: "初始化/更新知识库（RAG）"

    - name: cc-spec:list
      version: "1.0.0"
      description: "列出变更、任务、规格或归档"

    - name: cc-spec:goto
      version: "1.0.0"
      description: "跳转到指定变更或任务"

    - name: cc-spec:quick-delta
      version: "1.0.0"
      description: "快速记录简单变更"

    - name: cc-spec:update
      version: "1.0.0"
      description: "更新配置与模板"

  # 用户 Commands（可编辑）
  user: []
  # 示例:
  # - name: my-deploy
  #   version: "1.0.0"
  #   source: "~/.cc-spec/commands/my-deploy.md"
  #   description: 自定义部署命令
  #   imported_from: "project-name"

# ============================================
# 触发规则配置
# ============================================
trigger_rules:
  # 全局触发设置
  settings:
    case_sensitive: false           # 关键词大小写敏感
    min_keyword_length: 2           # 最小关键词长度
    max_matches_per_prompt: 3       # 每次提示最多匹配数

  # 触发优先级（冲突时的选择顺序）
  priority_order:
    - workflow      # 工作流类最高优先级
    - execution     # 执行类次之
    - domain        # 领域类最低

  # 触发行为
  enforcement_levels:
    require: "强制激活，用户必须使用"
    suggest: "建议激活，用户可选择"
    silent: "静默加载，不通知用户"

# ============================================
# 项目安装状态（自动维护）
# ============================================
projects: {}
# 示例:
# "C:/develop/my-project":
#   initialized_at: "2025-12-24T10:00:00Z"
#   commands_version: "1.0.0"
#   skills_installed:
#     - cc-spec-workflow
#     - subagent-coordinator
#   custom_overrides: []
```

---

## 四、数据类型定义

### 4.1 Skill 类型

```typescript
interface Skill {
  name: string;                    // 唯一标识符
  version: string;                 // 语义化版本
  type: "workflow" | "domain" | "execution";
  description: string;             // 多行描述，用于触发匹配
  enabled: boolean;                // 是否启用
  source?: string;                 // 用户 Skill 的本地路径
  imported_from?: string;          // 导入来源项目
  imported_at?: string;            // 导入时间 ISO8601
  triggers: TriggerConfig;         // 触发规则
}

interface TriggerConfig {
  keywords: string[];              // 关键词列表
  patterns: string[];              // 正则表达式模式
}
```

### 4.2 Command 类型

```typescript
interface Command {
  name: string;                    // 命令名（如 cc-spec-specify）
  version: string;                 // 语义化版本
  stage?: number;                  // 工作流阶段（1-6）
  description: string;             // 命令描述
  icon?: string;                   // 显示图标
  source?: string;                 // 用户 Command 的文件路径
  imported_from?: string;          // 导入来源
}
```

### 4.3 项目状态类型

```typescript
interface ProjectState {
  initialized_at: string;          // 初始化时间
  commands_version: string;        // 安装的 Commands 版本
  skills_installed: string[];      // 已安装的 Skills 名称列表
  custom_overrides: string[];      // 项目自定义覆盖的配置
}
```

---

## 五、Skill 目录结构

### 5.1 标准 Skill 结构

```
skill-name/
├── SKILL.md              # 必需 - 核心指令文档
├── scripts/              # 可选 - 可执行脚本
│   ├── main.py
│   └── utils.sh
├── references/           # 可选 - 参考文档（按需加载）
│   ├── guide.md
│   └── examples.md
└── assets/               # 可选 - 输出资源
    └── template.md
```

### 5.2 SKILL.md Frontmatter 格式

```yaml
---
name: skill-name
version: "1.0.0"
type: workflow | domain | execution
description: |
  多行描述，包含触发短语。
  Use when user wants to "do something specific".
triggers:
  keywords:
    - keyword1
    - keyword2
  patterns:
    - "regex.*pattern"
dependencies:
  - other-skill-name
---

# Skill 正文内容

## 使用场景

...

## 执行步骤

...
```

---

## 六、渐进式加载策略

### 6.1 三层加载模式

| 层级 | 内容 | 大小限制 | 加载时机 |
|------|------|----------|----------|
| L1 元数据 | name + description | ~100 words | 始终在 context |
| L2 主体 | SKILL.md body | <5k words | Skill 触发时 |
| L3 资源 | references/ + scripts/ | 无限制 | 按需显式加载 |

### 6.2 加载流程

```
1. 启动时
   └── 加载所有 Skill 的 L1 元数据到 context

2. 用户输入
   └── 匹配 triggers → 找到候选 Skills
       └── 排序（priority_order）
           └── 取 top N（max_matches_per_prompt）

3. Skill 激活
   └── 加载 L2 SKILL.md body
       └── 注入到当前对话 context

4. 需要深度信息
   └── 显式请求加载 L3 资源
       └── 使用 Read 工具读取 references/
```

---

## 七、触发匹配算法

### 7.1 匹配流程

```python
def match_skills(user_prompt: str, skills: list[Skill]) -> list[Skill]:
    matches = []

    for skill in skills:
        if not skill.enabled:
            continue

        score = 0

        # 关键词匹配
        for keyword in skill.triggers.keywords:
            if keyword.lower() in user_prompt.lower():
                score += 10

        # 正则匹配
        for pattern in skill.triggers.patterns:
            if re.search(pattern, user_prompt, re.IGNORECASE):
                score += 20

        if score > 0:
            matches.append((skill, score))

    # 按分数排序，再按类型优先级排序
    matches.sort(key=lambda x: (-x[1], priority_order.index(x[0].type)))

    return [m[0] for m in matches[:max_matches_per_prompt]]
```

### 7.2 优先级规则

1. **分数优先** - 匹配分数高的优先
2. **类型次之** - workflow > execution > domain
3. **用户优先** - 同名时用户 Skill 覆盖内置

---

## 八、与项目的交互

### 8.1 安装到项目

```bash
# 安装 Commands 到项目
cc-spec commands install
# → .claude/commands/cc-spec-*.md

# 安装 Skills 到项目
cc-spec skills install
# → .claude/skills/cc-spec-workflow/
# → .codex/skills/cc-spec-workflow/  (Codex 兼容)
```

### 8.2 从项目导出

```bash
# 导出项目 Skill 到用户库
cc-spec skills export my-custom-skill
# → ~/.cc-spec/skills/my-custom-skill/
# → 更新 tools.yaml 的 skills.user[]
```

### 8.3 同步状态

```bash
# 检查项目与 tools.yaml 的差异
cc-spec status
# → 显示版本差异、缺失的 Skills/Commands
```

---

## 九、UI 集成（cc-spec-tool）

### 9.1 Skills 管理页面功能

```
┌─────────────────────────────────────────────────────────────┐
│  Skills 管理                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  【内置 Skills】                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ☑ cc-spec-workflow      v1.0.0  workflow   已安装       ││
│  │ ☑ subagent-coordinator  v1.0.0  execution  已安装       ││
│  │ ☑ delta-tracker         v1.0.0  domain     需更新       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  【用户 Skills】                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ☑ my-code-review        v1.0.0  domain     已安装       ││
│  │   来源: project-a  导入于: 2025-12-24                    ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [+ 导入 Skill]  [刷新状态]  [安装选中]  [卸载选中]          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 触发规则编辑器

```
┌─────────────────────────────────────────────────────────────┐
│  触发规则编辑 - cc-spec-workflow                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  类型: [workflow ▼]    优先级: [high ▼]                      │
│                                                              │
│  关键词:                                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ cc-spec | 变更流程 | 需求分析 | proposal | clarify  [+] ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  正则模式:                                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ (specify|plan|apply|checklist|archive)              [+] ││
│  │ 变更.*流程                                           [+] ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  测试匹配: [输入测试文本...]                                  │
│  匹配结果: ✅ 命中 2 个关键词, 1 个模式                       │
│                                                              │
│  [保存]  [重置]  [取消]                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 十、迁移与兼容

### 10.1 从旧版本迁移

```yaml
# 旧版本（如果存在）
# ~/.cc-spec/config.yaml → ~/.cc-spec/tools.yaml

migration:
  from_version: "0.1.x"
  to_version: "0.2.1"
  steps:
    - "备份旧配置"
    - "合并 Skills 配置"
    - "迁移项目状态"
    - "清理废弃字段"
```

### 10.2 Codex 兼容

```
# Skills 安装时同时写入两个位置
.claude/skills/skill-name/    # Claude Code
.codex/skills/skill-name/     # Codex CLI

# 触发规则共享
skill-rules.json 与 tools.yaml 保持同步
```

---

## 十一、实现计划

### Phase 1: 基础结构
- [x] 定义 Rust 数据结构（ToolsConfig, Skill, Command）✅ 2025-12-24
- [x] 实现 tools.yaml 读写 ✅ 2025-12-24
- [x] 实现配置迁移逻辑 ✅ 2025-12-24

### Phase 2: Skills 管理
- [x] 实现 Skill 目录扫描 ✅ 2025-12-24
- [x] 实现触发匹配算法 ✅ 2025-12-24
- [x] 实现渐进式加载 ✅ 2025-12-24

### Phase 3: UI 集成
- [ ] Skills 管理页面组件
- [ ] 触发规则编辑器
- [ ] 项目状态同步显示

### Phase 4: 高级功能
- [ ] Skill 导入/导出
- [ ] 版本检查与更新
- [ ] 多项目状态管理
