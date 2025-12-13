#!/usr/bin/env python3
"""从 history.txt 中恢复计划文档"""

import re
from pathlib import Path

def extract_documents(history_path: Path) -> dict[str, str]:
    """从历史记录中提取文档内容"""
    content = history_path.read_text(encoding="utf-8")

    documents = {}

    # 查找所有 Write 操作后的文档内容
    # 格式: Write(...md) 后面跟着内容

    # 01-背景与目标.md
    doc1_match = re.search(
        r'Write\(.*01-背景与目标\.md\).*?⎿.*?Wrote.*?\n(.*?)(?=\n∴ Thinking|$)',
        content, re.DOTALL
    )

    # 实际上历史记录中的格式是行号开头的，让我重新解析
    # 格式如: "     3→     # 01 - 背景与目标"

    return documents


def extract_doc_content(content: str, start_marker: str, end_marker: str) -> str:
    """提取两个标记之间的文档内容"""
    start_idx = content.find(start_marker)
    if start_idx == -1:
        return ""

    end_idx = content.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        end_idx = len(content)

    raw_content = content[start_idx:end_idx]

    # 移除行号前缀 (如 "    10→     ")
    lines = []
    for line in raw_content.split('\n'):
        # 匹配 "数字→" 模式并移除
        match = re.match(r'\s*\d+→(.*)$', line)
        if match:
            lines.append(match.group(1))
        elif '→' not in line[:20] if len(line) > 20 else '→' not in line:
            # 如果不是行号格式，可能是原始内容
            lines.append(line)

    return '\n'.join(lines).strip()


def main():
    history_path = Path(__file__).parent / "history.txt"
    output_dir = Path(__file__).parent

    content = history_path.read_text(encoding="utf-8")

    # 定义文档的开始和结束标记
    doc_markers = [
        ("01-背景与目标.md", "# 01 - 背景与目标", "∴ Thinking…\n\n  好的，第一个文档写完了"),
        ("02-现状分析.md", "# 02 - 现状分析", "∴ Thinking…\n\n  好的，第二个文档写完了"),
        ("03-缺口分析.md", "# 03 - 缺口分析", "∴ Thinking…\n\n  很好，继续写 04-设计方案"),
        ("04-设计方案.md", "# 04 - 设计方案", "∴ Thinking…\n\n  很好，04 写完了"),
        ("05-实施步骤.md", "# 05 - 实施步骤", "∴ Thinking…\n\n  很好，继续写剩余的文档"),
        ("06-测试与验收.md", "# 06 - 测试与验收", "∴ Thinking…\n\n  继续写剩余的文档"),
        ("07-风险与依赖.md", "# 07 - 风险与依赖", "∴ Thinking…\n\n  继续写 08 和 09"),
        ("08-里程碑.md", "# 08 - 里程碑", "∴ Thinking…\n\n  继续写 09-附录"),
        ("09-附录.md", "# 09 - 附录", "══════════════════════"),
    ]

    for filename, start_marker, end_marker in doc_markers:
        doc_content = extract_doc_content(content, start_marker, end_marker)
        if doc_content:
            output_path = output_dir / filename
            output_path.write_text(doc_content, encoding="utf-8")
            print(f"✓ 已恢复: {filename} ({len(doc_content)} 字符)")
        else:
            print(f"✗ 未找到: {filename}")


if __name__ == "__main__":
    main()
