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


class AgentFlowConfig(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    token_budget: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    file_limits: FileLimitsConfig = Field(default_factory=FileLimitsConfig)
    mcps: list[str] = Field(default_factory=lambda: ["github", "filesystem"])
    parallelism: int = 4
