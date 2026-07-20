"""Integration tests: SessionManager + oracle_consent module."""
from __future__ import annotations
from unittest.mock import patch

import pytest

from agentflow.shell.oracle_consent import _CONSENT_PROMPT
from tests.shell.test_oracle_consent import (
    _oracle_manager,
    FakeTokenizer,
    make_manager,
)


def test_session_manager_has_oracle_consent_fields(tmp_path):
    sm, pty = _oracle_manager(tmp_path)
    assert hasattr(sm, "_oracle_consent_pending")
    assert hasattr(sm, "_oracle_consent_fired")
    assert hasattr(sm, "_oracle_consent_confirmed")
    assert sm._oracle_consent_pending is False
    assert sm._oracle_consent_fired is False
    assert sm._oracle_consent_confirmed is False


def test_session_manager_on_idle_tick_triggers_consent(tmp_path):
    sm, pty = _oracle_manager(tmp_path, threshold=90_000, tokens=90_000)
    with patch("os.write"):
        sm.on_idle_tick()
    assert any(_CONSENT_PROMPT in inp for inp in pty.inputs)


def test_non_oracle_session_at_90k_unchanged(tmp_path):
    tok = FakeTokenizer(fixed_return=90_000)
    sm, pty, _ = make_manager(tokenizer=tok)
    sm._project_root = tmp_path
    (tmp_path / ".agentflow").mkdir(parents=True, exist_ok=True)
    sm.session_type = "orchestrator"
    sm._last_accumulated_tokens = 90_000
    with patch("os.write"):
        sm.on_idle_tick()
    assert not any(_CONSENT_PROMPT in inp for inp in pty.inputs)
