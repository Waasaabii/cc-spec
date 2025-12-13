"""歧义检测器的数据类和枚举定义。

该模块定义了歧义检测系统的核心数据结构：
- AmbiguityType: 9 种歧义分类枚举
- AmbiguityMatch: 歧义匹配结果数据类
- AMBIGUITY_KEYWORDS: 每种歧义类型的关键词映射
"""

from dataclasses import dataclass, field
from enum import Enum


class AmbiguityType(Enum):
    """歧义类型枚举。

    定义了 9 种可能的歧义分类，用于识别规格文档中需要澄清的内容。
    """

    SCOPE = "scope"
    """范围歧义：功能边界、模块范围、影响范围不明确"""

    DATA_STRUCTURE = "data_structure"
    """数据结构歧义：字段定义、类型、关联关系不明确"""

    INTERFACE = "interface"
    """接口歧义：API 设计、参数、返回值不明确"""

    VALIDATION = "validation"
    """验证歧义：输入校验规则、约束条件不明确"""

    ERROR_HANDLING = "error_handling"
    """错误处理歧义：异常处理、降级策略、重试逻辑不明确"""

    PERFORMANCE = "performance"
    """性能歧义：性能指标、优化目标、资源限制不明确"""

    SECURITY = "security"
    """安全歧义：权限控制、数据保护、认证授权不明确"""

    DEPENDENCY = "dependency"
    """依赖歧义：外部依赖、版本约束、集成方式不明确"""

    UX = "ux"
    """用户体验歧义：交互流程、反馈方式、界面行为不明确"""


# 歧义关键词映射表：每种类型至少 5 个中英文关键词
AMBIGUITY_KEYWORDS: dict[AmbiguityType, list[str]] = {
    AmbiguityType.SCOPE: [
        # 中文关键词
        "可能", "或许", "大概", "适当", "合理", "相关",
        "类似", "等等", "之类", "某些", "部分", "左右",
        # 英文关键词
        "maybe", "perhaps", "possibly", "probably", "roughly",
        "approximately", "some", "certain", "various", "etc",
        "and so on", "similar", "related", "appropriate",
    ],
    AmbiguityType.DATA_STRUCTURE: [
        # 中文关键词
        "待定", "灵活", "动态", "可选", "不固定", "自定义",
        "根据情况", "视情况", "具体", "详细", "完整",
        # 英文关键词
        "tbd", "to be determined", "flexible", "dynamic",
        "optional", "custom", "varies", "depends", "details",
        "complete", "full", "specific",
    ],
    AmbiguityType.INTERFACE: [
        # 中文关键词
        "接口", "调用", "请求", "响应", "参数", "返回",
        "格式", "协议", "方法", "端点", "路由",
        # 英文关键词
        "api", "endpoint", "request", "response", "parameter",
        "return", "format", "protocol", "method", "route",
        "payload", "body",
    ],
    AmbiguityType.VALIDATION: [
        # 中文关键词
        "校验", "验证", "检查", "规则", "约束", "限制",
        "合法", "有效", "必填", "范围", "格式",
        # 英文关键词
        "validate", "validation", "check", "verify", "rule",
        "constraint", "limit", "valid", "invalid", "required",
        "range", "format", "pattern",
    ],
    AmbiguityType.ERROR_HANDLING: [
        # 中文关键词
        "错误", "异常", "失败", "重试", "降级", "回滚",
        "恢复", "超时", "熔断", "兜底", "容错",
        # 英文关键词
        "error", "exception", "fail", "failure", "retry",
        "fallback", "rollback", "recover", "timeout", "circuit",
        "fault", "tolerance", "graceful",
    ],
    AmbiguityType.PERFORMANCE: [
        # 中文关键词
        "性能", "速度", "效率", "优化", "缓存", "并发",
        "吞吐", "延迟", "响应时间", "资源", "内存",
        # 英文关键词
        "performance", "speed", "efficiency", "optimize", "cache",
        "concurrent", "throughput", "latency", "response time",
        "resource", "memory", "cpu", "fast", "slow",
    ],
    AmbiguityType.SECURITY: [
        # 中文关键词
        "安全", "权限", "认证", "授权", "加密", "脱敏",
        "敏感", "隐私", "访问控制", "角色", "鉴权",
        # 英文关键词
        "security", "permission", "auth", "authentication",
        "authorization", "encrypt", "decrypt", "sensitive",
        "privacy", "access control", "role", "token", "secret",
    ],
    AmbiguityType.DEPENDENCY: [
        # 中文关键词
        "依赖", "集成", "对接", "第三方", "外部", "版本",
        "兼容", "迁移", "升级", "配置", "环境",
        # 英文关键词
        "dependency", "integrate", "integration", "third-party",
        "external", "version", "compatible", "migrate", "upgrade",
        "config", "configuration", "environment",
    ],
    AmbiguityType.UX: [
        # 中文关键词
        "用户", "交互", "界面", "反馈", "提示", "流程",
        "体验", "友好", "直观", "响应", "加载",
        # 英文关键词
        "user", "interaction", "interface", "feedback", "prompt",
        "flow", "experience", "friendly", "intuitive", "loading",
        "spinner", "toast", "modal", "dialog",
    ],
}


@dataclass
class AmbiguityMatch:
    """歧义匹配结果。

    表示在文档中检测到的一处歧义。

    属性：
        type: 歧义类型
        keyword: 触发匹配的关键词
        line_number: 匹配所在的行号（从 1 开始）
        context: 匹配的上下文（包含前后各 2 行）
        original_line: 匹配所在的原始行内容
    """

    type: AmbiguityType
    keyword: str
    line_number: int
    context: str
    original_line: str = ""
    confidence: float = field(default=1.0)

    def __str__(self) -> str:
        """返回歧义匹配的可读描述。"""
        return (
            f"[{self.type.value}] Line {self.line_number}: "
            f"'{self.keyword}' - {self.original_line.strip()}"
        )

    def to_dict(self) -> dict[str, str | int | float]:
        """转换为字典格式。"""
        return {
            "type": self.type.value,
            "keyword": self.keyword,
            "line_number": self.line_number,
            "context": self.context,
            "original_line": self.original_line,
            "confidence": self.confidence,
        }


def get_type_description(ambiguity_type: AmbiguityType) -> str:
    """获取歧义类型的中文描述。

    参数：
        ambiguity_type: 歧义类型

    返回：
        类型的中文描述
    """
    descriptions = {
        AmbiguityType.SCOPE: "范围歧义 - 功能边界、模块范围、影响范围不明确",
        AmbiguityType.DATA_STRUCTURE: "数据结构歧义 - 字段定义、类型、关联关系不明确",
        AmbiguityType.INTERFACE: "接口歧义 - API 设计、参数、返回值不明确",
        AmbiguityType.VALIDATION: "验证歧义 - 输入校验规则、约束条件不明确",
        AmbiguityType.ERROR_HANDLING: "错误处理歧义 - 异常处理、降级策略、重试逻辑不明确",
        AmbiguityType.PERFORMANCE: "性能歧义 - 性能指标、优化目标、资源限制不明确",
        AmbiguityType.SECURITY: "安全歧义 - 权限控制、数据保护、认证授权不明确",
        AmbiguityType.DEPENDENCY: "依赖歧义 - 外部依赖、版本约束、集成方式不明确",
        AmbiguityType.UX: "用户体验歧义 - 交互流程、反馈方式、界面行为不明确",
    }
    return descriptions.get(ambiguity_type, ambiguity_type.value)


def get_all_keywords() -> list[str]:
    """获取所有歧义关键词的扁平列表。

    返回：
        所有关键词列表
    """
    keywords = []
    for kw_list in AMBIGUITY_KEYWORDS.values():
        keywords.extend(kw_list)
    return keywords


def get_keywords_by_type(ambiguity_type: AmbiguityType) -> list[str]:
    """获取指定类型的关键词列表。

    参数：
        ambiguity_type: 歧义类型

    返回：
        该类型的关键词列表
    """
    return AMBIGUITY_KEYWORDS.get(ambiguity_type, [])


def get_context(lines: list[str], line_idx: int, context_lines: int = 2) -> str:
    """获取指定行的上下文（前后各 N 行）。

    参数：
        lines: 文本的所有行列表
        line_idx: 当前行索引（从 0 开始）
        context_lines: 前后各取多少行（默认 2）

    返回：
        包含上下文的文本字符串
    """
    start = max(0, line_idx - context_lines)
    end = min(len(lines), line_idx + context_lines + 1)
    return "\n".join(lines[start:end])


def is_in_code_block(lines: list[str], line_idx: int) -> bool:
    """检查指定行是否在代码块内。

    代码块由三个反引号（```）标记开始和结束。

    参数：
        lines: 文本的所有行列表
        line_idx: 当前行索引（从 0 开始）

    返回：
        True 表示在代码块内，False 表示不在
    """
    # 向前扫描，统计代码块标记数量
    code_block_count = 0
    for i in range(line_idx):
        if lines[i].strip().startswith("```"):
            code_block_count += 1

    # 如果代码块标记数量为奇数，说明当前行在代码块内
    return code_block_count % 2 == 1


def filter_false_positives(match: AmbiguityMatch, line: str) -> bool:
    """过滤误报，返回 True 表示保留，False 表示过滤。

    过滤规则：
    1. 跳过行内代码（`code`）中的关键词
    2. 跳过 URL 中的关键词
    3. 跳过 Markdown 标题行（以 # 开头）
    4. 跳过包含"已定义"、"已确定"等否定词的行

    参数：
        match: 歧义匹配结果
        line: 原始行内容

    返回：
        True 保留匹配，False 过滤掉
    """
    stripped = line.strip()

    # 跳过 Markdown 标题行
    if stripped.startswith("#"):
        return False

    # 跳过包含否定词的行（如"已定义"、"已确定"）
    # 这些词表示内容已经明确，不应标记为歧义
    negation_words = [
        "已定义", "已确定", "已明确", "已指定", "已说明",
        "已实现", "已完成", "已决定", "确定的", "明确的",
        "defined", "determined", "specified", "confirmed", "clear",
        "explicit", "concrete", "precise", "exact", "definite"
    ]
    line_lower = line.lower()
    for negation in negation_words:
        if negation in line_lower:
            return False

    # 跳过 URL 中的关键词
    if "http://" in line or "https://" in line:
        # 检查关键词是否在 URL 内
        import re
        url_pattern = r'https?://[^\s)]+'
        urls = re.findall(url_pattern, line)
        for url in urls:
            if match.keyword.lower() in url.lower():
                return False

    # 跳过行内代码中的关键词
    # 检测 `code` 格式
    import re
    inline_code_pattern = r'`[^`]+`'
    inline_codes = re.findall(inline_code_pattern, line)
    for code in inline_codes:
        if match.keyword.lower() in code.lower():
            return False

    return True


def detect(content: str) -> list[AmbiguityMatch]:
    """扫描文本内容，检测歧义。

    对文本内容进行逐行扫描，使用 AMBIGUITY_KEYWORDS 中的关键词
    进行匹配，返回所有检测到的歧义。

    匹配规则：
    - 不区分大小写
    - 支持中英文关键词
    - 提取前后各 2 行作为上下文
    - 精确匹配置信度 1.0，部分匹配 0.8

    过滤规则：
    - 跳过代码块内容（``` 包围的区域）
    - 跳过行内代码（`code`）
    - 跳过 URL 中的关键词
    - 跳过 Markdown 标题行

    参数：
        content: 要扫描的文本内容（通常是 proposal.md）

    返回：
        检测到的歧义匹配列表
    """
    matches: list[AmbiguityMatch] = []
    lines = content.splitlines()

    for line_idx, line in enumerate(lines):
        # 跳过代码块内的行
        if is_in_code_block(lines, line_idx):
            continue

        # 对每种歧义类型的关键词进行匹配
        for ambiguity_type, keywords in AMBIGUITY_KEYWORDS.items():
            for keyword in keywords:
                # 不区分大小写的关键词匹配
                if keyword.lower() in line.lower():
                    # 创建初步匹配结果
                    match = AmbiguityMatch(
                        type=ambiguity_type,
                        keyword=keyword,
                        line_number=line_idx + 1,  # 行号从 1 开始
                        context=get_context(lines, line_idx, context_lines=2),
                        original_line=line,
                        confidence=1.0,  # 精确匹配的置信度
                    )

                    # 过滤误报
                    if filter_false_positives(match, line):
                        matches.append(match)

    return matches
