from pathlib import Path
from dataclasses import dataclass


@dataclass
class WriteResult:
    ok: bool
    path: str


class SandboxViolationError(Exception):
    pass


def set_owns_list(task_id: str, owns: list[str]) -> None:
    raise NotImplementedError


def write_file(project_root: Path, path: Path, contents: str) -> WriteResult:
    raise NotImplementedError
