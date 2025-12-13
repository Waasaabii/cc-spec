#!/usr/bin/env python3
"""修复文档缩进问题"""

import re
from pathlib import Path

def fix_indentation(content: str) -> str:
    """移除每行开头的多余空格（5个空格）"""
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # 如果行以5个空格开头，移除它们
        if line.startswith('     '):
            fixed_lines.append(line[5:])
        else:
            fixed_lines.append(line)
    return '\n'.join(fixed_lines)

def main():
    docs_dir = Path(__file__).parent

    # 需要修复缩进的文件
    files_to_fix = [
        "02-现状分析.md",
        "03-缺口分析.md",
        "04-设计方案.md",
        "05-实施步骤.md",
        "06-测试与验收.md",
        "07-风险与依赖.md",
        "08-里程碑.md",
        "09-附录.md",
    ]

    for filename in files_to_fix:
        filepath = docs_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            fixed_content = fix_indentation(content)
            filepath.write_text(fixed_content, encoding="utf-8")
            print(f"✓ 已修复缩进: {filename}")
        else:
            print(f"✗ 文件不存在: {filename}")

if __name__ == "__main__":
    main()
