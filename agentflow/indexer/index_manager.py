from pathlib import Path
from typing import Any


def get_index(project_root: Path, file_path: Path) -> dict | None:
    raise NotImplementedError


def update_index(project_root: Path, file_path: Path, contents: str) -> None:
    raise NotImplementedError
