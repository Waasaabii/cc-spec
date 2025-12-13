"""用于获取远程资源的下载工具。"""

from pathlib import Path

import httpx


async def download_file(
    url: str,
    dest_path: Path,
    timeout: float = 30.0,
    follow_redirects: bool = True,
) -> bool:
    """
    从 URL 下载文件到指定目标路径。

    Args:
        url: 要下载的 URL
        dest_path: 目标文件路径
        timeout: 请求超时时间（秒）
        follow_redirects: 是否跟随 HTTP 重定向

    Returns:
        bool: 下载成功返回 True，否则返回 False

    Raises:
        httpx.HTTPError: HTTP 请求失败时抛出
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=follow_redirects
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            # 确保父目录存在
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # 将内容写入文件
            dest_path.write_bytes(response.content)
            return True

    except (httpx.HTTPError, OSError) as e:
        # 记录错误但不抛出异常——由调用方处理回退逻辑
        print(f"Download failed: {e}")
        return False


def get_template_cache_dir() -> Path:
    """
    获取模板缓存目录。

    Returns:
        Path: 缓存目录路径（~/.cc-spec/templates/）
    """
    cache_dir = Path.home() / ".cc-spec" / "templates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_github_raw_url(repo: str, path: str, branch: str = "main") -> str:
    """
    构造 GitHub raw 内容的 URL。

    Args:
        repo: 仓库，格式为 "owner/repo"
        path: 仓库内的文件路径
        branch: 分支名（默认："main"）

    Returns:
        str: raw 内容 URL
    """
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
