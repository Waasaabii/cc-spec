"""cc-spec 的 Delta 解析与合并模块。

该模块提供 Delta spec 的解析、校验与合并能力。
Delta spec 用于记录对规格的增量变更（ADDED/MODIFIED/REMOVED/RENAMED）。
"""

import re
from dataclasses import dataclass
from enum import Enum


class DeltaOperation(Enum):
    """需求的 Delta 操作类型。"""

    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


@dataclass
class DeltaItem:
    """单个 Delta 变更项。

    属性：
        operation：操作类型（ADDED/MODIFIED/REMOVED/RENAMED）
        requirement_name：被变更的需求名称
        content：需求完整内容（仅用于 ADDED/MODIFIED）
        reason：删除原因（仅用于 REMOVED）
        migration：迁移指引（仅用于 REMOVED）
        old_name：原需求名称（仅用于 RENAMED）
        new_name：新需求名称（仅用于 RENAMED）
    """

    operation: DeltaOperation
    requirement_name: str
    content: str = ""
    reason: str | None = None
    migration: str | None = None
    old_name: str | None = None
    new_name: str | None = None


@dataclass
class DeltaSpec:
    """完整的 Delta 规格说明。

    属性：
        capability：被变更的能力（capability）名称
        items：Delta 变更项列表
    """

    capability: str
    items: list[DeltaItem]


def parse_delta(content: str) -> DeltaSpec:
    """解析 Delta spec.md 内容并提取所有变更项。

    参数：
        content：Delta spec 的原始 Markdown 内容

    返回：
        包含 capability 名称与全部变更项的 DeltaSpec 对象

    异常：
        ValueError：当 Delta spec 格式不合法时抛出
    """
    # 从标题提取能力名称：# Delta: {capability}
    title_match = re.search(r"^#\s+Delta:\s+(.+)$", content, re.MULTILINE)
    if not title_match:
        raise ValueError("Delta spec 标题格式无效：需要 `# Delta: {capability}`")

    capability = title_match.group(1).strip()
    items: list[DeltaItem] = []

    # 按 ## 标题拆分内容为多个区块
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)

    for section in sections[1:]:  # 跳过第一次拆分（第一个 ## 之前的内容）
        section = section.strip()
        if not section:
            continue

        # 根据区块标题确定操作类型
        if section.startswith("ADDED Requirements"):
            items.extend(_parse_added_section(section))
        elif section.startswith("MODIFIED Requirements"):
            items.extend(_parse_modified_section(section))
        elif section.startswith("REMOVED Requirements"):
            items.extend(_parse_removed_section(section))
        elif section.startswith("RENAMED Requirements"):
            items.extend(_parse_renamed_section(section))

    return DeltaSpec(capability=capability, items=items)


def _parse_added_section(section: str) -> list[DeltaItem]:
    """解析 ADDED Requirements 区块。

    参数：
        section：以 "ADDED Requirements" 开头的区块内容

    返回：
        operation=ADDED 的 DeltaItem 列表
    """
    items: list[DeltaItem] = []

    # 查找所有 ### Requirement: 标题
    requirements = re.split(r"^###\s+Requirement:\s+", section, flags=re.MULTILINE)

    for req in requirements[1:]:  # 跳过第一次拆分（区块标题）
        req = req.strip()
        if not req:
            continue

        # 提取需求名称（首行）与内容（其余部分）
        lines = req.split("\n", 1)
        requirement_name = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""

        items.append(
            DeltaItem(
                operation=DeltaOperation.ADDED,
                requirement_name=requirement_name,
                content=content,
            )
        )

    return items


def _parse_modified_section(section: str) -> list[DeltaItem]:
    """解析 MODIFIED Requirements 区块。

    参数：
        section：以 "MODIFIED Requirements" 开头的区块内容

    返回：
        operation=MODIFIED 的 DeltaItem 列表
    """
    items: list[DeltaItem] = []

    # 查找所有 ### Requirement: 标题
    requirements = re.split(r"^###\s+Requirement:\s+", section, flags=re.MULTILINE)

    for req in requirements[1:]:  # 跳过第一次拆分（区块标题）
        req = req.strip()
        if not req:
            continue

        # 提取需求名称（首行）与完整内容（其余部分）
        lines = req.split("\n", 1)
        requirement_name = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""

        items.append(
            DeltaItem(
                operation=DeltaOperation.MODIFIED,
                requirement_name=requirement_name,
                content=content,
            )
        )

    return items


def _parse_removed_section(section: str) -> list[DeltaItem]:
    """解析 REMOVED Requirements 区块。

    参数：
        section：以 "REMOVED Requirements" 开头的区块内容

    返回：
        operation=REMOVED 的 DeltaItem 列表
    """
    items: list[DeltaItem] = []

    # 查找所有 ### Requirement: 标题
    requirements = re.split(r"^###\s+Requirement:\s+", section, flags=re.MULTILINE)

    for req in requirements[1:]:  # 跳过第一次拆分（区块标题）
        req = req.strip()
        if not req:
            continue

        # 提取需求名称（首行）
        lines = req.split("\n", 1)
        requirement_name = lines[0].strip()

        # 提取 Reason 与 Migration
        reason = None
        migration = None

        if len(lines) > 1:
            content_part = lines[1]

            # 提取 **Reason**: ...
            reason_match = re.search(
                r"\*\*Reason\*\*:\s*(.+?)(?=\n\*\*|\Z)", content_part, re.DOTALL
            )
            if reason_match:
                reason = reason_match.group(1).strip()

            # 提取 **Migration**: ...
            migration_match = re.search(
                r"\*\*Migration\*\*:\s*(.+?)(?=\n\*\*|\Z)", content_part, re.DOTALL
            )
            if migration_match:
                migration = migration_match.group(1).strip()

        items.append(
            DeltaItem(
                operation=DeltaOperation.REMOVED,
                requirement_name=requirement_name,
                reason=reason,
                migration=migration,
            )
        )

    return items


def _parse_renamed_section(section: str) -> list[DeltaItem]:
    """解析 RENAMED Requirements 区块。

    参数：
        section：以 "RENAMED Requirements" 开头的区块内容

    返回：
        operation=RENAMED 的 DeltaItem 列表
    """
    items: list[DeltaItem] = []

    # 查找重命名对，格式：
    # - FROM（原名）: `### Requirement: Old Name`
    # - TO（新名）: `### Requirement: New Name`
    rename_pattern = re.compile(
        r"-\s*FROM:\s*`###\s+Requirement:\s+(.+?)`\s*\n"
        r"\s*-\s*TO:\s*`###\s+Requirement:\s+(.+?)`",
        re.MULTILINE,
    )

    for match in rename_pattern.finditer(section):
        old_name = match.group(1).strip()
        new_name = match.group(2).strip()

        items.append(
            DeltaItem(
                operation=DeltaOperation.RENAMED,
                requirement_name=new_name,  # 以新名称为主
                old_name=old_name,
                new_name=new_name,
            )
        )

    return items


def validate_delta(delta: DeltaSpec) -> tuple[bool, list[str]]:
    """校验 Delta spec 的格式与内容。

    参数：
        delta：要校验的 DeltaSpec 对象

    返回：
        (is_valid, error_messages)
        - is_valid：若所有校验通过则为 True
        - error_messages：校验错误信息列表（合法时为空）
    """
    errors: list[str] = []

    # 校验 capability 名称
    if not delta.capability:
        errors.append("Delta spec 必须包含 capability 名称")

    # 校验是否存在变更项
    if not delta.items:
        errors.append("Delta spec 至少要包含一个变更项")

    # 逐项校验
    for idx, item in enumerate(delta.items):
        item_prefix = f"第 {idx + 1} 项（{item.operation.value}）"

        # 校验 requirement_name
        if not item.requirement_name:
            errors.append(f"{item_prefix}：必须提供 requirement_name")

        # 校验 ADDED/MODIFIED 项必须有 content
        if item.operation in (DeltaOperation.ADDED, DeltaOperation.MODIFIED):
            if not item.content:
                errors.append(
                    f"{item_prefix}：ADDED/MODIFIED 操作必须提供 content"
                )

        # 校验 REMOVED 项必须有 reason
        if item.operation == DeltaOperation.REMOVED:
            if not item.reason:
                errors.append(
                    f"{item_prefix}：REMOVED 操作必须提供 reason"
                )

        # 校验 RENAMED 项必须有 old_name 与 new_name
        if item.operation == DeltaOperation.RENAMED:
            if not item.old_name:
                errors.append(
                    f"{item_prefix}：RENAMED 操作必须提供 old_name"
                )
            if not item.new_name:
                errors.append(
                    f"{item_prefix}：RENAMED 操作必须提供 new_name"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


def merge_delta(base_content: str, delta: DeltaSpec) -> str:
    """将 Delta 变更合并到基础 spec 内容中。

    参数：
        base_content：原始 spec.md 内容
        delta：包含待应用变更的 DeltaSpec

    返回：
        应用所有变更后的合并 spec 内容

    异常：
        ValueError：当发生合并冲突时（例如基础 spec 中找不到对应需求）
    """
    result = base_content

    for item in delta.items:
        if item.operation == DeltaOperation.ADDED:
            result = _merge_added(result, item)
        elif item.operation == DeltaOperation.MODIFIED:
            result = _merge_modified(result, item)
        elif item.operation == DeltaOperation.REMOVED:
            result = _merge_removed(result, item)
        elif item.operation == DeltaOperation.RENAMED:
            result = _merge_renamed(result, item)

    return result


def _merge_added(base_content: str, item: DeltaItem) -> str:
    """将 ADDED 需求合并到基础内容中。

    会将新需求追加到 spec 末尾。

    参数：
        base_content：原始 spec 内容
        item：operation=ADDED 的 DeltaItem

    返回：
        追加需求后的 spec 内容
    """
    # 确保追加前有换行
    if not base_content.endswith("\n"):
        base_content += "\n"

    # 添加新的需求
    new_requirement = f"\n### Requirement: {item.requirement_name}\n{item.content}\n"

    return base_content + new_requirement


def _merge_modified(base_content: str, item: DeltaItem) -> str:
    """将 MODIFIED 需求合并到基础内容中。

    用新内容替换整个需求区块。

    参数：
        base_content：原始 spec 内容
        item：operation=MODIFIED 的 DeltaItem

    返回：
        修改后的 spec 内容

    异常：
        ValueError：当基础内容中找不到对应需求时
    """
    # 匹配需求区块的模式
    # 从 ### Requirement: {name} 匹配到下一个 ### 或字符串结束
    pattern = re.compile(
        rf"^###\s+Requirement:\s+{re.escape(item.requirement_name)}\s*\n"
        r"(.*?)(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = pattern.search(base_content)
    if not match:
        raise ValueError(
            f"无法修改需求 '{item.requirement_name}'：在基础 spec 中未找到"
        )

    # 替换为新内容
    replacement = f"### Requirement: {item.requirement_name}\n{item.content}\n\n"
    result = pattern.sub(replacement, base_content, count=1)

    return result


def _merge_removed(base_content: str, item: DeltaItem) -> str:
    """将 REMOVED 需求合并到基础内容中。

    移除整个需求区块。

    参数：
        base_content：原始 spec 内容
        item：operation=REMOVED 的 DeltaItem

    返回：
        删除需求后的 spec 内容

    异常：
        ValueError：当基础内容中找不到对应需求时
    """
    # 匹配需求区块的模式
    # 从 ### Requirement: {name} 匹配到下一个 ### 或字符串结束
    pattern = re.compile(
        rf"^###\s+Requirement:\s+{re.escape(item.requirement_name)}\s*\n"
        r".*?(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = pattern.search(base_content)
    if not match:
        raise ValueError(
            f"无法删除需求 '{item.requirement_name}'：在基础 spec 中未找到"
        )

    # 移除需求区块
    result = pattern.sub("", base_content, count=1)

    return result


def _merge_renamed(base_content: str, item: DeltaItem) -> str:
    """将 RENAMED 需求合并到基础内容中。

    只修改需求标题，保留全部内容。

    参数：
        base_content：原始 spec 内容
        item：operation=RENAMED 的 DeltaItem

    返回：
        重命名后的 spec 内容

    异常：
        ValueError：当基础内容中找不到旧需求名称时
    """
    if not item.old_name or not item.new_name:
        raise ValueError("RENAMED 操作需要同时提供 old_name 与 new_name")

    # 仅匹配需求标题行的模式
    pattern = re.compile(
        rf"^(###\s+Requirement:\s+){re.escape(item.old_name)}\s*$", re.MULTILINE
    )

    match = pattern.search(base_content)
    if not match:
        raise ValueError(
            f"无法重命名需求 '{item.old_name}'：在基础 spec 中未找到"
        )

    # 仅替换标题，保持内容不变
    result = pattern.sub(rf"\g<1>{item.new_name}", base_content, count=1)

    return result


def generate_merge_preview(base_content: str, delta: DeltaSpec) -> str:
    """生成合并时将要应用的变更预览。

    参数：
        base_content：原始 spec 内容
        delta：包含待预览变更的 DeltaSpec

    返回：
        可读的预览文本，描述所有变更
    """
    preview_lines: list[str] = []
    preview_lines.append(f"# Delta 合并预览：{delta.capability}\n")
    preview_lines.append(f"变更总数：{len(delta.items)}\n")

    # 按操作类型分组
    added = [item for item in delta.items if item.operation == DeltaOperation.ADDED]
    modified = [
        item for item in delta.items if item.operation == DeltaOperation.MODIFIED
    ]
    removed = [item for item in delta.items if item.operation == DeltaOperation.REMOVED]
    renamed = [item for item in delta.items if item.operation == DeltaOperation.RENAMED]

    # ADDED 区块
    if added:
        preview_lines.append(f"\n## 新增需求（{len(added)}）\n")
        for item in added:
            preview_lines.append(f"  + {item.requirement_name}")

    # MODIFIED 区块
    if modified:
        preview_lines.append(f"\n## 修改需求（{len(modified)}）\n")
        for item in modified:
            preview_lines.append(f"  ~ {item.requirement_name}")

    # REMOVED 区块
    if removed:
        preview_lines.append(f"\n## 删除需求（{len(removed)}）\n")
        for item in removed:
            preview_lines.append(f"  - {item.requirement_name}")
            if item.reason:
                preview_lines.append(f"    原因：{item.reason}")

    # RENAMED 区块
    if renamed:
        preview_lines.append(f"\n## 重命名需求（{len(renamed)}）\n")
        for item in renamed:
            preview_lines.append(f"  → {item.old_name} → {item.new_name}")

    # 校验区块
    preview_lines.append("\n## 校验\n")
    is_valid, errors = validate_delta(delta)
    if is_valid:
        preview_lines.append("  ✓ 全部校验通过")
    else:
        preview_lines.append("  ✗ 发现校验错误：")
        for error in errors:
            preview_lines.append(f"    - {error}")

    return "\n".join(preview_lines)
