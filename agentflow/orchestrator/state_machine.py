from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class InvalidTransitionError(Exception):
    pass


STATES = [
    "PENDING", "SPAWNED", "IMPLEMENTING", "PR_OPEN",
    "REVIEW_IN_PROGRESS", "REVIEW_PASSED", "REWORK_NEEDED",
    "HUMAN_APPROVED", "MERGED",
]


def transition(state_path: Path, task_id: str, new_state: str) -> None:
    raise NotImplementedError


def load_state(state_path: Path) -> dict:
    raise NotImplementedError
