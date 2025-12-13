"""clarify 命令的模板实现。

该模块为 clarify 命令提供完整的模板内容，包括：
- 命令大纲说明
- 执行步骤详细指引
- 验证检查清单
- 9 大歧义分类指南
"""

from ..ambiguity import AmbiguityType
from ..ambiguity.detector import get_keywords_by_type, get_type_description
from .base import CommandTemplate, CommandTemplateContext


class ClarifyTemplate(CommandTemplate):
    """clarify 命令的模板实现。

    该命令用于审查提案文档，识别歧义和模糊描述，生成澄清问题供用户确认。
    """

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取 clarify 命令的大纲描述。"""
        return """clarify 命令用于**审查提案文档**，识别其中的歧义和模糊描述。

该命令会：
1. 扫描 proposal.md 文档内容
2. 运行 9 大歧义分类检测（SCOPE, DATA_STRUCTURE, INTERFACE,
   VALIDATION, ERROR_HANDLING, PERFORMANCE, SECURITY, DEPENDENCY, UX）
3. 将检测到的歧义按类型分组，生成结构化的问题列表
4. 以表格形式展示问题和建议选项
5. 等待用户确认或提供详细答案
6. 根据用户反馈更新 proposal.md，解决歧义

**重要原则：**
- 优先识别高优先级歧义（数据结构、接口、验证）
- 为每个歧义提供具体的澄清建议和可选方案
- 使用清晰的表格格式展示问题（类型 | 位置 | 问题描述 | 建议选项）
- 确保所有高优先级歧义都得到解决
- 更新后的 proposal.md 应该明确、无歧义
"""

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 clarify 命令的执行步骤。"""
        return [
            "读取 `.cc-spec/changes/<change-name>/proposal.md` 文件的完整内容",
            (
                "调用歧义检测模块，扫描 proposal.md 内容："
                "使用 `AMBIGUITY_KEYWORDS` 进行关键词匹配"
            ),
            (
                "分析检测结果，按 9 种歧义类型分组：SCOPE, DATA_STRUCTURE, "
                "INTERFACE, VALIDATION, ERROR_HANDLING, PERFORMANCE, "
                "SECURITY, DEPENDENCY, UX"
            ),
            (
                "对每种检测到的歧义类型，生成具体的澄清问题："
                "包括歧义位置（行号）、原文内容、问题描述、建议选项"
            ),
            (
                "以表格形式展示所有歧义问题：\n"
                "   - 列：类型 | 行号 | 原文片段 | 问题描述 | 建议选项\n"
                "   - 按优先级排序：高优先级类型"
                "（DATA_STRUCTURE, INTERFACE, VALIDATION）优先展示"
            ),
            (
                "等待用户确认或提供详细答案：\n"
                "   - 用户可以选择建议选项\n"
                "   - 用户可以提供自定义答案\n"
                '   - 用户可以标记为"暂不处理"'
            ),
            (
                "根据用户反馈更新 proposal.md：\n"
                "   - 将澄清后的内容替换原有的模糊描述\n"
                "   - 保持文档结构和格式\n"
                "   - 删除所有 TODO 标记和占位符"
            ),
            (
                "验证更新后的 proposal.md：\n"
                "   - 重新运行歧义检测，确认高优先级歧义已解决\n"
                "   - 检查是否存在遗留的 TODO 或占位符\n"
                "   - 确保文档的完整性和一致性"
            ),
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 clarify 命令的验证检查清单。"""
        return [
            "已成功读取 proposal.md 文件",
            "歧义检测已执行，生成了歧义匹配结果列表",
            "所有检测到的歧义已按类型分组并展示给用户",
            "所有高优先级歧义（DATA_STRUCTURE, INTERFACE, VALIDATION）已得到解决",
            "proposal.md 已根据用户反馈更新",
            "更新后的 proposal.md 中无遗留的 TODO 或占位符",
            "重新运行歧义检测，确认高优先级歧义数量显著减少或为零",
            "文档结构和格式保持完整，无格式错误",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取 9 大歧义分类的详细说明和示例。"""
        guidelines = [
            "## 9 大歧义分类指南",
            "",
            (
                "clarify 命令使用 9 种歧义分类来系统化地识别提案文档中的"
                "模糊描述。以下是各类型的详细说明："
            ),
            "",
            "### 歧义分类表",
            "",
            "| 类型 | 说明 | 典型关键词（中文） | 典型关键词（英文） |",
            "|------|------|-------------------|-------------------|",
        ]

        # 为每种歧义类型生成表格行
        for ambiguity_type in AmbiguityType:
            keywords = get_keywords_by_type(ambiguity_type)
            cn_keywords = [k for k in keywords if any('\u4e00' <= c <= '\u9fff' for c in k)][:5]
            en_keywords = [k for k in keywords if not any('\u4e00' <= c <= '\u9fff' for c in k)][:5]

            type_desc = get_type_description(ambiguity_type)
            # 提取描述的简短版本（去掉具体说明）
            short_desc = type_desc.split(" - ")[0] if " - " in type_desc else type_desc

            guidelines.append(
                f"| **{ambiguity_type.value.upper()}** | {short_desc} | "
                f"{', '.join(cn_keywords)} | {', '.join(en_keywords)} |"
            )

        guidelines.extend([
            "",
            "### 优先级说明",
            "",
            "**高优先级**（必须在 clarify 阶段解决）：",
            "- **DATA_STRUCTURE**：影响后续代码实现的数据模型设计",
            "- **INTERFACE**：影响模块间通信和 API 设计",
            "- **VALIDATION**：影响输入校验和业务规则",
            "",
            "**中优先级**（建议在 clarify 阶段解决）：",
            "- **ERROR_HANDLING**：影响系统稳定性和容错能力",
            "- **SECURITY**：影响系统安全性和数据保护",
            "- **SCOPE**：影响功能边界和工作量评估",
            "",
            "**低优先级**（可以在 plan 阶段解决）：",
            "- **PERFORMANCE**：可以在实现时优化",
            "- **DEPENDENCY**：可以在技术选型时确定",
            "- **UX**：可以在详细设计时完善",
            "",
            "### 澄清问题格式",
            "",
            "对于每个检测到的歧义，应该生成以下格式的澄清问题：",
            "",
            "```",
            "【类型】: INTERFACE",
            "【位置】: proposal.md 第 42 行",
            "【原文】: \"系统需要提供接口来处理用户请求\"",
            "【问题】: 接口的具体设计不明确",
            "【建议】:",
            "  A. RESTful API (HTTP POST /api/users/request)",
            "  B. GraphQL API (mutation submitRequest)",
            "  C. gRPC 服务接口",
            "  D. 其他（请说明）",
            "```",
            "",
            "### 更新文档的原则",
            "",
            "1. **精确替换**：仅替换包含歧义的句子，保持其他内容不变",
            "2. **保持格式**：维持原有的 Markdown 格式（标题层级、列表、代码块等）",
            "3. **增加细节**：用用户提供的详细信息替换模糊描述",
            "4. **移除标记**：删除所有 TODO、TBD、待定等临时标记",
            "5. **验证完整性**：确保更新后的章节逻辑完整、前后一致",
        ])

        return "\n".join(guidelines)
