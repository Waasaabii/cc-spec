"""Standards templates and defaults for SKILL.md / AGENTS.md generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


MANAGED_START = "<!-- CC-SPEC:START -->"
MANAGED_END = "<!-- CC-SPEC:END -->"


@dataclass(frozen=True)
class Artifact:
    type: str
    description: str


# ---------------------------------------------------------------------------
# Template strings (mirror docs/plan/cc-spec-v0.1.8/base-template.yaml mapping)
# ---------------------------------------------------------------------------

SKILL_MD_TEMPLATE = """# cc-spec Standards (for Claude)

## 角色定位
{claude.role.rules}

## 产出物
{claude.outputs.artifacts}

### 禁止产出
{claude.outputs.forbidden}

## 工作流程
{claude.workflow.phases}

## 项目编码规范
{project.coding_rules}

## KB 规则
### 写入规则
{claude.kb_write_rules.rules}
"""


AGENTS_MD_TEMPLATE = """# AGENTS.md (for Codex)

## 角色定位
{codex.role.rules}

## 产出物
{codex.outputs.artifacts}

### 禁止产出
{codex.outputs.forbidden}

## 执行规则
{codex.execution_rules.rules}

## 项目编码规范
{project.coding_rules}

## 命令说明
{codex.commands.list}
"""


# ---------------------------------------------------------------------------
# Defaults (extracted from base-template.yaml)
# ---------------------------------------------------------------------------

CLAUDE_ROLE_RULES = [
    "作为主控 Agent（Orchestrator），负责需求分析和任务编排",
    "负责将需求/上下文写入 KB，供 Codex 读取",
    "不直接编写业务代码，代码实现由 Codex 完成",
    "负责审核 Codex 的执行结果，处理异常情况",
]

CLAUDE_OUTPUTS = [
    Artifact("proposal.md", "变更提案（需求描述、影响范围、技术方案）"),
    Artifact("tasks.yaml", "任务拆分（Wave/Task 结构、依赖关系、检查清单）"),
    Artifact("config.yaml", "项目配置（工具选项、打分阈值、KB 策略）"),
    Artifact("base-template.yaml", "规范模板（编码规范、架构约束、安全规则）"),
    Artifact("KB records", "工作流记录（需求摘要、任务上下文、执行结果）"),
]

CLAUDE_FORBIDDEN = [
    "业务代码（.py, .ts, .js 等）",
    "测试代码（test_*.py, *.spec.ts 等）",
    "配置代码（除 cc-spec 相关的 yaml 外）",
]

CLAUDE_WORKFLOW_PHASES = [
    {
        "phase": 1,
        "name": "需求分析与 KB 写入",
        "actor": "Claude",
        "actions": [
            "阅读 proposal.md 和 tasks.yaml，理解任务目标",
            "将任务摘要/需求要点写入 KB",
            "cc-spec kb record --step apply --change \"{change_name}\" --task-id \"{task_id}\" --notes \"{task_summary}\"",
        ],
    },
    {
        "phase": 2,
        "name": "调用 Codex 执行",
        "actor": "Claude → Codex",
        "actions": [
            "cc-spec apply --change \"{change_name}\"",
            "SubAgentExecutor 自动检索 KB 并注入上下文",
        ],
    },
    {
        "phase": 3,
        "name": "结果审核",
        "actor": "Claude",
        "actions": [
            "检查 tasks.yaml 中的任务状态",
            "失败任务分析原因并决定是否重试",
            "必要时补充 KB 并重新执行",
        ],
    },
]

CLAUDE_KB_WRITE_RULES = [
    "需求分析完成后，必须将任务摘要写入 KB",
    "使用 cc-spec kb record 记录工作流步骤",
    "复杂需求拆解为多个 KB 条目，便于 Codex 检索",
    "写入内容包括：任务目标、技术要点、约束条件、参考文件",
]


CODEX_ROLE_RULES = [
    "作为执行 Agent，负责实际的代码编写和修改",
    "从 KB 获取上下文（需求 + 代码），理解任务目标",
    "直接执行任务，修改代码文件",
    "遵循项目规范，输出高质量代码",
]

CODEX_OUTPUTS = [
    Artifact("业务代码", "功能实现（.py, .ts, .js, .go 等）"),
    Artifact("测试代码", "单元测试、集成测试（test_*.py, *.spec.ts 等）"),
    Artifact("配置文件", "应用配置（非 cc-spec 相关）"),
    Artifact("数据库迁移", "Schema 变更（migrations/）"),
]

CODEX_FORBIDDEN = [
    "cc-spec 规范文件（proposal.md, tasks.yaml, base-template.yaml）",
    "KB 记录（由 Claude 通过 cc-spec kb record 写入）",
    "工作流状态文件（status.yaml）",
]

CODEX_EXECUTION_RULES = [
    "严格按照 prompt 中的任务要求执行",
    "遵循项目编码规范（从 KB 上下文获取）",
    "最小作用域，只改需求范围内的代码",
    "不擅自扩展需求范围",
]


CODEX_COMMANDS = [
    {"name": "specify", "description": "创建新的变更规格说明", "usage": "cc-spec specify <变更名称>"},
    {"name": "clarify", "description": "审查任务并标记需要返工的内容", "usage": "cc-spec clarify"},
    {"name": "plan", "description": "从提案生成执行计划", "usage": "cc-spec plan"},
    {"name": "apply", "description": "使用 SubAgent 并行执行任务", "usage": "cc-spec apply"},
    {"name": "checklist", "description": "使用检查清单评分验证任务完成情况", "usage": "cc-spec checklist"},
    {"name": "archive", "description": "归档已完成的变更", "usage": "cc-spec archive"},
    {"name": "quick-delta", "description": "快速模式，一步创建并归档简单变更", "usage": "cc-spec quick-delta <变更名称> \"<变更描述>\""},
    {"name": "list", "description": "列出变更、任务、规格或归档", "usage": "cc-spec list [changes|tasks|specs|archives]"},
    {"name": "goto", "description": "导航到特定变更或任务", "usage": "cc-spec goto <变更名称>"},
    {"name": "update", "description": "更新配置、命令或模板", "usage": "cc-spec update [config|commands|templates]"},
    {
        "name": "kb",
        "description": "KB（向量库）相关命令",
        "subcommands": [
            {"name": "kb init", "description": "全量构建 KB"},
            {"name": "kb update", "description": "增量更新 KB"},
            {"name": "kb query", "description": "向量检索"},
            {"name": "kb context", "description": "输出格式化上下文"},
        ],
    },
]


def format_rules(lines: Iterable[str]) -> str:
    items = [str(x).strip() for x in lines if str(x).strip()]
    if not items:
        return "- (none)"
    return "\n".join(f"- {item}" for item in items)


def format_artifacts(artifacts: Iterable[Artifact]) -> str:
    items = [a for a in artifacts if a.type.strip()]
    if not items:
        return "- (none)"
    return "\n".join(f"- **{a.type}**：{a.description}" for a in items)


def format_workflow(phases: list[dict]) -> str:
    if not phases:
        return "- (none)"
    lines: list[str] = []
    for phase in phases:
        name = phase.get("name", "")
        actor = phase.get("actor", "")
        header = f"- **{name}**"
        if actor:
            header = f"{header}（{actor}）"
        lines.append(header)
        actions = phase.get("actions", []) or []
        for action in actions:
            action_line = str(action).strip()
            if not action_line:
                continue
            lines.append(f"  - {action_line}")
    return "\n".join(lines)


def format_commands(commands: list[dict]) -> str:
    if not commands:
        return "- (none)"
    lines: list[str] = []
    for cmd in commands:
        name = cmd.get("name", "")
        desc = cmd.get("description", "")
        usage = cmd.get("usage", "")
        if name:
            line = f"- **{name}**：{desc}".rstrip("：")
            lines.append(line)
        if usage:
            lines.append(f"  - `{usage}`")
        subcommands = cmd.get("subcommands", []) or []
        for sub in subcommands:
            sub_name = sub.get("name", "")
            sub_desc = sub.get("description", "")
            if sub_name:
                lines.append(f"  - `{sub_name}`：{sub_desc}".rstrip("："))
    return "\n".join(lines)
