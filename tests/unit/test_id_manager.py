"""Unit tests for ID manager module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from cc_spec.core.id_manager import (
    ArchiveEntry,
    ChangeEntry,
    IDManager,
    IDMap,
    IDType,
    ParsedID,
    SpecEntry,
)


class TestIDType:
    """Tests for IDType enum."""

    def test_change_type(self) -> None:
        assert IDType.CHANGE.value == "C"

    def test_task_type(self) -> None:
        assert IDType.TASK.value == "T"

    def test_spec_type(self) -> None:
        assert IDType.SPEC.value == "S"

    def test_archive_type(self) -> None:
        assert IDType.ARCHIVE.value == "A"


class TestParsedID:
    """Tests for ParsedID dataclass."""

    def test_change_parsed_id(self) -> None:
        parsed = ParsedID(
            type=IDType.CHANGE,
            change_id="C-001",
            task_id=None,
            full_id="C-001",
        )
        assert parsed.type == IDType.CHANGE
        assert parsed.change_id == "C-001"
        assert parsed.task_id is None

    def test_task_parsed_id(self) -> None:
        parsed = ParsedID(
            type=IDType.TASK,
            change_id="C-001",
            task_id="02-MODEL",
            full_id="C-001:02-MODEL",
        )
        assert parsed.type == IDType.TASK
        assert parsed.change_id == "C-001"
        assert parsed.task_id == "02-MODEL"


class TestIDMap:
    """Tests for IDMap dataclass."""

    def test_empty_id_map(self) -> None:
        id_map = IDMap()
        assert id_map.version == "1.0"
        assert id_map.changes == {}
        assert id_map.specs == {}
        assert id_map.archive == {}
        assert id_map.next_change_id == 1

    def test_id_map_to_dict(self) -> None:
        id_map = IDMap()
        id_map.changes["C-001"] = ChangeEntry(
            name="test-change",
            path="changes/test-change",
            created="2024-01-15T10:00:00",
        )
        id_map.next_change_id = 2

        data = id_map.to_dict()

        assert data["version"] == "1.0"
        assert "C-001" in data["changes"]
        assert data["changes"]["C-001"]["name"] == "test-change"
        assert data["next_change_id"] == 2

    def test_id_map_from_dict(self) -> None:
        data = {
            "version": "1.0",
            "changes": {
                "C-001": {
                    "name": "test-change",
                    "path": "changes/test-change",
                    "created": "2024-01-15T10:00:00",
                }
            },
            "specs": {},
            "archive": {},
            "next_change_id": 2,
        }

        id_map = IDMap.from_dict(data)

        assert id_map.version == "1.0"
        assert "C-001" in id_map.changes
        assert id_map.changes["C-001"].name == "test-change"
        assert id_map.next_change_id == 2


class TestIDManager:
    """Tests for IDManager class."""

    @pytest.fixture
    def temp_cc_spec(self) -> Path:
        """Create a temporary .cc-spec directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cc_spec_root = Path(tmpdir) / ".cc-spec"
            cc_spec_root.mkdir(parents=True)
            yield cc_spec_root

    def test_init_creates_id_map(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        assert manager.id_map_path.exists()
        assert manager._id_map is not None

    def test_generate_change_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        id1 = manager.generate_change_id()
        id2 = manager.generate_change_id()
        id3 = manager.generate_change_id()

        assert id1 == "C-001"
        assert id2 == "C-002"
        assert id3 == "C-003"

    def test_parse_change_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        parsed = manager.parse_id("C-001")

        assert parsed.type == IDType.CHANGE
        assert parsed.change_id == "C-001"
        assert parsed.task_id is None
        assert parsed.full_id == "C-001"

    def test_parse_task_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        parsed = manager.parse_id("C-001:02-MODEL")

        assert parsed.type == IDType.TASK
        assert parsed.change_id == "C-001"
        assert parsed.task_id == "02-MODEL"
        assert parsed.full_id == "C-001:02-MODEL"

    def test_parse_spec_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        parsed = manager.parse_id("S-auth")

        assert parsed.type == IDType.SPEC
        assert parsed.change_id is None
        assert parsed.task_id is None
        assert parsed.full_id == "S-auth"

    def test_parse_archive_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        parsed = manager.parse_id("A-20240115-001")

        assert parsed.type == IDType.ARCHIVE
        assert parsed.change_id is None
        assert parsed.task_id is None
        assert parsed.full_id == "A-20240115-001"

    def test_parse_invalid_task_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        with pytest.raises(ValueError):
            manager.parse_id("invalid:task")

    def test_register_change(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        change_id = manager.register_change("test-change", change_path)

        assert change_id == "C-001"
        assert change_id in manager._id_map.changes
        assert manager._id_map.changes[change_id].name == "test-change"

    def test_resolve_path_for_change(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        change_id = manager.register_change("test-change", change_path)
        resolved = manager.resolve_path(change_id)

        assert resolved is not None
        assert resolved.name == "test-change"

    def test_resolve_path_for_nonexistent(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        resolved = manager.resolve_path("C-999")

        assert resolved is None

    def test_register_spec(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        spec_path = temp_cc_spec / "specs" / "auth"
        spec_path.mkdir(parents=True)

        spec_id = manager.register_spec("auth", spec_path)

        assert spec_id == "S-auth"
        assert spec_id in manager._id_map.specs

    def test_register_archive(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        archive_path = temp_cc_spec / "changes" / "archive" / "2024-01-15-test"
        archive_path.mkdir(parents=True)

        archive_id = manager.register_archive("test", archive_path)

        assert archive_id.startswith("A-")
        assert archive_id in manager._id_map.archive

    def test_unregister_change(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        change_id = manager.register_change("test-change", change_path)
        result = manager.unregister_change(change_id)

        assert result is True
        assert change_id not in manager._id_map.changes

    def test_unregister_nonexistent_change(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        result = manager.unregister_change("C-999")

        assert result is False

    def test_get_change_entry(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        change_id = manager.register_change("test-change", change_path)
        entry = manager.get_change_entry(change_id)

        assert entry is not None
        assert entry.name == "test-change"

    def test_get_change_by_name(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        manager.register_change("test-change", change_path)
        result = manager.get_change_by_name("test-change")

        assert result is not None
        change_id, entry = result
        assert change_id == "C-001"
        assert entry.name == "test-change"

    def test_list_changes(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)

        # Register some changes
        for i in range(3):
            change_path = temp_cc_spec / "changes" / f"change-{i}"
            change_path.mkdir(parents=True)
            manager.register_change(f"change-{i}", change_path)

        changes = manager.list_changes()

        assert len(changes) == 3
        assert "C-001" in changes
        assert "C-002" in changes
        assert "C-003" in changes

    def test_is_valid_id(self, temp_cc_spec: Path) -> None:
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)

        change_id = manager.register_change("test-change", change_path)

        assert manager.is_valid_id(change_id) is True
        assert manager.is_valid_id("C-999") is False

    def test_persistence(self, temp_cc_spec: Path) -> None:
        """Test that ID map persists across manager instances."""
        # Create first manager and register a change
        manager1 = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)
        change_id = manager1.register_change("test-change", change_path)

        # Create second manager and verify data persisted
        manager2 = IDManager(temp_cc_spec)

        assert change_id in manager2._id_map.changes
        assert manager2._id_map.changes[change_id].name == "test-change"

    def test_resolve_by_name(self, temp_cc_spec: Path) -> None:
        """Test resolving ID by change name."""
        manager = IDManager(temp_cc_spec)
        change_path = temp_cc_spec / "changes" / "my-feature"
        change_path.mkdir(parents=True)
        manager.register_change("my-feature", change_path)

        parsed = manager.parse_id("my-feature")

        assert parsed.type == IDType.CHANGE
        assert parsed.change_id == "C-001"

    def test_scan_existing_changes(self, temp_cc_spec: Path) -> None:
        """Test scanning existing change directories."""
        # Create changes directory with existing changes
        changes_dir = temp_cc_spec / "changes"
        change1 = changes_dir / "existing-change-1"
        change1.mkdir(parents=True)
        (change1 / "status.yaml").write_text(
            "change_name: existing-change-1\ncurrent_stage: specify\n"
        )

        change2 = changes_dir / "existing-change-2"
        change2.mkdir(parents=True)
        (change2 / "status.yaml").write_text(
            "change_name: existing-change-2\ncurrent_stage: plan\n"
        )

        # Create manager (should scan existing changes)
        manager = IDManager(temp_cc_spec)

        changes = manager.list_changes()
        assert len(changes) == 2

    def test_rebuild_from_directory(self, temp_cc_spec: Path) -> None:
        """Test rebuilding ID map from directories."""
        manager = IDManager(temp_cc_spec)

        # Register some changes
        change_path = temp_cc_spec / "changes" / "test-change"
        change_path.mkdir(parents=True)
        (change_path / "status.yaml").write_text(
            "change_name: test-change\ncurrent_stage: specify\n"
        )
        manager.register_change("test-change", change_path)

        # Corrupt the ID map
        manager._id_map = IDMap()
        manager._save_id_map()

        # Rebuild
        manager.rebuild_from_directory()

        changes = manager.list_changes()
        assert len(changes) == 1
