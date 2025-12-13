"""cc-spec 的文件系统工具。

本模块提供文件与目录操作的辅助函数。
"""

from pathlib import Path
from typing import Optional


def ensure_dir(path: Path) -> None:
    """确保目录存在（必要时创建）。

    参数：
        path: 需要确保存在的目录路径
    """
    path.mkdir(parents=True, exist_ok=True)


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """通过查找 .cc-spec 目录来定位项目根目录。

    参数：
        start_path: 搜索起始目录（默认：当前目录）

    返回：
        找到则返回项目根目录路径，否则返回 None
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # 向上查找，直到找到 .cc-spec 目录或到达文件系统根目录
    while current != current.parent:
        cc_spec_dir = current / ".cc-spec"
        if cc_spec_dir.exists() and cc_spec_dir.is_dir():
            return current
        current = current.parent

    # 最后也检查根目录本身
    cc_spec_dir = current / ".cc-spec"
    if cc_spec_dir.exists() and cc_spec_dir.is_dir():
        return current

    return None


def get_cc_spec_dir(project_root: Path) -> Path:
    """获取 .cc-spec 目录路径。

    参数：
        project_root: 项目根目录

    返回：
        .cc-spec 目录路径
    """
    return project_root / ".cc-spec"


def get_config_path(project_root: Path) -> Path:
    """获取 config.yaml 文件路径。

    参数：
        project_root: 项目根目录

    返回：
        config.yaml 文件路径
    """
    return get_cc_spec_dir(project_root) / "config.yaml"


def get_changes_dir(project_root: Path) -> Path:
    """获取 changes 目录路径。

    参数：
        project_root: 项目根目录

    返回：
        changes 目录路径
    """
    return get_cc_spec_dir(project_root) / "changes"


def get_templates_dir(project_root: Path) -> Path:
    """获取 templates 目录路径。

    参数：
        project_root: 项目根目录

    返回：
        templates 目录路径
    """
    return get_cc_spec_dir(project_root) / "templates"


def get_specs_dir(project_root: Path) -> Path:
    """获取 specs 目录路径。

    参数：
        project_root: 项目根目录

    返回：
        specs 目录路径
    """
    return get_cc_spec_dir(project_root) / "specs"
