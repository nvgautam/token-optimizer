"""Tests for T-153: oracle_threshold_tokens config model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentflow.config.models import OrchestratorConfig


def test_oracle_threshold_tokens_default_value():
    """Test that oracle_threshold_tokens has default value of 50000."""
    config = OrchestratorConfig()
    assert config.oracle_threshold_tokens == 50000


def test_oracle_threshold_tokens_override_via_constructor():
    """Test that oracle_threshold_tokens can be overridden via constructor."""
    config = OrchestratorConfig(oracle_threshold_tokens=75000)
    assert config.oracle_threshold_tokens == 75000


def test_oracle_threshold_tokens_field_type_is_int():
    """Test that oracle_threshold_tokens field type is int."""
    config = OrchestratorConfig()
    assert isinstance(config.oracle_threshold_tokens, int)


def test_oracle_threshold_tokens_rejects_non_int():
    """Test that oracle_threshold_tokens rejects non-int values."""
    with pytest.raises(ValidationError) as exc_info:
        OrchestratorConfig(oracle_threshold_tokens="not-an-int")
    assert "oracle_threshold_tokens" in str(exc_info.value)
