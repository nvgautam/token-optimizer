from pathlib import Path
from dataclasses import dataclass


@dataclass
class ScanResult:
    indexed: int
    skipped: int
    duration_ms: int


def scan(project_root: Path, config) -> ScanResult:
    raise NotImplementedError
