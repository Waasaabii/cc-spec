#!/usr/bin/env python
"""演示 tech_check 模块的功能。"""

from pathlib import Path

from cc_spec.core.tech_check import (
    detect_tech_stack,
    get_default_commands,
    read_tech_requirements,
    run_tech_checks,
    should_block,
)


def main() -> None:
    """演示 tech_check 模块的主要功能。"""
    project_root = Path(".")

    print("=" * 60)
    print("技术检查模块演示")
    print("=" * 60)

    # 1. 从 CLAUDE.md 读取技术要求
    print("\n[步骤 1] 从 CLAUDE.md 读取技术要求")
    print("-" * 60)
    req = read_tech_requirements(project_root)
    if req:
        print(f"✓ 来源文件: {req.source_file}")
        print(f"  - 测试命令: {len(req.test_commands)} 个")
        for cmd in req.test_commands[:2]:  # 只显示前两个
            print(f"    • {cmd}")
        if len(req.test_commands) > 2:
            print(f"    ... 还有 {len(req.test_commands) - 2} 个")
        print(f"  - Lint 命令: {len(req.lint_commands)} 个")
        for cmd in req.lint_commands[:2]:
            print(f"    • {cmd}")
        print(f"  - 类型检查命令: {len(req.type_check_commands)} 个")
        for cmd in req.type_check_commands:
            print(f"    • {cmd}")
    else:
        print("✗ 未找到技术要求配置")

    # 2. 检测技术栈
    print("\n[步骤 2] 智能检测项目技术栈")
    print("-" * 60)
    stack = detect_tech_stack(project_root)
    print(f"✓ 检测到的技术栈: {stack.value}")

    # 3. 获取默认命令
    print("\n[步骤 3] 获取技术栈默认命令")
    print("-" * 60)
    defaults = get_default_commands(stack)
    print(f"  - 测试命令: {defaults.test_commands}")
    print(f"  - Lint 命令: {defaults.lint_commands}")
    print(f"  - 类型检查: {defaults.type_check_commands}")

    # 4. 演示失败处理规则
    print("\n[步骤 4] 失败处理规则")
    print("-" * 60)
    from cc_spec.core.tech_check import CheckResult

    check_types = [
        ("test", "测试失败"),
        ("build", "构建失败"),
        ("lint", "Lint 失败"),
        ("type_check", "类型检查失败"),
    ]

    for check_type, desc in check_types:
        result = CheckResult(
            command="dummy",
            success=False,
            output="",
            error="error",
            duration_seconds=1.0,
            check_type=check_type,
        )
        blocks = should_block(result)
        status = "🛑 阻断执行" if blocks else "⚠️  警告继续"
        print(f"  {status}  {desc}")

    # 5. 执行实际检查（仅 lint，不运行测试避免等待）
    print("\n[步骤 5] 执行技术检查示例")
    print("-" * 60)
    if req:
        # 只运行 lint 检查作为演示
        results = run_tech_checks(req, project_root, check_types=["lint"])
        for result in results:
            status = "✓" if result.success else "✗"
            print(f"  {status} {result.check_type}: {result.command}")
            print(f"    耗时: {result.duration_seconds:.2f}s")
            if not result.success:
                print(f"    错误: {result.error}")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
