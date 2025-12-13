# 命令参考

## 全局选项

所有命令都支持以下全局选项：

```bash
cc-spec --version    # 显示版本号
cc-spec --help       # 显示帮助信息
```

---

## init

初始化 cc-spec 项目结构。

### 用法

```bash
cc-spec init [OPTIONS]
```

### 选项

| 选项 | 说明 |
|------|------|
| `--force`, `-f` | 强制覆盖已存在的配置 |
| `--agent`, `-a` | v1.2: 指定默认 AI 工具 (如 claude, cursor, gemini) |

### 示例

```bash
# 初始化项目
cc-spec init

# 强制重新初始化
cc-spec init --force

# 指定 AI 工具 (v1.2)
cc-spec init --agent gemini

# 指定项目名和工具
cc-spec init my-project --agent cursor
```

### 说明

- 创建 `.cc-spec/` 目录结构
- 下载或复制模板文件
- 生成默认 `config.yaml`
- 自动检测 AI 工具类型

---

## specify

创建新的变更规范。

### 用法

```bash
cc-spec specify <CHANGE_NAME>
```

### 参数

| 参数 | 说明 |
|------|------|
| `CHANGE_NAME` | 变更名称 (必须是有效的目录名) |

### 示例

```bash
# 创建新变更
cc-spec specify add-user-auth

# 创建带连字符的变更名
cc-spec specify fix-login-bug
```

### 说明

- 创建 `.cc-spec/changes/<name>/` 目录
- 生成 `proposal.md` 模板
- 初始化 `status.yaml` 状态文件
- 变更名称必须唯一

---

## clarify

查看任务列表或标记任务需要返工。

### 用法

```bash
cc-spec clarify [TASK_ID]
```

### 参数

| 参数 | 说明 |
|------|------|
| `TASK_ID` | (可选) 需要返工的任务 ID |

### 示例

```bash
# 查看所有任务
cc-spec clarify

# 标记任务需要返工
cc-spec clarify 01-SETUP
```

### 说明

- 无参数时显示当前变更的任务列表
- 指定任务 ID 时进入返工模式
- 显示任务状态和执行历史

---

## plan

生成任务计划。

### 用法

```bash
cc-spec plan <CHANGE_NAME>
```

### 参数

| 参数 | 说明 |
|------|------|
| `CHANGE_NAME` | 变更名称 |

### 示例

```bash
cc-spec plan add-user-auth
```

### 说明

- 读取 `proposal.md` 内容
- 生成 `tasks.md` (Wave 分组格式)
- 生成 `design.md` (技术决策)
- 验证依赖关系合法性
- 更新状态到 PLAN 阶段

---

## apply

执行任务 (SubAgent 并发)。

### 用法

```bash
cc-spec apply [CHANGE_NAME] [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `CHANGE_NAME` | (可选) 变更名称，默认使用当前变更 |

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--max-concurrent`, `-c` | 最大并发数 | 3 |
| `--timeout`, `-t` | 任务超时时间 (毫秒) | 300000 |
| `--resume`, `-r` | 从失败处继续执行 | false |
| `--dry-run` | 仅预览，不实际执行 | false |

### 示例

```bash
# 执行任务
cc-spec apply add-user-auth

# 设置并发数
cc-spec apply add-user-auth --max-concurrent 5

# 从失败处继续
cc-spec apply add-user-auth --resume

# 预览模式
cc-spec apply add-user-auth --dry-run
```

### 说明

- 按 Wave 顺序执行任务
- 同一 Wave 内的任务并发执行
- 实时显示执行进度
- 支持断点续传
- 失败任务会中断后续 Wave

---

## checklist

验证任务完成情况。

### 用法

```bash
cc-spec checklist <CHANGE_NAME> [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `CHANGE_NAME` | 变更名称 |

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--threshold` | 通过阈值 (百分比) | 100 |

### 示例

```bash
# 验证 checklist
cc-spec checklist add-user-auth

# 设置 80% 通过阈值
cc-spec checklist add-user-auth --threshold 80
```

### 说明

- 解析 `tasks.md` 中的 checklist 项
- 计算完成得分
- 通过时更新状态到 CHECKLIST
- 失败时生成详细报告

---

## archive

归档已完成的变更。

### 用法

```bash
cc-spec archive <CHANGE_NAME> [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `CHANGE_NAME` | 变更名称 |

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--no-confirm` | 跳过确认提示 | false |

### 示例

```bash
# 归档变更
cc-spec archive add-user-auth

# 跳过确认
cc-spec archive add-user-auth --no-confirm
```

### 说明

- 检查 checklist 是否通过
- 显示将更新的 specs 列表
- 执行 Delta 合并
- 移动到 `archive/YYYY-MM-DD-{name}/`

---

## quick-delta

快速创建并归档小型变更。

### 用法

```bash
cc-spec quick-delta <DESCRIPTION>
```

### 参数

| 参数 | 说明 |
|------|------|
| `DESCRIPTION` | 变更描述 |

### 示例

```bash
# 快速修复
cc-spec quick-delta "Fix typo in README"

# 小型功能
cc-spec quick-delta "Add loading spinner to button"
```

### 说明

- 自动生成时间戳变更名
- 创建简化版 proposal (mini-proposal)
- 直接归档到 `archive/`
- 适合小型、快速的修改

---

## list

列出变更、任务、规范或归档 (v1.1+)。

### 用法

```bash
cc-spec list <TARGET> [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `TARGET` | 列出目标: changes, tasks, specs, archive |

### 选项

| 选项 | 说明 |
|------|------|
| `-c`, `--change` | 指定变更 ID (用于 tasks) |

### 示例

```bash
# 列出所有变更
cc-spec list changes

# 列出指定变更的任务
cc-spec list tasks -c C-001

# 列出所有规范
cc-spec list specs

# 列出归档
cc-spec list archive
```

---

## goto

导航到变更或任务 (v1.1+)。

### 用法

```bash
cc-spec goto <ID> [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `ID` | 变更 ID (如 C-001) 或任务 ID (如 C-001:02-MODEL) |

### 选项

| 选项 | 说明 |
|------|------|
| `-f`, `--force` | 强制导航，忽略状态检查 |
| `-x`, `--execute` | v1.2: 直接执行选择的命令 |

### 示例

```bash
# 导航到变更
cc-spec goto C-001

# 导航到任务
cc-spec goto C-001:02-MODEL

# 导航并执行选择的命令 (v1.2)
cc-spec goto C-001 --execute
```

### 说明

- 显示变更/任务的详细信息面板
- 提供上下文相关的操作选项
- v1.2: 使用 `--execute` 可直接执行选择的命令

---

## update

更新配置、斜杠命令或模板 (v1.1+)。

### 用法

```bash
cc-spec update [TARGET] [OPTIONS]
```

### 参数

| 参数 | 说明 |
|------|------|
| `TARGET` | 更新目标: commands, subagent, agents, all |

### 选项

| 选项 | 说明 |
|------|------|
| `-a`, `--add-agent` | 添加 AI 工具支持 (可多次使用) |
| `-t`, `--templates` | v1.2: 更新模板到最新版本 |
| `-f`, `--force` | 强制覆盖 |

### 示例

```bash
# 更新所有配置
cc-spec update

# 只更新斜杠命令
cc-spec update commands

# 添加 Gemini 支持
cc-spec update --add-agent gemini

# 添加多个工具 (v1.2)
cc-spec update --add-agent gemini --add-agent cody

# 更新模板 (v1.2)
cc-spec update --templates

# 查看可用工具
cc-spec update agents
```

### 支持的 AI 工具 (v1.2: 17 种)

**原有 9 种:** claude, cursor, gemini, copilot, amazonq, windsurf, qwen, codeium, continue

**v1.2 新增 8 种:** tabnine, aider, devin, replit, cody, supermaven, kilo, auggie

---

## 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 一般错误 |
| 2 | 参数错误 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `CC_SPEC_CONFIG` | 自定义配置文件路径 |
| `CC_SPEC_TEMPLATES` | 自定义模板目录路径 |
| `CC_SPEC_NO_COLOR` | 禁用颜色输出 |
