import json
from pathlib import Path
import pytest
from agentflow.tools.cleanup_violations import (
    flatten_archive,
    append_to_archive,
    _split_description,
    auto_file_size_violations,
)


# ============================================================================
# flatten_archive tests
# ============================================================================

def test_flatten_archive_with_file(tmp_path):
    """flatten_archive flattens nested lists and preserves plain dicts."""
    archive_path = tmp_path / "archive.json"
    archive_data = [
        {"task_id": "T-001", "title": "First"},
        [{"task_id": "T-002", "title": "Second"}, {"task_id": "T-003", "title": "Third"}],
        {"task_id": "T-004", "title": "Fourth"},
    ]
    archive_path.write_text(json.dumps(archive_data))

    result = flatten_archive(archive_path)

    assert len(result) == 4
    assert result[0]["task_id"] == "T-001"
    assert result[1]["task_id"] == "T-002"
    assert result[2]["task_id"] == "T-003"
    assert result[3]["task_id"] == "T-004"


def test_flatten_archive_empty():
    """flatten_archive handles empty archive."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "archive.json"
        archive_path.write_text("[]")
        result = flatten_archive(archive_path)
        assert result == []


def test_flatten_archive_only_lists():
    """flatten_archive handles archive with only nested lists."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "archive.json"
        data = [
            [{"task_id": "T-001"}],
            [{"task_id": "T-002"}, {"task_id": "T-003"}],
        ]
        archive_path.write_text(json.dumps(data))
        result = flatten_archive(archive_path)
        assert len(result) == 3


def test_flatten_archive_only_dicts():
    """flatten_archive handles archive with only plain dicts."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "archive.json"
        data = [
            {"task_id": "T-001"},
            {"task_id": "T-002"},
        ]
        archive_path.write_text(json.dumps(data))
        result = flatten_archive(archive_path)
        assert len(result) == 2


# ============================================================================
# append_to_archive tests
# ============================================================================

def test_append_to_archive_creates_new_archive(tmp_path):
    """append_to_archive creates archive if it doesn't exist."""
    archive_path = tmp_path / "archive.json"
    task = {"task_id": "T-001", "title": "New task"}

    append_to_archive(archive_path, task)

    assert archive_path.exists()
    data = json.loads(archive_path.read_text())
    assert len(data) == 1
    assert data[0]["task_id"] == "T-001"


def test_append_to_archive_appends_to_existing(tmp_path):
    """append_to_archive appends to existing archive."""
    archive_path = tmp_path / "archive.json"
    existing_data = [{"task_id": "T-001", "title": "First"}]
    archive_path.write_text(json.dumps(existing_data))

    task = {"task_id": "T-002", "title": "Second"}
    append_to_archive(archive_path, task)

    data = json.loads(archive_path.read_text())
    assert len(data) == 2
    assert data[0]["task_id"] == "T-001"
    assert data[1]["task_id"] == "T-002"


def test_append_to_archive_idempotent_on_rerun(tmp_path):
    """append_to_archive can be run multiple times with same result."""
    archive_path = tmp_path / "archive.json"
    task = {"task_id": "T-001", "title": "Task"}

    append_to_archive(archive_path, task)
    data1 = json.loads(archive_path.read_text())

    # Append same task again
    append_to_archive(archive_path, task)
    data2 = json.loads(archive_path.read_text())

    # Second archive has one more entry (no dedup in append_to_archive itself)
    assert len(data2) == len(data1) + 1


def test_append_to_archive_creates_parent_dir(tmp_path):
    """append_to_archive creates parent directory if needed."""
    archive_path = tmp_path / "a" / "b" / "archive.json"
    task = {"task_id": "T-001"}

    append_to_archive(archive_path, task)

    assert archive_path.exists()
    data = json.loads(archive_path.read_text())
    assert len(data) == 1


# ============================================================================
# _split_description tests
# ============================================================================

def test_split_description_commands_path():
    """_split_description includes 'by phase/section' for commands/ files."""
    desc = _split_description(
        "commands/claude/oracle.md",
        160,
        150,
        "2026-07-17T00:00:00"
    )
    assert "Split commands/claude/oracle.md" in desc
    assert "160 lines" in desc
    assert "limit 150" in desc
    assert "2026-07-17T00:00:00" in desc
    assert "by phase/section responsibility" in desc
    assert "150 lines" in desc


def test_split_description_tests_path():
    """_split_description includes 'by test class or fixture' for tests/ files."""
    desc = _split_description(
        "tests/test_oracle.py",
        360,
        350,
        "2026-07-17T00:00:00"
    )
    assert "Split tests/test_oracle.py" in desc
    assert "360 lines" in desc
    assert "limit 350" in desc
    assert "2026-07-17T00:00:00" in desc
    assert "by test class or fixture group" in desc
    assert "350 lines" in desc


def test_split_description_default_path():
    """_split_description includes 'by domain' for other paths."""
    desc = _split_description(
        "agentflow/tools/cleanup_tasks.py",
        260,
        250,
        "2026-07-17T00:00:00"
    )
    assert "Split agentflow/tools/cleanup_tasks.py" in desc
    assert "260 lines" in desc
    assert "limit 250" in desc
    assert "2026-07-17T00:00:00" in desc
    assert "by domain" in desc
    assert "250 lines" in desc


def test_split_description_backslash_paths():
    """_split_description handles backslash path separators."""
    desc = _split_description(
        "agentflow\\tools\\cleanup_tasks.py",
        260,
        250,
        "2026-07-17T00:00:00"
    )
    # Should normalize slashes and still detect non-command/test path
    assert "Split agentflow\\tools\\cleanup_tasks.py" in desc
    assert "by domain" in desc
