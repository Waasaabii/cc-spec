"""v0.1.5：Codex 切片/摘要 Prompt 模板。"""

from __future__ import annotations


def chunk_file_prompt(*, rel_path: str, content: str) -> str:
    """让 Codex 将文件切成语义片段并返回 JSON 数组。"""
    return f"""你是一个“文件切片器”。**不要修改任何文件，不要执行命令**。

目标：把给定文件切成有意义的片段，返回**严格 JSON**（只能输出 JSON，不能有任何解释文字）。

输入文件：`{rel_path}`

输出要求：
- 输出必须是 JSON 数组（list）
- 每个元素是对象，字段：
  - id: string（建议简短、稳定、可读）
  - type: string（function/class/module/section/config/other 之一即可）
  - summary: string（中文优先，<= 80 字）
  - content: string（该片段原文，尽量保留关键上下文）
  - start_line: number|null（可选）
  - end_line: number|null（可选）

禁止：
- 不要输出 Markdown
- 不要输出 ``` 包裹
- 不要输出额外字段（除非你非常确定需要）

文件内容如下（原文）：\n\n{content}
"""


def reference_index_prompt(*, rel_path: str, content: str) -> str:
    """reference/** 的索引级摘要：尽量少 token，但可检索。"""
    excerpt = content[:8000]
    return f"""你是一个“参考资料索引器”。**不要修改任何文件，不要执行命令**。

目标：为 reference 目录中的文件生成“索引级摘要”，用于后续向量检索命中后再做深切片。

输入文件：`{rel_path}`

输出要求：只输出严格 JSON 数组（list），元素对象字段：
- id: string（建议用 file_index）
- type: string（固定写 "reference_index"）
- summary: string（<= 120 字，中文优先）
- content: string（只放提取的关键信息/目录/入口提示；不要全文复述）

文件内容节选如下（可能被截断）：\n\n{excerpt}
"""

