"""Integration tests for cc-spec workflow (v0.2.x).

Focus: init/specify/plan/accept/archive work together without legacy checklist stages.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.state import Stage, TaskStatus, load_state

runner = CliRunner()


class TestFullWorkflow:
    def setup_method(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_command(self) -> None:
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["init", "--agent", "claude"])
        assert result.exit_code == 0
        assert (self.project_root / ".cc-spec").exists()
        assert (self.project_root / ".cc-spec" / "config.yaml").exists()

    def test_specify_and_plan(self) -> None:
        os.chdir(str(self.project_root))
        runner.invoke(app, ["init", "--agent", "claude"])
        assert runner.invoke(app, ["specify", "add-feature"]).exit_code == 0
        assert runner.invoke(app, ["plan", "add-feature"]).exit_code == 0

        status_path = self.project_root / ".cc-spec" / "changes" / "add-feature" / "status.yaml"
        state = load_state(status_path)
        assert state.current_stage == Stage.PLAN

    def test_accept_updates_state(self) -> None:
        os.chdir(str(self.project_root))
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])

        # Make accept deterministic: all checks pass.
        ok = type("obj", (object,), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("cc_spec.commands.accept.subprocess.run", return_value=ok):
            result = runner.invoke(app, ["accept", "test-change"])
            assert result.exit_code == 0

        status_path = self.project_root / ".cc-spec" / "changes" / "test-change" / "status.yaml"
        state = load_state(status_path)
        assert state.current_stage == Stage.ACCEPT
        assert state.stages[Stage.ACCEPT].status == TaskStatus.COMPLETED

    def test_archive_requires_accept(self) -> None:
        os.chdir(str(self.project_root))
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "to-archive"])

        # Without accept, archive should fail.
        result = runner.invoke(app, ["archive", "to-archive", "--force"])
        assert result.exit_code == 1

        ok = type("obj", (object,), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("cc_spec.commands.accept.subprocess.run", return_value=ok):
            assert runner.invoke(app, ["accept", "to-archive"]).exit_code == 0

        result = runner.invoke(app, ["archive", "to-archive", "--force"])
        assert result.exit_code == 0
