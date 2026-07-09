"""Shared fixtures for agentflow.shell tests."""
from __future__ import annotations
import pathlib
from unittest.mock import patch
import pytest
from agentflow.shell.session_manager import SessionManager


@pytest.fixture(autouse=True)
def mock_cwd(tmp_path):
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        yield


class FakePTY:
    def __init__(self):
        self._on_output = self._on_exit = None
        self.inputs: list[str] = []
        self._exited = False
        self._command = ["claude"]
    def write_input(self, text: str) -> None:
        self.inputs.append(text)
    def read_output(self, timeout: float = 1.0) -> bytes:
        return b""


class FakeTokenizer:
    def __init__(self, fixed_return: int | None = None):
        self._total = 0
        self._fixed = fixed_return
    def count_tokens(self, text: str, provider: str = "claude") -> int:
        return self._fixed if self._fixed is not None else 1
    def accumulate(self, text: str, provider: str = "claude") -> int:
        if self._fixed is not None:
            return self._fixed
        self._total += 1
        return self._total
    def reset(self) -> None:
        self._total = 0


def make_manager(config=None, tokenizer=None):
    pty = FakePTY()
    tok = tokenizer or FakeTokenizer()
    return SessionManager(pty, tok, config or {}), pty, tok


def fire_output(sm: SessionManager, pty: FakePTY, text: str) -> None:
    if pty._on_output:
        pty._on_output(text.encode())
