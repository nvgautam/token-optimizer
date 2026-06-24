"""Layered config loader: env vars > project > user > defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from agentflow.config.schema import AgentFlowConfig

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"

# Env var prefix and the section/field mapping it supports.
# Format: AGENTFLOW_<SECTION>_<FIELD>=value
# Sections: MODELS, PROMPTS, TESTING, TOKEN_BUDGET, FILE_LIMITS
_ENV_PREFIX = "AGENTFLOW_"
_SECTION_FIELDS: dict[str, list[str]] = {
    "models": ["oracle", "worker", "reviewer_code", "reviewer_security"],
    "prompts": ["oracle", "worker", "reviewer"],
    "testing": ["coverage_threshold", "require_integration_tests", "mock_io"],
    "token_budget": ["per_worker", "reviewer"],
    "file_limits": ["implementation", "tests", "prompts", "stubs"],
}
_TOP_LEVEL_FIELDS = ["parallelism", "mcps"]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base, recursing into nested dicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _coerce(value: str, target: Any) -> Any:
    """Coerce a string env var value to match the type of target."""
    if isinstance(target, bool):
        return value.lower() in ("1", "true", "yes")
    if isinstance(target, int):
        return int(value)
    return value


def _apply_env_vars(data: dict[str, Any]) -> dict[str, Any]:
    """Overlay AGENTFLOW_* env vars onto the merged dict."""
    result = _deep_merge({}, data)

    for section, fields in _SECTION_FIELDS.items():
        for field in fields:
            env_key = f"{_ENV_PREFIX}{section.upper()}_{field.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is None:
                continue
            section_data = result.setdefault(section, {})
            # Coerce to match the existing type if present
            existing = section_data.get(field)
            section_data[field] = _coerce(env_val, existing)

    for field in _TOP_LEVEL_FIELDS:
        env_key = f"{_ENV_PREFIX}{field.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None:
            continue
        existing = result.get(field)
        result[field] = _coerce(env_val, existing)

    return result


def load_config(cwd: Path) -> AgentFlowConfig:
    """Load AgentFlow config with layered precedence.

    Resolution order (highest to lowest):
      1. AGENTFLOW_* environment variables
      2. <cwd>/.agentflow/config.yaml  (project-level)
      3. ~/.agentflow/config.yaml      (user-level)
      4. Package defaults.yaml
    """
    defaults = _load_yaml(_DEFAULTS_PATH)
    user_cfg = _load_yaml(Path.home() / ".agentflow" / "config.yaml")
    project_cfg = _load_yaml(cwd / ".agentflow" / "config.yaml")

    merged = _deep_merge(defaults, user_cfg)
    merged = _deep_merge(merged, project_cfg)
    merged = _apply_env_vars(merged)

    return AgentFlowConfig.model_validate(merged)
