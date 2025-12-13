"""specify 命令的模板实现。

该模板用于生成 specify 命令的完整工作流指令，包括：
- 创建新的变更规格说明
- 从用户描述中提取功能要点
- 生成 proposal.md 文件
"""

from .base import CommandTemplate, CommandTemplateContext


class SpecifyTemplate(CommandTemplate):
    """specify 命令的模板实现。

    该模板指导 AI 工具完成变更规格说明的创建，包括名称生成、
    目录结构创建、proposal.md 填充和质量验证。
    """

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取 specify 命令的大纲描述。

        参数：
            ctx: 模板渲染上下文

        返回：
            大纲文本（Markdown 格式）
        """
        return """创建新的变更规格说明（Specification）。

本命令负责将用户的功能需求转化为结构化的变更提案：
- 从自然语言描述中提取核心要点
- 生成符合规范的变更名称（action-noun 格式）
- 创建 proposal.md 文档，描述 WHY、WHAT、IMPACT
- 初始化变更状态追踪

**关键原则：**
- 关注业务价值（WHY）和具体改动（WHAT），避免实现细节（HOW）
- 面向业务人员和技术人员共同可读
- 每个需求必须可测试、可验证
"""

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 specify 命令的执行步骤列表。

        参数：
            ctx: 模板渲染上下文

        返回：
            执行步骤列表
        """
        return [
            (
                "**解析用户输入**：阅读用户提供的功能描述（$ARGUMENTS），"
                "理解核心需求和业务价值。如果描述不清晰，"
                "主动向用户提问澄清关键信息（背景、目标、影响范围）"
            ),
            (
                "**生成变更名称**：基于功能描述创建简洁的短名称"
                "（2-4 词，action-noun 格式，如 add-oauth、fix-auth-bug）。"
                "确保名称：(a) 以小写字母开头，(b) 仅包含小写字母、数字、连字符，"
                "(c) 长度 ≤64 字符，(d) 语义清晰，见名知意"
            ),
            (
                "**检查 Git 分支状态**：运行 `git branch` 和 `git status` "
                "检查当前仓库状态。如果已存在同名分支，提示用户选择新名称或"
                "使用已有 ID 编辑（`cc-spec specify C-XXX`）。"
                "如果工作区有未提交修改，建议用户先提交或暂存"
            ),
            (
                "**创建变更目录结构**：在 `.cc-spec/changes/{变更名称}/` 下创建目录。"
                "确认父目录 `.cc-spec/changes/` 存在，"
                "如不存在则报错提示用户运行 `cc-spec init`"
            ),
            (
                "**填充 proposal.md 模板**：基于用户描述填写 proposal.md，"
                "包含三个必填章节：\n"
                "   - **## Why**：说明背景、动机、要解决的问题（业务价值）\n"
                "   - **## What Changes**：列出具体改动内容"
                "（功能点、API 变更、配置修改等）\n"
                "   - **## Impact**：描述影响范围"
                "（受影响的规格文件、预期代码改动区域）\n"
                "   如果用户描述不足以填写某个章节，使用 `[NEEDS CLARIFICATION]` "
                "标记（最多 3 处），并在标记后说明需要澄清的具体问题"
            ),
            (
                "**执行规格质量验证**：检查 proposal.md 内容质量：\n"
                "(a) 三个必填章节均已填写且非空，\n"
                "(b) 每个改动点是否可测试（有明确的验收标准），\n"
                "(c) 避免过度技术细节（如具体函数名、代码结构），\n"
                "(d) `[NEEDS CLARIFICATION]` 标记 ≤3 处。\n"
                "如果验证失败，向用户说明问题并提供改进建议"
            ),
            (
                "**报告完成状态和下一步**：显示创建的文件路径"
                "（proposal.md、status.yaml）和分配的变更 ID（C-XXX）。"
                "提示用户下一步操作：\n"
                "(a) 编辑 proposal.md 补充细节，\n"
                "(b) 运行 `cc-spec clarify C-XXX` 进行歧义检测，\n"
                "(c) 运行 `cc-spec plan C-XXX` 生成执行任务"
            ),
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 specify 命令的验证检查清单。

        参数：
            ctx: 模板渲染上下文

        返回：
            验证项列表
        """
        return [
            "变更名称符合格式要求（小写字母开头，仅含小写字母/数字/连字符，长度 ≤64）",
            "proposal.md 已创建且文件大小 >0 字节",
            "proposal.md 包含三个必填章节：## Why、## What Changes、## Impact",
            "每个必填章节均有实质内容（非空，非仅占位符）",
            "`[NEEDS CLARIFICATION]` 标记数量 ≤3 处",
            "status.yaml 已初始化，current_stage 为 SPECIFY",
            "变更 ID（C-XXX）已分配并显示给用户",
            "Git 分支状态检查通过（无同名分支冲突）",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取 specify 命令的指南。

        参数：
            ctx: 模板渲染上下文

        返回：
            指南文本（Markdown 格式）
        """
        return """### 编写高质量 proposal.md 的指南

**关注 WHAT 和 WHY，避免 HOW：**
- ✅ **好**：添加 OAuth 2.0 登录支持，允许用户使用 GitHub 账号登录
- ❌ **差**：在 auth.py 中实现 OAuthHandler 类，使用 requests 库调用 GitHub API

**面向业务人员编写：**
- 使用业务术语而非技术黑话
- 说明功能的业务价值，而非技术实现细节
- 避免代码片段、类名、函数名等低层次信息

**每个需求必须可测试：**
- ✅ **好**：用户点击"GitHub 登录"按钮后，跳转到 GitHub 授权页面
- ❌ **差**：改进登录体验

**最多 3 个澄清标记：**
- 仅在关键信息缺失时使用 `[NEEDS CLARIFICATION]`
- 每个标记后必须说明需要澄清的具体问题
- 超过 3 处标记说明用户描述过于模糊，应主动提问澄清

**变更名称命名规范：**
- 动词-名词格式：add-feature、fix-bug、update-config、remove-deprecated
- 避免泛泛的名称：improve-performance → optimize-db-queries
- 避免版本号：v2-auth → migrate-auth-to-oauth
"""
