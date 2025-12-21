"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.state import ChangeState, Stage, StageInfo, TaskInfo, TaskStatus, update_state
from cc_spec.utils.files import get_cc_spec_dir

# Add src directory to Python path for tests
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
tests_path = Path(__file__).parent
sys.path.insert(0, str(tests_path))


@dataclass
class TestProject:
    """Test helper to build minimal cc-spec project structures."""

    root: Path

    @property
    def cc_spec_dir(self) -> Path:
        return get_cc_spec_dir(self.root)

    @property
    def changes_dir(self) -> Path:
        return self.cc_spec_dir / "changes"

    def init_structure(self, include_templates: bool = False) -> None:
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        (self.cc_spec_dir / "changes").mkdir(parents=True, exist_ok=True)
        (self.cc_spec_dir / "specs").mkdir(parents=True, exist_ok=True)
        (self.cc_spec_dir / "archive").mkdir(parents=True, exist_ok=True)
        if include_templates:
            (self.cc_spec_dir / "templates").mkdir(parents=True, exist_ok=True)

    def create_change(self, name: str = "test-change") -> Path:
        change_dir = self.changes_dir / name
        change_dir.mkdir(parents=True, exist_ok=True)
        return change_dir

    def write_proposal(self, change_dir: Path, content: str | None = None) -> Path:
        if content is None:
            content = """# Proposal

## Why

Need this change.

## What Changes

- Add something

## Impact

- Low risk
"""
        proposal_path = change_dir / "proposal.md"
        proposal_path.write_text(content, encoding="utf-8")
        return proposal_path

    def write_tasks_yaml(self, change_dir: Path, content: str | None = None) -> Path:
        if content is None:
            content = """version: "1.6"
change: test-change
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    deps: []
    checklist:
      - Prepare workspace
"""
        tasks_path = change_dir / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def write_status(
        self,
        change_dir: Path,
        change_name: str,
        current_stage: Stage = Stage.SPECIFY,
        tasks: Iterable[dict[str, object]] | None = None,
    ) -> Path:
        now = datetime.now().isoformat()
        state = ChangeState(
            change_name=change_name,
            created_at=now,
            current_stage=current_stage,
            stages={
                Stage.SPECIFY: StageInfo(status=TaskStatus.COMPLETED, started_at=now, completed_at=now),
                Stage.CLARIFY: StageInfo(status=TaskStatus.PENDING),
                Stage.PLAN: StageInfo(status=TaskStatus.PENDING),
                Stage.APPLY: StageInfo(status=TaskStatus.PENDING),
                Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
            tasks=[],
        )

        if tasks:
            for task in tasks:
                state.tasks.append(
                    TaskInfo(
                        id=str(task.get("id", "")),
                        status=TaskStatus(task.get("status", TaskStatus.PENDING.value)),
                        wave=int(task.get("wave", 0)),
                    )
                )

        status_path = change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def invoke(cli_runner: CliRunner):
    def _invoke(args: list[str], cwd: Path | None = None):
        if cwd is None:
            return cli_runner.invoke(app, args)
        original = Path.cwd()
        os.chdir(cwd)
        try:
            return cli_runner.invoke(app, args)
        finally:
            os.chdir(original)

    return _invoke


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestProject:
    proj = TestProject(root=tmp_path)
    proj.init_structure()
    monkeypatch.chdir(tmp_path)
    return proj


@pytest.fixture
def project_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _factory(init_structure: bool = True) -> TestProject:
        proj = TestProject(root=tmp_path)
        if init_structure:
            proj.init_structure()
        monkeypatch.chdir(tmp_path)
        return proj

    return _factory


@pytest.fixture
def change_name() -> str:
    return "test-change"


@pytest.fixture
def change_dir(project: TestProject, change_name: str) -> Path:
    return project.create_change(change_name)


@pytest.fixture
def proposal_file(project: TestProject, change_dir: Path) -> Path:
    return project.write_proposal(change_dir)


@pytest.fixture
def tasks_yaml(project: TestProject, change_dir: Path) -> Path:
    return project.write_tasks_yaml(change_dir)


@pytest.fixture
def status_yaml(
    project: TestProject,
    change_dir: Path,
    change_name: str,
) -> Path:
    return project.write_status(change_dir, change_name)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = Path(str(item.fspath))
        if "tests" not in path.parts:
            continue
        try:
            tests_index = path.parts.index("tests")
        except ValueError:
            continue
        if len(path.parts) <= tests_index + 1:
            continue
        group = path.parts[tests_index + 1]
        if group in {"unit", "cli", "rag", "codex", "integration"}:
            item.add_marker(getattr(pytest.mark, group))
