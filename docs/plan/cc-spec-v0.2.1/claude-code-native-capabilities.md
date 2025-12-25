# Claude Code 原生能力参考文档

本文档整理 Claude Code 的核心原生能力，供 cc-spec 项目设计和开发参考。

---

## 1. Agent Skills 机制

### 1.1 什么是 Skill？

Skill 是**指令集**（不是工具），用于向 Claude 提供域特定知识和工作流程。Claude 会根据 `description` 自动判断何时使用。

### 1.2 存放位置

| 作用域 | 路径 |
|--------|------|
| 用户级 | `~/.claude/skills/skill-name/SKILL.md` |
| 项目级 | `.claude/skills/skill-name/SKILL.md` |

### 1.3 SKILL.md 格式规范

```yaml
---
name: your-skill-name          # 必需：小写+数字+连字符，最多64字符
description: 简明描述及触发条件  # 必需：说清楚什么时候用，最多1024字符
allowed-tools: Read, Grep, Glob # 可选：限制工具访问（不指定则继承全部）
---

# Skill 名称

## Instructions
清晰的逐步指导。

## Examples
具体示例代码。
```

### 1.4 Skill 目录结构

```
my-skill/
├── SKILL.md              # 必需
├── reference.md          # 可选文档
├── examples.md           # 可选示例
├── scripts/
│   └── helper.py         # 可选脚本
└── templates/
    └── template.txt      # 可选模板
```

Claude 会按需读取这些文件（渐进式披露），不会一次性全部加载。

### 1.5 关键限制

- **Skill 不等于 Tool**：不能接收参数或返回结构化数据
- **Skill 是自动调用的**：Claude 根据 description 自动决定何时使用
- **脚本调用用 Bash**：Skill 里的脚本需要通过 Bash 工具调用

---

## 2. SubAgent 系统

### 2.1 内置 SubAgent 类型

| 类型 | 模型 | 工具 | 用途 |
|------|------|------|------|
| `general-purpose` | Sonnet | 全部 | 复杂多步骤任务 |
| `Plan` | Sonnet | Read, Glob, Grep, Bash（只读） | 规划模式 |
| `Explore` | Haiku | 只读工具 | 快速代码库探索 |

### 2.2 自定义 SubAgent

**存放位置**：
- 项目级：`.claude/agents/agent-name.md`
- 用户级：`~/.claude/agents/agent-name.md`

**格式**：
```markdown
---
name: code-reviewer
description: 代码审查专家。检查代码质量、安全问题。
tools: Read, Grep, Glob, Bash, Edit  # 可选
model: opus                           # 可选：sonnet/opus/haiku/inherit
permissionMode: default               # 可选
skills: skill1, skill2                # 可选：自动加载的 Skills
---

你是资深代码审查员，关注代码质量和安全。

## 审查清单
1. 代码清晰度
2. 错误处理
3. 性能考量
```

### 2.3 并发限制

- 最多 **10 个并发 SubAgent**
- 每个 SubAgent 有独立上下文窗口
- SubAgent **不能嵌套**（不能创建其他 SubAgent）

---

## 3. MCP Server 集成

### 3.1 什么是 MCP？

Model Context Protocol - 标准化的 AI 工具集成协议，用于连接外部系统。

### 3.2 安装方式

**HTTP 服务器**（推荐）：
```bash
claude mcp add --transport http notion https://mcp.notion.com/mcp
```

**Stdio 服务器**（本地进程）：
```bash
claude mcp add --transport stdio airtable \
  --env AIRTABLE_API_KEY=YOUR_KEY \
  -- npx -y airtable-mcp-server

# Windows 需要 cmd /c 包装
claude mcp add --transport stdio myserver -- cmd /c npx -y @some/package
```

### 3.3 作用域

```bash
# 本地作用域（.claude.json）
claude mcp add --scope local <name> <url>

# 项目作用域（.mcp.json，检入版控）
claude mcp add --scope project <name> <url>

# 用户作用域（~/.claude.json）
claude mcp add --scope user <name> <url>
```

**优先级**：Local > Project > User

### 3.4 MCP vs Skill 对比

| 特性 | Skill | MCP |
|------|-------|-----|
| 本质 | 指令集 | 工具/资源集 |
| 调用 | 模型自动 | 工具调用 |
| 扩展 | Claude 内部能力 | 外部系统集成 |
| 适用 | 域特定知识、工作流程 | 数据库、GitHub、Slack 等 |

---

## 4. 文件操作与上下文管理

### 4.1 原生能力

- **没有原生代码库索引**：需要自建（如 cc-spec KB）
- **@ 引用直接加载文件**：会占用上下文
- **上下文窗口**：标准 Sonnet 200K token

### 4.2 处理大量文件的策略

**1. 使用 Explore SubAgent**
```
用 Explore subagent 找出所有处理认证的文件
```
快速（用 Haiku），只读，不污染主对话上下文。

**2. 逐步加载**
```
1. 首先给我代码架构概览
2. 然后分析认证模块的核心文件
3. 最后解释它如何与数据库交互
```

**3. 使用 Glob 和 Grep**
```bash
# 找出匹配模式的文件
glob: **/*.auth.ts

# 搜索关键字符串
grep: "export.*authenticate" --type ts
```

### 4.3 上下文管理策略

| 策略 | 说明 |
|------|------|
| SubAgent 隔离 | 每个 SubAgent 独立上下文 |
| Prompt Caching | 自动缓存大型文件 |
| 渐进式披露 | Skill 文件按需加载 |
| 1M Token 模式 | `/model sonnet[1m]` |

---

## 5. 多模型支持

### 5.1 可用模型

| 别名 | 模型 | 用途 |
|------|------|------|
| `sonnet` | Sonnet 4.5 | 日常编码 |
| `opus` | Opus 4.5 | 复杂推理 |
| `haiku` | Haiku | 快速任务（SubAgent 默认） |
| `opusplan` | Opus（规划）+ Sonnet（执行） | 混合模式 |

### 5.2 切换模型

```bash
# 启动时指定
claude --model opus

# 会话中切换
/model sonnet

# 环境变量
export ANTHROPIC_MODEL=opus
```

### 5.3 多模型协作模式

**1. opusplan 混合模式**
```
/model opusplan
> 设计复杂架构    # Opus 规划
> 实现这个方案    # 自动切 Sonnet 执行
```

**2. SubAgent 模型分离**
```markdown
---
name: architect
model: opus          # 复杂分析用 Opus
---
```

```markdown
---
name: explorer
model: haiku         # 快速搜索用 Haiku
---
```

---

## 6. 对 cc-spec 的设计启示

### 6.1 KB 系统的价值

Claude Code **没有原生代码库索引**，cc-spec 的 KB 系统正好填补这个空白：
- 向量检索提供语义相关的上下文
- 减少上下文占用
- 支持增量更新

### 6.2 Skill vs 命令模板

| 场景 | 推荐方式 |
|------|---------|
| 工作流指令（如 5-Phase 协作） | Skill（SKILL.md） |
| 具体命令执行 | 命令模板（init_template.py） |
| 调用外部脚本 | Bash 工具 |

### 6.3 调用 Codex 的正确方式

**不是用 Skill**，而是用 Bash：
```bash
python .cc-spec/scripts/codex_bridge.py \
  --cd "." \
  --PROMPT "..." \
  --SANDBOX workspace-write
```

Skill 用于提供工作流指令，Bash 用于实际执行脚本。

### 6.4 init 阶段的设计

由于上下文限制，init 时 Claude 做语义切片需要：
1. 分批读取文件（每批 10-20 个）
2. 输出 chunks JSON
3. 调用 `cc-spec kb import` 导入
4. 循环处理

或者使用基于规则的切片（不依赖 LLM）。

---

## 参考资料

- [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [cc-spec 项目 CLAUDE.md](../CLAUDE.md)
