"""Tests for agentflow.tools.task_db — SQLite-backed task store."""
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from agentflow.tools.task_db import TaskDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed(db: TaskDB, task_id: str, status: str = "pending") -> None:
    db.upsert_task(task_id, status=status)


# ---------------------------------------------------------------------------
# mark_complete
# ---------------------------------------------------------------------------

def test_mark_complete_pending_task(tmp_path: Path) -> None:
    db = TaskDB(tmp_path / "tasks.db")
    _seed(db, "T-001", "pending")
    result = db.mark_complete("T-001")
    assert result == "marked"


def test_mark_complete_idempotent(tmp_path: Path) -> None:
    db = TaskDB(tmp_path / "tasks.db")
    _seed(db, "T-001", "pending")
    db.mark_complete("T-001")
    result = db.mark_complete("T-001")
    assert result == "already_complete"


def test_mark_complete_not_found(tmp_path: Path) -> None:
    db = TaskDB(tmp_path / "tasks.db")
    result = db.mark_complete("T-999")
    assert result == "not_found"


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------

def test_wal_mode_enabled(tmp_path: Path) -> None:
    TaskDB(tmp_path / "tasks.db")
    conn = sqlite3.connect(str(tmp_path / "tasks.db"))
    row = conn.execute("PRAGMA journal_mode").fetchone()
    conn.close()
    assert row[0] == "wal"


# ---------------------------------------------------------------------------
# Concurrent writes
# ---------------------------------------------------------------------------

def test_concurrent_writes(tmp_path: Path) -> None:
    db = TaskDB(tmp_path / "tasks.db")
    _seed(db, "T-001", "pending")
    _seed(db, "T-002", "pending")

    errors: list[Exception] = []

    def mark(task_id: str) -> None:
        try:
            result = db.mark_complete(task_id)
            assert result in ("marked", "already_complete", "not_found")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=mark, args=("T-001",))
    t2 = threading.Thread(target=mark, args=("T-002",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []


# ---------------------------------------------------------------------------
# get_pending_tasks
# ---------------------------------------------------------------------------

def test_get_pending_tasks(tmp_path: Path) -> None:
    db = TaskDB(tmp_path / "tasks.db")
    _seed(db, "T-001", "pending")
    _seed(db, "T-002", "pending")
    _seed(db, "T-003", "pending")
    db.mark_complete("T-002")

    pending = db.get_pending_tasks()
    pending_ids = {t["task_id"] for t in pending}
    assert "T-001" in pending_ids
    assert "T-003" in pending_ids
    assert "T-002" not in pending_ids


# ---------------------------------------------------------------------------
# tasks.json sync
# ---------------------------------------------------------------------------

def test_tasks_json_sync(tmp_path: Path) -> None:
    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(json.dumps({"tasks": [{"task_id": "T-001", "status": "pending"}]}, indent=2))
    db = TaskDB(tmp_path / "tasks.db", tasks_json_path=tasks_json)
    # ensure task is in DB (bootstrap loaded it)
    db.mark_complete("T-001")

    data = json.loads(tasks_json.read_text())
    matched = [t for t in data["tasks"] if t["task_id"] == "T-001"]
    assert matched, "T-001 not found in synced tasks.json"
    assert matched[0]["status"] == "complete"


# ---------------------------------------------------------------------------
# definition roundtrip
# ---------------------------------------------------------------------------

def test_definition_roundtrip(tmp_path: Path) -> None:
    definition = {"title": "Test task", "nested": {"key": "value"}, "tags": [1, 2, 3]}
    db = TaskDB(tmp_path / "tasks.db")
    db.upsert_task("T-001", status="pending", definition=definition)

    pending = db.get_pending_tasks()
    assert len(pending) == 1
    task = pending[0]
    assert task["task_id"] == "T-001"
    assert task.get("title") == "Test task"
    assert task.get("nested") == {"key": "value"}
    assert task.get("tags") == [1, 2, 3]


# ---------------------------------------------------------------------------
# missing DB path (directory auto-create)
# ---------------------------------------------------------------------------

def test_missing_db_path(tmp_path: Path) -> None:
    db_path = tmp_path / "deep" / "nested" / "dir" / "tasks.db"
    assert not db_path.parent.exists(), "parent dir should not exist yet"
    db = TaskDB(db_path)
    db.upsert_task("T-001", status="pending")
    result = db.mark_complete("T-001")
    assert result == "marked"
    assert db_path.exists()
