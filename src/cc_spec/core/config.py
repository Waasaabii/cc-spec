"""cc-spec 的配置管理。

该模块提供配置的加载、保存与管理能力。
它负责处理 config.yaml，并为所有设置提供默认值。

v1.1：新增 SubAgentProfile 及 profile 支持。
v1.2：新增 AgentsConfig 以支持多工具。
v1.3：新增 ScoringConfig（四维评分）与 LockConfig。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Dimension(Enum):
    """v1.3 四维评分机制的评分维度。"""

    FUNCTIONALITY = "functionality"  # 功能完整性
    CODE_QUALITY = "code_quality"    # 代码质量
    TEST_COVERAGE = "test_coverage"  # 测试覆盖
    DOCUMENTATION = "documentation"  # 文档同步


@dataclass
class DimensionConfig:
    """单个评分维度的配置。

    属性：
        weight：该维度的权重百分比（0-100）
        keywords：用于将 checklist 项归类到该维度的关键词
    """

    weight: int = 25
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        return {
            "weight": self.weight,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DimensionConfig":
        """从字典创建实例。"""
        return cls(
            weight=data.get("weight", 25),
            keywords=data.get("keywords", []),
        )


# v1.3 的默认维度配置
DEFAULT_DIMENSION_CONFIGS: dict[Dimension, DimensionConfig] = {
    Dimension.FUNCTIONALITY: DimensionConfig(
        weight=30,
        keywords=["功能", "实现", "需求", "feature", "implement", "create", "add"],
    ),
    Dimension.CODE_QUALITY: DimensionConfig(
        weight=25,
        keywords=["代码", "规范", "重构", "quality", "lint", "refactor", "style"],
    ),
    Dimension.TEST_COVERAGE: DimensionConfig(
        weight=25,
        keywords=["测试", "test", "覆盖", "用例", "coverage", "unit", "integration"],
    ),
    Dimension.DOCUMENTATION: DimensionConfig(
        weight=20,
        keywords=["文档", "注释", "类型", "doc", "comment", "type", "docstring"],
    ),
}


@dataclass
class ScoringConfig:
    """v1.3 四维评分的评分配置。

    属性：
        pass_threshold：通过所需的最低百分比（0-100）
        auto_retry：是否自动重试失败任务
        dimensions：各评分维度的配置
    """

    pass_threshold: int = 80
    auto_retry: bool = False
    dimensions: dict[str, DimensionConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """如果未提供则初始化默认维度。"""
        if not self.dimensions:
            self.dimensions = {
                dim.value: config
                for dim, config in DEFAULT_DIMENSION_CONFIGS.items()
            }

    def get_dimension_config(self, dimension: Dimension) -> DimensionConfig:
        """获取指定维度的配置。

        参数：
            dimension：要获取配置的维度

        返回：
            该维度的 DimensionConfig；未找到则返回默认值
        """
        dim_key = dimension.value
        if dim_key in self.dimensions:
            return self.dimensions[dim_key]
        return DEFAULT_DIMENSION_CONFIGS.get(dimension, DimensionConfig())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        return {
            "pass_threshold": self.pass_threshold,
            "auto_retry": self.auto_retry,
            "dimensions": {
                name: config.to_dict()
                for name, config in self.dimensions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoringConfig":
        """从字典创建实例。"""
        dimensions_data = data.get("dimensions", {})
        dimensions = {
            name: DimensionConfig.from_dict(dim_data)
            for name, dim_data in dimensions_data.items()
        }

        return cls(
            pass_threshold=data.get("pass_threshold", 80),
            auto_retry=data.get("auto_retry", False),
            dimensions=dimensions,
        )


@dataclass
class LockConfig:
    """v1.3 分布式锁的锁配置。

    属性：
        timeout_minutes：锁超时时间（分钟，默认 30）
        use_git_commit：是否使用 git commit 作为分布式锁标识
        cleanup_on_start：启动时是否清理过期锁
    """

    timeout_minutes: int = 30
    use_git_commit: bool = False
    cleanup_on_start: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        return {
            "timeout_minutes": self.timeout_minutes,
            "use_git_commit": self.use_git_commit,
            "cleanup_on_start": self.cleanup_on_start,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LockConfig":
        """从字典创建实例。"""
        return cls(
            timeout_minutes=data.get("timeout_minutes", 30),
            use_git_commit=data.get("use_git_commit", False),
            cleanup_on_start=data.get("cleanup_on_start", True),
        )


@dataclass
class AgentsConfig:
    """v1.2 的多 agent 配置。

    允许为项目配置多个 AI 工具，以便团队使用不同工具协作。

    属性：
        enabled：已启用的 AI 工具列表
        default：默认使用的 AI 工具
    """

    enabled: list[str] = field(default_factory=lambda: ["claude"])
    default: str = "claude"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        return {
            "enabled": self.enabled,
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentsConfig":
        """从字典创建实例。"""
        return cls(
            enabled=data.get("enabled", ["claude"]),
            default=data.get("default", "claude"),
        )


@dataclass
class SubAgentProfile:
    """SubAgent profile 配置（v1.1）。

    profile 用于定义不同任务类型的执行设置。

    属性：
        model：使用的模型（例如 "sonnet"、"haiku"、"opus"）
        timeout：超时时间（毫秒）
        permissionMode：权限模式（例如 "default"、"acceptEdits"）
        tools：允许工具列表（逗号分隔）
        description：profile 的可读描述
    """

    model: str = "sonnet"
    timeout: int = 300000
    permissionMode: str = "default"
    tools: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        result: dict[str, Any] = {
            "model": self.model,
            "timeout": self.timeout,
            "permissionMode": self.permissionMode,
        }
        if self.tools:
            result["tools"] = self.tools
        if self.description:
            result["description"] = self.description
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubAgentProfile":
        """从字典创建实例。"""
        return cls(
            model=data.get("model", "sonnet"),
            timeout=data.get("timeout", 300000),
            permissionMode=data.get("permissionMode", "default"),
            tools=data.get("tools"),
            description=data.get("description", ""),
        )


@dataclass
class SubAgentConfig:
    """SubAgent 执行配置。

    v1.1：新增 common 与 profiles，以支持基于 profile 的配置。

    属性：
        max_concurrent：最大并发任务数
        timeout：默认超时（已废弃，使用 common.timeout）
        common：所有 profiles 继承的公共设置
        profiles：命名的 profile 配置
    """

    max_concurrent: int = 10
    timeout: int = 300000  # 5 分钟（毫秒，旧字段）

    # v1.1 新增字段
    common: SubAgentProfile = field(default_factory=SubAgentProfile)
    profiles: dict[str, SubAgentProfile] = field(default_factory=dict)

    def get_profile(self, name: str | None) -> SubAgentProfile:
        """按名称获取 profile，并与 common 设置合并。

        参数：
            name：profile 名称（None 或 "default" 返回 common）

        返回：
            合并了 common 设置的 SubAgentProfile
        """
        if not name or name == "default":
            return self.common

        if name not in self.profiles:
            return self.common

        profile = self.profiles[name]

        # 与 common 合并：profile 的值覆盖 common
        return SubAgentProfile(
            model=profile.model if profile.model != "sonnet" else self.common.model,
            timeout=profile.timeout if profile.timeout != 300000 else self.common.timeout,
            permissionMode=profile.permissionMode if profile.permissionMode != "default" else self.common.permissionMode,
            tools=profile.tools if profile.tools else self.common.tools,
            description=profile.description,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        result: dict[str, Any] = {
            "max_concurrent": self.max_concurrent,
        }

        # 包含 common 配置
        if self.common:
            result["common"] = self.common.to_dict()

        # 包含 profiles
        if self.profiles:
            result["profiles"] = {
                name: profile.to_dict()
                for name, profile in self.profiles.items()
            }

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubAgentConfig":
        """从字典创建实例。"""
        common_data = data.get("common", {})
        profiles_data = data.get("profiles", {})

        profiles = {
            name: SubAgentProfile.from_dict(profile_data)
            for name, profile_data in profiles_data.items()
        }

        return cls(
            max_concurrent=data.get("max_concurrent", 10),
            timeout=data.get("timeout", 300000),
            common=SubAgentProfile.from_dict(common_data) if common_data else SubAgentProfile(),
            profiles=profiles,
        )


@dataclass
class ChecklistConfig:
    """Checklist 验证配置。"""

    pass_threshold: int = 80
    auto_retry: bool = False


@dataclass
class Config:
    """cc-spec 的主配置。

    属性：
        version：配置文件格式版本
        agent：当前 AI 工具类型（v1.2 已废弃，使用 agents.default）
        agents：多 agent 配置（v1.2）
        project_name：项目名称
        tech_requirements_sources：读取技术需求的文件列表
        subagent：SubAgent 执行配置
        checklist：Checklist 验证配置（v1.3 已废弃，使用 scoring）
        scoring：v1.3 四维评分配置
        lock：v1.3 分布式锁配置
    """

    version: str = "1.3"
    agent: str = "claude"  # v1.2 已废弃：为了向后兼容保留
    agents: AgentsConfig = field(default_factory=AgentsConfig)  # v1.2（多 agent 配置）
    project_name: str = "my-project"
    tech_requirements_sources: list[str] = field(default_factory=lambda: [
        ".claude/CLAUDE.md",
        "AGENTS.md",
        "pyproject.toml",
        "package.json",
    ])
    subagent: SubAgentConfig = field(default_factory=SubAgentConfig)
    checklist: ChecklistConfig = field(default_factory=ChecklistConfig)  # v1.3 已废弃
    # v1.3 新增字段
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    lock: LockConfig = field(default_factory=LockConfig)

    def get_active_agent(self) -> str:
        """获取当前激活的 AI agent。

        v1.2+ 优先使用 agents.default；为兼容 v1.0/v1.1 配置，回退到 agent 字段。

        返回：
            当前 agent 名称（例如 "claude"、"cursor"、"gemini"）
        """
        # v1.2：如果配置了 agents，则使用 agents.default
        if self.agents and self.agents.enabled:
            return self.agents.default
        # 兼容 v1.0/v1.1 配置：回退到 agent 字段
        return self.agent

    def get_pass_threshold(self) -> int:
        """获取评分的通过阈值。

        v1.3+ 优先使用 scoring.pass_threshold；为兼容 v1.2 配置，回退到 checklist.pass_threshold。

        返回：
            通过阈值百分比（0-100）
        """
        # v1.3：优先使用 scoring.pass_threshold
        if self.version >= "1.3":
            return self.scoring.pass_threshold
        # 兼容 v1.2 配置：回退到 checklist.pass_threshold
        return self.checklist.pass_threshold

    def to_dict(self) -> dict[str, Any]:
        """将 Config 转换为字典以便 YAML 序列化。

        返回：
            配置的字典表示
        """
        result: dict[str, Any] = {
            "version": self.version,
            "project_name": self.project_name,
            "tech_requirements_sources": self.tech_requirements_sources,
            "subagent": self.subagent.to_dict(),
        }

        # v1.2：包含 agents 配置
        if self.version >= "1.2":
            result["agents"] = self.agents.to_dict()
        else:
            # 旧格式：包含 agent 字段
            result["agent"] = self.agent

        # v1.3：包含 scoring 与 lock 配置
        if self.version >= "1.3":
            result["scoring"] = self.scoring.to_dict()
            result["lock"] = self.lock.to_dict()
        else:
            # 旧格式：包含 checklist 配置
            result["checklist"] = {
                "pass_threshold": self.checklist.pass_threshold,
                "auto_retry": self.checklist.auto_retry,
            }

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """从 YAML 读取的字典创建 Config。

        支持从 v1.0/v1.1/v1.2 格式迁移到 v1.3 格式。

        参数：
            data：从 config.yaml 读取的字典

        返回：
            Config 实例
        """
        subagent_data = data.get("subagent", {})
        checklist_data = data.get("checklist", {})
        scoring_data = data.get("scoring", {})
        lock_data = data.get("lock", {})

        # v1.2 迁移：agent -> agents
        agents_data = data.get("agents")
        agent = data.get("agent", "claude")

        if agents_data:
            # v1.2+ 格式
            agents = AgentsConfig.from_dict(agents_data)
        else:
            # v1.0/v1.1 格式：将单一 agent 迁移到 agents
            agents = AgentsConfig(
                enabled=[agent],
                default=agent,
            )

        # v1.3 迁移：checklist -> scoring
        if scoring_data:
            # v1.3 格式
            scoring = ScoringConfig.from_dict(scoring_data)
        else:
            # v1.2 格式：将 checklist 迁移到 scoring
            scoring = ScoringConfig(
                pass_threshold=checklist_data.get("pass_threshold", 80),
                auto_retry=checklist_data.get("auto_retry", False),
            )

        # v1.3：Lock 配置（新字段，不存在则使用默认值）
        lock = LockConfig.from_dict(lock_data) if lock_data else LockConfig()

        return cls(
            version=data.get("version", "1.3"),
            agent=agent,  # 为了向后兼容保留
            agents=agents,
            project_name=data.get("project_name", "my-project"),
            tech_requirements_sources=data.get("tech_requirements_sources", [
                ".claude/CLAUDE.md",
                "AGENTS.md",
                "pyproject.toml",
                "package.json",
            ]),
            subagent=SubAgentConfig.from_dict(subagent_data),
            checklist=ChecklistConfig(
                pass_threshold=checklist_data.get("pass_threshold", 80),
                auto_retry=checklist_data.get("auto_retry", False),
            ),
            scoring=scoring,
            lock=lock,
        )


def load_config(config_path: Path) -> Config:
    """从 YAML 文件加载配置。

    参数：
        config_path：config.yaml 文件路径

    返回：
        加载后的 Config 实例（缺失字段使用默认值）

    异常：
        FileNotFoundError：配置文件不存在
        yaml.YAMLError：配置文件内容不合法
    """
    if not config_path.exists():
        raise FileNotFoundError(f"未找到配置文件：{config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}

    return Config.from_dict(data)


def save_config(config: Config, config_path: Path) -> None:
    """将配置保存到 YAML 文件。

    参数：
        config：要保存的 Config 实例
        config_path：config.yaml 文件路径

    异常：
        OSError：无法写入文件
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            config.to_dict(),
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def detect_agent(project_root: Path) -> str:
    """根据目录标识检测当前使用的 AI 工具。

    参数：
        project_root：项目根目录

    返回：
        检测到的 agent 类型（"claude"、"cursor"、"gemini" 等），或 "unknown"
    """
    agent_markers = {
        ".claude": "claude",
        ".cursor": "cursor",
        ".gemini": "gemini",
        ".github/copilot": "copilot",
        ".amazonq": "amazonq",
        ".windsurf": "windsurf",
        ".qwen": "qwen",
    }

    for marker, agent_type in agent_markers.items():
        marker_path = project_root / marker
        if marker_path.exists():
            return agent_type

    return "unknown"


def read_tech_requirements(
    project_root: Path,
    sources: list[str]
) -> dict[str, str]:
    """从项目配置文件读取技术需求。

    参数：
        project_root：项目根目录
        sources：要读取的文件路径列表（相对项目根目录）

    返回：
        文件路径到内容的映射；文件不存在或无法读取则对应空字符串
    """
    requirements = {}

    for source in sources:
        file_path = project_root / source

        if not file_path.exists():
            requirements[source] = ""
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                requirements[source] = f.read()
        except Exception:
            # 读取失败则返回空字符串
            requirements[source] = ""

    return requirements
