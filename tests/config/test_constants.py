"""Tests for AgentFlow central constants."""

from __future__ import annotations

from agentflow.config import constants


def test_constants_defined():
    """Verify that essential constants exist and hold the correct values."""
    assert constants.UTF8 == "utf-8"
    assert constants.ENV_SESSION_ID == "AGENTFLOW_SESSION_ID"
    assert constants.DIR_AGENTFLOW == ".agentflow"
    assert constants.FILE_SESSION_STATE == "session_state.json"
    assert constants.FILE_CURRENT_ROUND == "current_round.json"
    assert constants.SESSION_TYPE_ORCHESTRATOR == "orchestrator"
    assert constants.CFG_HANDOFF_PRIMARY_TOKENS == "handoff_primary_tokens"
