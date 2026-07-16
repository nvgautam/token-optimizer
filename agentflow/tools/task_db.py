#!/usr/bin/env python3
"""SQLite-backed task store with WAL mode and atomic writes.

Schema: tasks(task_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending', definition TEXT)
where definition holds the full JSON blob of the task entry.

After every write, tasks.json is regenerated from the DB (single-writer pattern)
so that cleanup_tasks.py and orchestrate.md reads continue to work without
modification.
"""
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional


class TaskDB:
    """Atomic SQLite task store.

    WAL mode is enabled on open.  All mutations are atomic transactions.
    Idempotent: calling mark_complete on an already-complete task is safe.
    """

    def __init__(
        self,
        db_path: Path,
        tasks_json_path: Optional[Path] = None,
    ) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.tasks_json_path = tasks_json_path
        self._init_db()
        if tasks_json_path and tasks_json_path.exists():
            self._bootstrap_from_json()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    task_id    TEXT PRIMARY KEY,
                    status     TEXT NOT NULL DEFAULT 'pending',
                    definition TEXT
                )"""
            )
            conn.commit()

    def _bootstrap_from_json(self) -> None:
        """Populate an empty DB from tasks.json (one-time migration path)."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if count > 0:
                return

        if self.tasks_json_path is None or not self.tasks_json_path.exists():
            return
        try:
            data = json.loads(self.tasks_json_path.read_text())
        except Exception:
            return

        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for t in data.get("tasks", []):
                task_id = t.get("task_id")
                if not task_id:
                    continue
                status = t.get("status", "pending")
                conn.execute(
                    "INSERT OR IGNORE INTO tasks (task_id, status, definition)"
                    " VALUES (?, ?, ?)",
                    (task_id, status, json.dumps(t)),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_complete(self, task_id: str) -> str:
        """Mark task complete.

        Returns:
            'marked'          — task was pending and is now complete
            'already_complete'— task was already complete (idempotent)
            'not_found'       — task_id does not exist in the DB
        """
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            row = conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row["status"] != "pending":
                return "already_complete"
            conn.execute(
                "UPDATE tasks SET status = 'complete' WHERE task_id = ?",
                (task_id,),
            )
            conn.commit()
        self._sync_tasks_json()
        return "marked"

    def get_pending_tasks(self) -> list:
        """Return list of task dicts with status='pending'."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, status, definition FROM tasks WHERE status = 'pending'"
            ).fetchall()
        result = []
        for row in rows:
            t: dict = {}
            if row["definition"]:
                try:
                    t.update(json.loads(row["definition"]))
                except Exception:
                    pass
            # DB values always win over stale definition fields
            t["task_id"] = row["task_id"]
            t["status"] = row["status"]
            result.append(t)
        return result

    def upsert_task(
        self,
        task_id: str,
        status: str = "pending",
        definition: Optional[dict] = None,
    ) -> None:
        """Insert or replace a task (idempotent)."""
        def_str = json.dumps(definition) if definition is not None else None
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO tasks (task_id, status, definition) VALUES (?, ?, ?)"
                " ON CONFLICT(task_id) DO UPDATE SET"
                " status = excluded.status,"
                " definition = excluded.definition",
                (task_id, status, def_str),
            )
            conn.commit()
        self._sync_tasks_json()

    # ------------------------------------------------------------------
    # tasks.json sync
    # ------------------------------------------------------------------

    def _sync_tasks_json(self) -> None:
        """Atomically regenerate tasks.json from the DB."""
        if self.tasks_json_path is None:
            return
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, status, definition FROM tasks ORDER BY rowid"
            ).fetchall()
        tasks = []
        for row in rows:
            t: dict = {}
            if row["definition"]:
                try:
                    t.update(json.loads(row["definition"]))
                except Exception:
                    pass
            # DB values always win over stale definition fields
            t["task_id"] = row["task_id"]
            t["status"] = row["status"]
            tasks.append(t)
        data = {"tasks": tasks}
        try:
            self.tasks_json_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.tasks_json_path.parent,
                delete=False,
                suffix=".tmp",
                encoding="utf-8",
            ) as tmp:
                json.dump(data, tmp, indent=2)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, self.tasks_json_path)
        except Exception:
            pass
