"""cc-spec 技术栈检测器。

该模块负责自动检测项目使用的技术栈，并提供相应的默认检查命令。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TechStack(Enum):
    """支持的技术栈。"""

    PYTHON_UV = "python_uv"  # Python + uv
    PYTHON_PIP = "python_pip"  # Python + pip
    NODE_PNPM = "node_pnpm"  # Node.js + pnpm
    NODE_NPM = "node_npm"  # Node.js + npm
    GO = "go"  # Go
    UNKNOWN = "unknown"


@dataclass
class TechRequirements:
    """技术要求配置。"""

    # 测试命令（如 "uv run pytest"）
    test_commands: list[str] = field(default_factory=list)
    # lint 命令（如 "uv run ruff check src/"）
    lint_commands: list[str] = field(default_factory=list)
    # 类型检查（如 "uv run mypy src/"）
    type_check_commands: list[str] = field(default_factory=list)
    # 构建命令（如 "pnpm build"）
    build_commands: list[str] = field(default_factory=list)
    # 来源文件路径
    source_file: str = ""


def detect_tech_stack(project_root: Path) -> TechStack:
    """检测项目技术栈。

    检测规则：
    - 存在 pyproject.toml + uv.lock → PYTHON_UV
    - 存在 pyproject.toml / requirements.txt → PYTHON_PIP
    - 存在 package.json + pnpm-lock.yaml → NODE_PNPM
    - 存在 package.json → NODE_NPM
    - 存在 go.mod → GO

    参数：
        project_root: 项目根目录路径

    返回：
        检测到的技术栈类型
    """
    # 检测 Python + uv
    if (project_root / "pyproject.toml").exists() and (project_root / "uv.lock").exists():
        return TechStack.PYTHON_UV

    # 检测 Python + pip
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return TechStack.PYTHON_PIP

    # 检测 Node.js + pnpm
    if (project_root / "package.json").exists() and (project_root / "pnpm-lock.yaml").exists():
        return TechStack.NODE_PNPM

    # 检测 Node.js + npm
    if (project_root / "package.json").exists():
        return TechStack.NODE_NPM

    # 检测 Go
    if (project_root / "go.mod").exists():
        return TechStack.GO

    return TechStack.UNKNOWN


def get_default_commands(tech_stack: TechStack) -> TechRequirements:
    """获取技术栈的默认检查命令。

    参数：
        tech_stack: 技术栈类型

    返回：
        该技术栈的默认命令集合
    """
    match tech_stack:
        case TechStack.PYTHON_UV:
            return TechRequirements(
                test_commands=["uv run pytest"],
                lint_commands=["uv run ruff check src/"],
                type_check_commands=["uv run mypy src/"],
                build_commands=[],
                source_file="<default:python_uv>",
            )

        case TechStack.PYTHON_PIP:
            return TechRequirements(
                test_commands=["pytest"],
                lint_commands=["ruff check src/"],
                type_check_commands=["mypy src/"],
                build_commands=[],
                source_file="<default:python_pip>",
            )

        case TechStack.NODE_PNPM:
            return TechRequirements(
                test_commands=["pnpm test"],
                lint_commands=["pnpm lint"],
                type_check_commands=["pnpm type-check"],
                build_commands=["pnpm build"],
                source_file="<default:node_pnpm>",
            )

        case TechStack.NODE_NPM:
            return TechRequirements(
                test_commands=["npm test"],
                lint_commands=["npm run lint"],
                type_check_commands=["npm run type-check"],
                build_commands=["npm run build"],
                source_file="<default:node_npm>",
            )

        case TechStack.GO:
            return TechRequirements(
                test_commands=["go test ./..."],
                lint_commands=["golangci-lint run"],
                type_check_commands=[],  # Go 的类型检查是内置的
                build_commands=["go build"],
                source_file="<default:go>",
            )

        case _:
            return TechRequirements(
                source_file="<default:unknown>",
            )
