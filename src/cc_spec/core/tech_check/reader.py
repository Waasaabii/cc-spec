"""cc-spec 技术要求配置读取器。

该模块负责从 CLAUDE.md、.claude/CLAUDE.md、pyproject.toml 等文件中提取技术要求。
"""

import re
import tomllib
from pathlib import Path

from .detector import TechRequirements


def read_tech_requirements(project_root: Path) -> TechRequirements | None:
    """从项目配置文件中读取技术要求。

    查找顺序：
    1. .claude/CLAUDE.md
    2. CLAUDE.md
    3. pyproject.toml（[tool.cc-spec] 段）

    解析规则：
    - 查找以 "uv run"、"pnpm"、"npm run"、"pytest"、"ruff"、"mypy" 等开头的命令
    - 识别代码块中的命令（```bash ... ```）

    参数：
        project_root: 项目根目录路径

    返回：
        解析到的技术要求，如果没有找到配置则返回 None
    """
    # 查找顺序：.claude/CLAUDE.md -> CLAUDE.md -> pyproject.toml
    candidate_files = [
        project_root / ".claude" / "CLAUDE.md",
        project_root / "CLAUDE.md",
        project_root / "pyproject.toml",
    ]

    for file_path in candidate_files:
        if not file_path.exists():
            continue

        # 根据文件类型选择解析方法
        if file_path.suffix == ".md":
            result = _parse_markdown(file_path)
            if result:
                result.source_file = str(file_path)
                return result
        elif file_path.name == "pyproject.toml":
            result = _parse_pyproject(file_path)
            if result:
                result.source_file = str(file_path)
                return result

    return None


def _parse_markdown(file_path: Path) -> TechRequirements | None:
    """从 Markdown 文件中解析技术要求。

    参数：
        file_path: Markdown 文件路径

    返回：
        解析到的技术要求，如果没有找到则返回 None
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    requirements = TechRequirements()

    # 提取所有代码块
    code_blocks = re.findall(r"```(?:bash|shell|sh)?\n(.*?)```", content, re.DOTALL)

    # 从代码块中提取命令
    for block in code_blocks:
        lines = block.strip().split("\n")
        for line in lines:
            line = line.strip()
            # 跳过注释行
            if not line or line.startswith("#"):
                continue

            # 分类命令
            _categorize_command(line, requirements)

    # 如果没有从代码块中找到命令，尝试从整个文档中查找
    if not any([
        requirements.test_commands,
        requirements.lint_commands,
        requirements.type_check_commands,
        requirements.build_commands,
    ]):
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            _categorize_command(line, requirements)

    # 如果找到了至少一个命令，返回结果
    if any([
        requirements.test_commands,
        requirements.lint_commands,
        requirements.type_check_commands,
        requirements.build_commands,
    ]):
        return requirements

    return None


def _parse_pyproject(file_path: Path) -> TechRequirements | None:
    """从 pyproject.toml 文件中解析技术要求。

    查找 [tool.cc-spec.tech-check] 段。

    参数：
        file_path: pyproject.toml 文件路径

    返回：
        解析到的技术要求，如果没有找到则返回 None
    """
    try:
        with open(file_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    # 查找 [tool.cc-spec.tech-check] 段
    tech_check_config = data.get("tool", {}).get("cc-spec", {}).get("tech-check", {})

    if not tech_check_config:
        return None

    requirements = TechRequirements(
        test_commands=tech_check_config.get("test", []),
        lint_commands=tech_check_config.get("lint", []),
        type_check_commands=tech_check_config.get("type-check", []),
        build_commands=tech_check_config.get("build", []),
    )

    return requirements


def _categorize_command(line: str, requirements: TechRequirements) -> None:
    """将命令分类到相应的类型中。

    参数：
        line: 命令行内容
        requirements: 要更新的技术要求对象
    """
    # 移除行尾注释（以 # 开头的注释）
    # 但要注意保留命令中的 # （比如在字符串中）
    if "#" in line:
        # 简单处理：找到 # 之前的内容
        parts = line.split("#", 1)
        # 检查 # 是否在引号内
        if parts[0].count('"') % 2 == 0 and parts[0].count("'") % 2 == 0:
            line = parts[0].strip()

    # 测试命令特征
    test_patterns = [
        r"^(?:uv run )?pytest",
        r"^(?:pnpm|npm)(?: run)? test",
        r"^go test",
        r"^cargo test",
    ]

    # Lint 命令特征
    lint_patterns = [
        r"^(?:uv run )?ruff check",
        r"^(?:pnpm|npm)(?: run)? lint",
        r"^eslint",
        r"^golangci-lint",
        r"^cargo clippy",
    ]

    # 类型检查命令特征
    type_check_patterns = [
        r"^(?:uv run )?mypy",
        r"^(?:pnpm|npm)(?: run)? type-check",
        r"^tsc",
    ]

    # 构建命令特征
    build_patterns = [
        r"^(?:pnpm|npm)(?: run)? build",
        r"^go build",
        r"^cargo build",
        r"^make build",
    ]

    # 检查并分类
    for pattern in test_patterns:
        if re.match(pattern, line):
            if line not in requirements.test_commands:
                requirements.test_commands.append(line)
            return

    for pattern in lint_patterns:
        if re.match(pattern, line):
            if line not in requirements.lint_commands:
                requirements.lint_commands.append(line)
            return

    for pattern in type_check_patterns:
        if re.match(pattern, line):
            if line not in requirements.type_check_commands:
                requirements.type_check_commands.append(line)
            return

    for pattern in build_patterns:
        if re.match(pattern, line):
            if line not in requirements.build_commands:
                requirements.build_commands.append(line)
            return
