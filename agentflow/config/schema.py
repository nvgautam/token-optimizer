"""Pydantic schema for AgentFlow configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelsConfig(BaseModel):
    oracle: str = "claude-opus-4-8"
    worker: str = "claude-sonnet-4-6"
    reviewer_code: str = "claude-sonnet-4-6"
    reviewer_security: str = "claude-opus-4-8"


class PromptsConfig(BaseModel):
    oracle: str = "v1"
    worker: str = "v1"
    reviewer: str = "v1"


class TestingConfig(BaseModel):
    coverage_threshold: int = 85
    require_integration_tests: bool = True
    mock_io: bool = True


class TokenBudgetConfig(BaseModel):
    per_worker: int = 50000
    reviewer: int = 20000


class FileLimitsConfig(BaseModel):
    implementation: int = 250
    tests: int = 350
    prompts: int = 150
    stubs: int = 100


class HeadroomConfig(BaseModel):
    enabled: bool = True


class AgentFlowConfig(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    token_budget: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    file_limits: FileLimitsConfig = Field(default_factory=FileLimitsConfig)
    headroom: HeadroomConfig = Field(default_factory=HeadroomConfig)
    mcps: list[str] = Field(default_factory=lambda: ["github", "filesystem"])
    parallelism: int = 4


# T-086: resolution order for whether the PTY shell should wrap the AI CLI
# with `headroom wrap`. Extracted as a pure function (no IO) so cli.py stays
# under its 250-line cap and the precedence logic is unit-testable in
# isolation from PTY/subprocess mocking.
_HEADROOM_INACTIVE_REASONS: dict[str, str] = {
    "not installed": "headroom not installed",
    "env-override": "disabled via AGENTFLOW_ENABLE_HEADROOM override",
    "config-disabled": "disabled via config (headroom.enabled: false)",
}


def resolve_headroom_status(
    config_enabled: bool, env_value: str | None, installed: bool
) -> tuple[bool, str]:
    """Resolve whether headroom wrap should be active for this shell session.

    Precedence: binary availability > AGENTFLOW_ENABLE_HEADROOM env override
    > headroom.enabled config value.

    Returns:
        (active, reason). `reason` is "" when active is True; otherwise one
        of "not installed", "env-override", "config-disabled".
    """
    if not installed:
        return False, "not installed"

    if env_value is not None:
        env_enabled = env_value.strip().lower() in ("1", "true", "yes")
        return (True, "") if env_enabled else (False, "env-override")

    if not config_enabled:
        return False, "config-disabled"

    return True, ""


def format_headroom_banner(active: bool, reason: str) -> str:
    """Format the PTY startup banner line describing headroom wrap status."""
    if active:
        return "[agentflow] headroom wrap: active"
    why = _HEADROOM_INACTIVE_REASONS.get(reason, reason)
    return f"[agentflow] headroom wrap: inactive ({why})"
