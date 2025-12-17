"""Unit tests for KB scan and ignore rules."""

from __future__ import annotations

from cc_spec.rag.scanner import (
    ScanSettings,
    build_file_hash_map,
    diff_file_hash_map,
    scan_project,
)


def test_scan_project_respects_cc_specignore_and_default_rules(tmp_path) -> None:
    (tmp_path / ".cc-specignore").write_text(
        "\n".join(
            [
                "src/",
                "!src/keep.txt",
                "secret.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "src" / "ignored.txt").write_text("ignored", encoding="utf-8")

    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("print('x')", encoding="utf-8")

    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "info.md").write_text("ref", encoding="utf-8")

    # Binary file (contains NUL) should be excluded
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02")

    # Too large file should be included as index-only (reason=too_large)
    (tmp_path / "large.txt").write_text("0123456789ABCDEF", encoding="utf-8")

    files, report = scan_project(tmp_path, settings=ScanSettings(max_file_bytes=10))
    by_path = {f.rel_path.as_posix(): f for f in files}

    assert "README.md" in by_path
    assert "src/keep.txt" in by_path
    assert "reference/info.md" in by_path

    assert "secret.txt" not in by_path
    assert "src/ignored.txt" not in by_path
    assert "binary.bin" not in by_path
    assert ".venv/ignored.py" not in by_path

    assert "large.txt" in by_path
    assert by_path["large.txt"].reason == "too_large"
    assert by_path["large.txt"].is_text is False
    assert by_path["large.txt"].sha256 is None

    assert by_path["reference/info.md"].is_reference is True

    hashes = build_file_hash_map(files)
    assert "README.md" in hashes
    assert "src/keep.txt" in hashes
    assert "reference/info.md" in hashes
    assert "large.txt" not in hashes  # too_large / not text

    assert report.included >= 3
    assert report.excluded >= 1


def test_diff_file_hash_map_reports_added_changed_removed() -> None:
    old = {"a": "1", "b": "1"}
    new = {"b": "2", "c": "1"}

    added, changed, removed = diff_file_hash_map(old, new)

    assert added == ["c"]
    assert changed == ["b"]
    assert removed == ["a"]

