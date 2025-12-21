"""Tests for tech_check module."""

import tempfile
from pathlib import Path

import pytest

from cc_spec.core.tech_check import (
    CheckResult,
    TechRequirements,
    TechStack,
    detect_tech_stack,
    get_default_commands,
    read_tech_requirements,
    run_tech_checks,
    should_block,
)


class TestTechStack:
    """Tests for TechStack enum."""

    def test_has_five_main_stacks(self) -> None:
        """Test that enum has 5 main stack types."""
        assert len(TechStack) == 6  # 包含 UNKNOWN

    def test_python_uv_type(self) -> None:
        """Test PYTHON_UV type exists."""
        assert TechStack.PYTHON_UV.value == "python_uv"

    def test_python_pip_type(self) -> None:
        """Test PYTHON_PIP type exists."""
        assert TechStack.PYTHON_PIP.value == "python_pip"

    def test_node_pnpm_type(self) -> None:
        """Test NODE_PNPM type exists."""
        assert TechStack.NODE_PNPM.value == "node_pnpm"

    def test_node_npm_type(self) -> None:
        """Test NODE_NPM type exists."""
        assert TechStack.NODE_NPM.value == "node_npm"

    def test_go_type(self) -> None:
        """Test GO type exists."""
        assert TechStack.GO.value == "go"

    def test_unknown_type(self) -> None:
        """Test UNKNOWN type exists."""
        assert TechStack.UNKNOWN.value == "unknown"


class TestTechRequirements:
    """Tests for TechRequirements data class."""

    def test_basic_creation(self) -> None:
        """Test basic TechRequirements creation."""
        req = TechRequirements(
            test_commands=["pytest"],
            lint_commands=["ruff check"],
        )
        assert req.test_commands == ["pytest"]
        assert req.lint_commands == ["ruff check"]
        assert req.type_check_commands == []
        assert req.build_commands == []

    def test_default_values(self) -> None:
        """Test default values."""
        req = TechRequirements()
        assert req.test_commands == []
        assert req.lint_commands == []
        assert req.type_check_commands == []
        assert req.build_commands == []
        assert req.source_file == ""

    def test_with_all_fields(self) -> None:
        """Test with all fields populated."""
        req = TechRequirements(
            test_commands=["pytest", "pytest tests/integration/"],
            lint_commands=["ruff check src/"],
            type_check_commands=["mypy src/"],
            build_commands=["python -m build"],
            source_file="CLAUDE.md",
        )
        assert len(req.test_commands) == 2
        assert req.lint_commands[0] == "ruff check src/"
        assert req.type_check_commands[0] == "mypy src/"
        assert req.build_commands[0] == "python -m build"
        assert req.source_file == "CLAUDE.md"


class TestDetectTechStack:
    """Tests for detect_tech_stack function."""

    def test_detect_python_uv(self) -> None:
        """Test detection of Python + uv project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()
            (project_root / "uv.lock").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.PYTHON_UV

    def test_detect_python_pip(self) -> None:
        """Test detection of Python + pip project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.PYTHON_PIP

    def test_detect_python_pip_with_requirements(self) -> None:
        """Test detection of Python + pip with requirements.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "requirements.txt").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.PYTHON_PIP

    def test_detect_node_pnpm(self) -> None:
        """Test detection of Node.js + pnpm project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "package.json").touch()
            (project_root / "pnpm-lock.yaml").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.NODE_PNPM

    def test_detect_node_npm(self) -> None:
        """Test detection of Node.js + npm project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "package.json").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.NODE_NPM

    def test_detect_go(self) -> None:
        """Test detection of Go project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "go.mod").touch()

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.GO

    def test_detect_unknown(self) -> None:
        """Test detection of unknown project type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            stack = detect_tech_stack(project_root)
            assert stack == TechStack.UNKNOWN


class TestGetDefaultCommands:
    """Tests for get_default_commands function."""

    def test_python_uv_defaults(self) -> None:
        """Test default commands for Python + uv."""
        req = get_default_commands(TechStack.PYTHON_UV)
        assert "uv run pytest" in req.test_commands
        assert "uv run ruff check src/" in req.lint_commands
        assert "uv run mypy src/" in req.type_check_commands
        assert req.build_commands == []
        assert req.source_file == "<default:python_uv>"

    def test_python_pip_defaults(self) -> None:
        """Test default commands for Python + pip."""
        req = get_default_commands(TechStack.PYTHON_PIP)
        assert "pytest" in req.test_commands
        assert "ruff check src/" in req.lint_commands
        assert "mypy src/" in req.type_check_commands

    def test_node_pnpm_defaults(self) -> None:
        """Test default commands for Node.js + pnpm."""
        req = get_default_commands(TechStack.NODE_PNPM)
        assert "pnpm test" in req.test_commands
        assert "pnpm lint" in req.lint_commands
        assert "pnpm type-check" in req.type_check_commands
        assert "pnpm build" in req.build_commands

    def test_node_npm_defaults(self) -> None:
        """Test default commands for Node.js + npm."""
        req = get_default_commands(TechStack.NODE_NPM)
        assert "npm test" in req.test_commands
        assert "npm run lint" in req.lint_commands

    def test_go_defaults(self) -> None:
        """Test default commands for Go."""
        req = get_default_commands(TechStack.GO)
        assert "go test ./..." in req.test_commands
        assert "golangci-lint run" in req.lint_commands
        assert req.type_check_commands == []  # Go 类型检查是内置的
        assert "go build" in req.build_commands

    def test_unknown_defaults(self) -> None:
        """Test default commands for unknown stack."""
        req = get_default_commands(TechStack.UNKNOWN)
        assert req.test_commands == []
        assert req.lint_commands == []
        assert req.type_check_commands == []
        assert req.build_commands == []


class TestReadTechRequirements:
    """Tests for read_tech_requirements function."""

    def test_read_from_claude_md(self) -> None:
        """Test reading from CLAUDE.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_md = project_root / "CLAUDE.md"
            claude_md.write_text(
                """# Project

```bash
uv run pytest
uv run ruff check src/
uv run mypy src/
```
""",
                encoding="utf-8",
            )

            req = read_tech_requirements(project_root)
            assert req is not None
            assert "uv run pytest" in req.test_commands
            assert "uv run ruff check src/" in req.lint_commands
            assert "uv run mypy src/" in req.type_check_commands

    def test_read_from_dot_claude_dir(self) -> None:
        """Test reading from .claude/CLAUDE.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()
            claude_md = claude_dir / "CLAUDE.md"
            claude_md.write_text(
                """```bash
pytest tests/
ruff check .
```
""",
                encoding="utf-8",
            )

            req = read_tech_requirements(project_root)
            assert req is not None
            assert "pytest tests/" in req.test_commands
            assert "ruff check ." in req.lint_commands

    def test_read_from_pyproject_toml(self) -> None:
        """Test reading from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pyproject = project_root / "pyproject.toml"
            pyproject.write_text(
                """[tool.cc-spec.tech-check]
test = ["pytest"]
lint = ["ruff check src/"]
type-check = ["mypy src/"]
build = []
""",
                encoding="utf-8",
            )

            req = read_tech_requirements(project_root)
            assert req is not None
            assert "pytest" in req.test_commands
            assert "ruff check src/" in req.lint_commands
            assert "mypy src/" in req.type_check_commands

    def test_return_none_when_no_config(self) -> None:
        """Test return None when no configuration found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            req = read_tech_requirements(project_root)
            assert req is None

    def test_skip_comment_lines(self) -> None:
        """Test that comment lines are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_md = project_root / "CLAUDE.md"
            claude_md.write_text(
                """```bash
# This is a comment
pytest tests/
# Another comment
ruff check src/
```
""",
                encoding="utf-8",
            )

            req = read_tech_requirements(project_root)
            assert req is not None
            assert len(req.test_commands) == 1
            assert len(req.lint_commands) == 1

    def test_handle_inline_comments(self) -> None:
        """Test handling of inline comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_md = project_root / "CLAUDE.md"
            claude_md.write_text(
                """```bash
pytest tests/  # Run all tests
ruff check src/  # Lint source code
```
""",
                encoding="utf-8",
            )

            req = read_tech_requirements(project_root)
            assert req is not None
            # 内联注释应该被移除
            assert any("pytest tests/" in cmd for cmd in req.test_commands)
            assert any("ruff check src/" in cmd for cmd in req.lint_commands)


class TestCheckResult:
    """Tests for CheckResult data class."""

    def test_basic_creation(self) -> None:
        """Test basic CheckResult creation."""
        result = CheckResult(
            command="pytest",
            success=True,
            output="All tests passed",
            error=None,
            duration_seconds=1.5,
            check_type="test",
        )
        assert result.command == "pytest"
        assert result.success is True
        assert result.output == "All tests passed"
        assert result.error is None
        assert result.duration_seconds == 1.5
        assert result.check_type == "test"

    def test_failed_check(self) -> None:
        """Test CheckResult for failed check."""
        result = CheckResult(
            command="ruff check src/",
            success=False,
            output="",
            error="Found 5 errors",
            duration_seconds=0.5,
            check_type="lint",
        )
        assert result.success is False
        assert result.error == "Found 5 errors"
        assert result.check_type == "lint"


class TestShouldBlock:
    """Tests for should_block function."""

    def test_test_failure_blocks(self) -> None:
        """Test that test failure blocks."""
        result = CheckResult(
            command="pytest",
            success=False,
            output="",
            error="Tests failed",
            duration_seconds=1.0,
            check_type="test",
        )
        assert should_block(result) is True

    def test_build_failure_blocks(self) -> None:
        """Test that build failure blocks."""
        result = CheckResult(
            command="npm run build",
            success=False,
            output="",
            error="Build failed",
            duration_seconds=1.0,
            check_type="build",
        )
        assert should_block(result) is True

    def test_lint_failure_does_not_block(self) -> None:
        """Test that lint failure does not block."""
        result = CheckResult(
            command="ruff check src/",
            success=False,
            output="",
            error="Lint errors",
            duration_seconds=0.5,
            check_type="lint",
        )
        assert should_block(result) is False

    def test_type_check_failure_does_not_block(self) -> None:
        """Test that type check failure does not block."""
        result = CheckResult(
            command="mypy src/",
            success=False,
            output="",
            error="Type errors",
            duration_seconds=1.0,
            check_type="type_check",
        )
        assert should_block(result) is False


class TestRunTechChecks:
    """Tests for run_tech_checks function."""

    def test_run_with_no_commands(self) -> None:
        """Test running with no commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            req = TechRequirements()

            results = run_tech_checks(req, project_root)
            assert results == []

    def test_run_with_successful_command(self) -> None:
        """Test running with a successful command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            req = TechRequirements(
                test_commands=["echo 'test passed'"],
            )

            results = run_tech_checks(req, project_root)
            assert len(results) == 1
            assert results[0].success is True
            assert results[0].check_type == "test"

    def test_check_order_execution(self) -> None:
        """Test that checks are executed in correct order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            req = TechRequirements(
                test_commands=["echo 'test'"],
                lint_commands=["echo 'lint'"],
                type_check_commands=["echo 'type-check'"],
                build_commands=["echo 'build'"],
            )

            results = run_tech_checks(req, project_root)
            assert len(results) == 4
            # 检查顺序：lint -> type_check -> test -> build
            assert results[0].check_type == "lint"
            assert results[1].check_type == "type_check"
            assert results[2].check_type == "test"
            assert results[3].check_type == "build"

    def test_selective_check_types(self) -> None:
        """Test running only selected check types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            req = TechRequirements(
                test_commands=["echo 'test'"],
                lint_commands=["echo 'lint'"],
                type_check_commands=["echo 'type-check'"],
            )

            # 只运行 lint 和 test
            results = run_tech_checks(req, project_root, check_types=["lint", "test"])
            assert len(results) == 2
            assert results[0].check_type == "lint"
            assert results[1].check_type == "test"
