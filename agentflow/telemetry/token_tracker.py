"""Per-span token attribution, budget enforcement, and shadow model ledger."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class BudgetStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


@dataclass
class BudgetResult:
    status: BudgetStatus
    consumed: int
    budget: int
    pct: float


@dataclass
class SpanRecord:
    task_id: str
    span_name: str
    tokens_in: int
    tokens_out: int
    timestamp: str
    record_type: str = "span"


class TokenTracker:
    def __init__(self, cwd: Path, config: Any) -> None:
        self._ledger_path = cwd / ".agentflow" / "ledger.json"
        self._budget = config.token_budget.per_worker
        self._records: list[dict] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def track_span(
        self,
        task_id: str,
        span_name: str,
        tokens_in: int,
        tokens_out: int,
    ) -> BudgetResult:
        record = SpanRecord(
            task_id=task_id,
            span_name=span_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            timestamp=_now(),
        )
        self._append(asdict(record))
        consumed = self.session_total(task_id)
        return _budget_result(consumed, self._budget)

    def close_session(self, task_id: str, status: str = "completed") -> None:
        record = {
            "task_id": task_id,
            "record_type": "session_close",
            "status": status,
            "timestamp": _now(),
            "total_tokens": self.session_total(task_id),
        }
        self._append(record)

    def session_total(self, task_id: str) -> int:
        return sum(
            r.get("tokens_in", 0) + r.get("tokens_out", 0)
            for r in self._records
            if r.get("task_id") == task_id and r.get("record_type") == "span"
        )

    def project_total(self) -> int:
        return sum(
            r.get("tokens_in", 0) + r.get("tokens_out", 0)
            for r in self._records
            if r.get("record_type") == "span"
        )

    def shadow_total(self) -> int:
        """Shadow = real tokens + accumulated prior-task output injected as context."""
        task_ids = _ordered_unique(
            r["task_id"]
            for r in self._records
            if r.get("record_type") == "span"
        )
        shadow = 0
        accumulated_output = 0
        for task_id in task_ids:
            task_in = sum(
                r["tokens_in"]
                for r in self._records
                if r.get("task_id") == task_id and r.get("record_type") == "span"
            )
            task_out = sum(
                r["tokens_out"]
                for r in self._records
                if r.get("task_id") == task_id and r.get("record_type") == "span"
            )
            shadow += (task_in + accumulated_output) + task_out
            accumulated_output += task_out
        return shadow

    def report(self) -> dict:
        real = self.project_total()
        shadow = self.shadow_total()
        task_ids = _ordered_unique(
            r["task_id"]
            for r in self._records
            if r.get("record_type") == "span"
        )
        return {
            "real_total": real,
            "shadow_total": shadow,
            "ratio": round(shadow / real, 3) if real > 0 else 0.0,
            "task_count": len(task_ids),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        if not self._ledger_path.exists():
            return []
        try:
            data = json.loads(self._ledger_path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _append(self, record: dict) -> None:
        self._records.append(record)
        self._write()

    def _write(self) -> None:
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._records, indent=2))
        os.replace(tmp, self._ledger_path)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _budget_result(consumed: int, budget: int) -> BudgetResult:
    pct = consumed / budget if budget > 0 else 0.0
    if pct >= 1.0:
        status = BudgetStatus.EXCEEDED
    elif pct >= 0.8:
        status = BudgetStatus.WARNING
    else:
        status = BudgetStatus.OK
    return BudgetResult(status=status, consumed=consumed, budget=budget, pct=round(pct, 4))


def _ordered_unique(iterable) -> list:
    seen: set = set()
    result = []
    for item in iterable:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
