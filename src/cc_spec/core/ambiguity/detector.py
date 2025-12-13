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
