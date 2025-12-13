"""手动测试脚本：验证歧义检测器核心功能。

验证点：
1. detect() 正确扫描内容
2. 关键词匹配支持中英文
3. 上下文包含前后各 2 行
4. 含误报过滤逻辑（如"已定义"、"已确定"不标记）
"""

from cc_spec.core.ambiguity import detect, AmbiguityType

# 测试用例 1: 基本的中英文关键词检测
test_content_1 = """
# 功能需求

用户登录功能的具体实现可能需要调整。
The system might need additional validation.
我们大概需要 3-5 个接口来完成这个功能。
"""

print("=" * 60)
print("测试 1: 基本中英文关键词检测")
print("=" * 60)
matches = detect(test_content_1)
print(f"检测到 {len(matches)} 处歧义:")
for match in matches:
    print(f"  - [{match.type.value}] 行 {match.line_number}: '{match.keyword}'")
    print(f"    原文: {match.original_line.strip()}")
print()

# 测试用例 2: 上下文验证（前后各 2 行）
test_content_2 = """
第一行内容
第二行内容
第三行内容
这里可能存在一些问题
第五行内容
第六行内容
第七行内容
"""

print("=" * 60)
print("测试 2: 上下文包含前后各 2 行")
print("=" * 60)
matches = detect(test_content_2)
if matches:
    match = matches[0]
    print(f"检测到的行号: {match.line_number}")
    print(f"上下文内容:")
    print(match.context)
    print()
    # 验证上下文包含前后各 2 行
    context_lines = match.context.split('\n')
    print(f"上下文行数: {len(context_lines)} (应该是 5 行: 前2+当前1+后2)")
print()

# 测试用例 3: 误报过滤 - "已定义"、"已确定"
test_content_3 = """
# 数据结构

数据结构待定，需要进一步讨论。
用户表结构已定义，包含以下字段。
API 格式已确定，使用 REST 风格。
性能指标已明确，响应时间不超过 100ms。
"""

print("=" * 60)
print("测试 3: 误报过滤（已定义、已确定应该被过滤）")
print("=" * 60)
matches = detect(test_content_3)
print(f"检测到 {len(matches)} 处歧义:")
for match in matches:
    print(f"  - [{match.type.value}] 行 {match.line_number}: '{match.keyword}'")
    print(f"    原文: {match.original_line.strip()}")
print()
print("注意: '已定义'、'已确定'、'已明确' 所在的行应该被过滤掉")
print()

# 测试用例 4: 代码块过滤
test_content_4 = """
# 示例代码

以下是一个示例：

```python
# 这里可能有一些问题
def maybe_process(data):
    return data
```

但是文档中可能还需要补充说明。
"""

print("=" * 60)
print("测试 4: 代码块内容过滤")
print("=" * 60)
matches = detect(test_content_4)
print(f"检测到 {len(matches)} 处歧义:")
for match in matches:
    print(f"  - [{match.type.value}] 行 {match.line_number}: '{match.keyword}'")
    print(f"    原文: {match.original_line.strip()}")
print()
print("注意: 代码块内的 '可能'、'maybe' 应该被过滤掉")
print()

# 测试用例 5: Markdown 标题过滤
test_content_5 = """
# 可能的解决方案

这是正文中的可能方案。

## 相关功能

这里描述相关功能。
"""

print("=" * 60)
print("测试 5: Markdown 标题行过滤")
print("=" * 60)
matches = detect(test_content_5)
print(f"检测到 {len(matches)} 处歧义:")
for match in matches:
    print(f"  - [{match.type.value}] 行 {match.line_number}: '{match.keyword}'")
    print(f"    原文: {match.original_line.strip()}")
print()
print("注意: 标题行（# 开头）中的关键词应该被过滤掉")
print()

# 测试用例 6: 多种歧义类型
test_content_6 = """
# 系统设计文档

1. 数据结构待定，需要根据实际情况调整
2. API 接口需要定义清楚
3. 需要添加参数校验规则
4. 错误处理的重试策略要明确
5. 性能优化目标大概是 100ms
6. 权限控制机制需要设计
7. 第三方依赖版本要确定
8. 用户交互流程需要优化
"""

print("=" * 60)
print("测试 6: 多种歧义类型检测")
print("=" * 60)
matches = detect(test_content_6)
print(f"检测到 {len(matches)} 处歧义:")

# 按类型分组统计
type_counts = {}
for match in matches:
    type_name = match.type.value
    if type_name not in type_counts:
        type_counts[type_name] = 0
    type_counts[type_name] += 1
    print(f"  - [{match.type.value}] 行 {match.line_number}: '{match.keyword}'")

print(f"\n歧义类型分布:")
for type_name, count in sorted(type_counts.items()):
    print(f"  {type_name}: {count} 处")
print()

print("=" * 60)
print("测试完成！✓")
print("=" * 60)
