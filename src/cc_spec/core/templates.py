"""cc-spec 的模板处理模块。"""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from cc_spec.utils.download import (
    download_file,
    get_github_raw_url,
    get_template_cache_dir,
)

# 默认模板仓库
DEFAULT_TEMPLATE_REPO = "owner/cc-spec-templates"  # TODO：更新为实际仓库名称
DEFAULT_TEMPLATE_BRANCH = "main"

# 模板文件名
TEMPLATE_FILES = [
    "spec-template.md",
    "plan-template.md",
    "tasks-template.md",
    "checklist-template.md",
]


class TemplateError(Exception):
    """模板相关错误的基础异常。"""

    pass


def get_template_source() -> tuple[str, str]:
    """从环境变量获取模板来源，或使用默认值。

    返回：
        (repository, branch)
    """
    # 检查环境变量中的自定义模板 URL
    custom_url = os.environ.get("CC_SPEC_TEMPLATE_URL")
    if custom_url:
        # 解析自定义 URL 格式：https://github.com/user/repo/tree/branch
        match = re.match(
            r"https://github\.com/([^/]+/[^/]+)(?:/tree/([^/]+))?", custom_url
        )
        if match:
            repo = match.group(1)
            branch = match.group(2) or DEFAULT_TEMPLATE_BRANCH
            return repo, branch

    return DEFAULT_TEMPLATE_REPO, DEFAULT_TEMPLATE_BRANCH


async def download_templates(
    dest_dir: Optional[Path] = None, use_cache: bool = True
) -> bool:
    """从 GitHub 下载模板文件。

    参数：
        dest_dir：目标目录（默认：缓存目录）
        use_cache：下载失败时是否使用缓存模板

    返回：
        模板下载成功或从缓存获取成功则为 True

    异常：
        TemplateError：无法获取模板时抛出
    """
    if dest_dir is None:
        dest_dir = get_template_cache_dir()

    dest_dir.mkdir(parents=True, exist_ok=True)

    repo, branch = get_template_source()

    # 尝试下载每个模板文件
    download_tasks = []
    for template_file in TEMPLATE_FILES:
        url = get_github_raw_url(repo, f"templates/{template_file}", branch)
        dest_path = dest_dir / template_file
        download_tasks.append(download_file(url, dest_path))

    results = await asyncio.gather(*download_tasks)

    # 检查是否全部下载成功
    all_success = all(results)

    if not all_success:
        # 下载失败时检查是否存在缓存模板
        if use_cache and _has_cached_templates(dest_dir):
            print("使用缓存模板（下载失败）")
            return True

        # 检查是否存在内置模板（兜底）
        bundled_dir = Path(__file__).parent.parent / "templates"
        if bundled_dir.exists():
            print("使用内置模板（下载失败）")
            _copy_bundled_templates(bundled_dir, dest_dir)
            return True

        raise TemplateError("模板下载失败，且没有可用的缓存模板")

    return True


def _has_cached_templates(cache_dir: Path) -> bool:
    """检查缓存中是否存在所有必需的模板文件。"""
    return all((cache_dir / template).exists() for template in TEMPLATE_FILES)


def _copy_bundled_templates(source_dir: Path, dest_dir: Path) -> None:
    """将内置模板复制到目标目录。"""
    for template_file in TEMPLATE_FILES:
        source_path = source_dir / template_file
        if source_path.exists():
            dest_path = dest_dir / template_file
            dest_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")


def render_template(template_content: str, variables: Dict[str, str]) -> str:
    """渲染模板并进行变量替换。

    支持变量格式：{variable_name}

    参数：
        template_content：模板内容
        variables：变量名到变量值的映射

    返回：
        渲染后的模板内容
    """
    rendered = template_content

    # 如未提供则补充通用变量
    if "date" not in variables:
        variables["date"] = datetime.now().strftime("%Y-%m-%d")

    if "timestamp" not in variables:
        variables["timestamp"] = datetime.now().isoformat()

    # 替换变量
    for key, value in variables.items():
        # 同时支持 {key} 与 $ARGUMENTS 形式
        rendered = rendered.replace(f"{{{key}}}", value)
        rendered = rendered.replace(f"${key.upper()}", value)

    return rendered


def copy_template(
    template_name: str,
    dest_path: Path,
    variables: Optional[Dict[str, str]] = None,
    source_dir: Optional[Path] = None,
) -> Path:
    """复制模板到目标位置，并进行变量替换。

    参数：
        template_name：模板文件名（例如 "spec-template.md"）
        dest_path：目标文件路径
        variables：用于替换的变量字典
        source_dir：模板来源目录（默认：缓存目录）

    返回：
        目标文件路径

    异常：
        TemplateError：模板文件不存在时抛出
    """
    if source_dir is None:
        source_dir = get_template_cache_dir()

    template_path = source_dir / template_name
    if not template_path.exists():
        raise TemplateError(f"未找到模板：{template_name}")

    # 读取模板内容
    template_content = template_path.read_text(encoding="utf-8")

    # 如提供变量则渲染替换
    if variables:
        template_content = render_template(template_content, variables)

    # 确保目标目录存在
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入渲染后的内容
    dest_path.write_text(template_content, encoding="utf-8")

    return dest_path


def list_templates(source_dir: Optional[Path] = None) -> List[str]:
    """列出可用的模板文件。

    参数：
        source_dir：模板来源目录（默认：缓存目录）

    返回：
        可用模板文件名列表
    """
    if source_dir is None:
        source_dir = get_template_cache_dir()

    if not source_dir.exists():
        return []

    # 返回存在的模板文件列表
    return [
        template for template in TEMPLATE_FILES if (source_dir / template).exists()
    ]


def get_template_path(template_name: str, source_dir: Optional[Path] = None) -> Path:
    """获取模板文件路径。

    参数：
        template_name：模板文件名
        source_dir：模板来源目录（默认：缓存目录）

    返回：
        模板文件路径

    异常：
        TemplateError：模板不存在时抛出
    """
    if source_dir is None:
        source_dir = get_template_cache_dir()

    template_path = source_dir / template_name
    if not template_path.exists():
        raise TemplateError(f"未找到模板：{template_name}")

    return template_path
