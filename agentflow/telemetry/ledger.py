from pathlib import Path
from typing import Any


def read_ledger(path: Path) -> dict:
    raise NotImplementedError


def write_ledger(path: Path, data: dict) -> None:
    raise NotImplementedError


def session_total(path: Path, task_id: str) -> int:
    raise NotImplementedError


def project_total(path: Path) -> int:
    raise NotImplementedError
