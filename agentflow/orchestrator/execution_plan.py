from pathlib import Path
from typing import Optional


def write_execution_plan(architecture_path: Path, output_path: Path) -> None:
    raise NotImplementedError


def resume_from(execution_plan_path: Path) -> Optional[dict]:
    raise NotImplementedError
