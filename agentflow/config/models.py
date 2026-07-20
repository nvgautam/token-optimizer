"""Pydantic v2 models for AgentFlow configuration."""

from __future__ import annotations

from pydantic import BaseModel


class OrchestratorConfig(BaseModel):
    """Configuration for orchestrator and oracle thresholds."""

    oracle_threshold_tokens: int = 50000
    encrypt_skills: bool = False
