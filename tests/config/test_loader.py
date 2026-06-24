"""Tests for T-002: config system."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agentflow.config.loader import load_config
from agentflow.config.schema import AgentFlowConfig


def _write_config(directory: Path, data: dict) -> None:
    agentflow_dir = directory / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    with (agentflow_dir / "config.yaml").open("w") as f:
        yaml.dump(data, f)


def test_returns_typed_config_instance(tmp_path):
    cfg = load_config(tmp_path)
    assert isinstance(cfg, AgentFlowConfig)


def test_defaults_used_when_no_config_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config(tmp_path)
    assert cfg.models.worker == "claude-sonnet-4-6"
    assert cfg.testing.coverage_threshold == 85
    assert cfg.parallelism == 4


def test_project_config_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    _write_config(tmp_path, {"models": {"worker": "claude-haiku-4-5"}})
    cfg = load_config(tmp_path)
    assert cfg.models.worker == "claude-haiku-4-5"
    assert cfg.models.oracle == "claude-opus-4-8"  # default preserved


def test_user_config_overrides_defaults(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_config(home, {"testing": {"coverage_threshold": 95}})
    cfg = load_config(tmp_path)
    assert cfg.testing.coverage_threshold == 95


def test_project_config_overrides_user_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_config(home, {"models": {"worker": "claude-haiku-4-5"}})
    _write_config(tmp_path, {"models": {"worker": "claude-opus-4-8"}})
    cfg = load_config(tmp_path)
    assert cfg.models.worker == "claude-opus-4-8"


def test_env_var_overrides_project_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    _write_config(tmp_path, {"models": {"worker": "claude-haiku-4-5"}})
    monkeypatch.setenv("AGENTFLOW_MODELS_WORKER", "claude-opus-4-8")
    cfg = load_config(tmp_path)
    assert cfg.models.worker == "claude-opus-4-8"


def test_env_var_sets_worker_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("AGENTFLOW_MODELS_WORKER", "foo-model")
    cfg = load_config(tmp_path)
    assert cfg.models.worker == "foo-model"


def test_env_var_int_coercion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("AGENTFLOW_TESTING_COVERAGE_THRESHOLD", "99")
    cfg = load_config(tmp_path)
    assert cfg.testing.coverage_threshold == 99


def test_env_var_bool_coercion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("AGENTFLOW_TESTING_MOCK_IO", "false")
    cfg = load_config(tmp_path)
    assert cfg.testing.mock_io is False


def test_invalid_config_raises_validation_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    _write_config(tmp_path, {"testing": {"coverage_threshold": "not-an-int"}})
    with pytest.raises(ValidationError) as exc_info:
        load_config(tmp_path)
    assert "coverage_threshold" in str(exc_info.value)


def test_missing_project_and_user_configs_use_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    cfg = load_config(tmp_path)
    assert cfg.mcps == ["github", "filesystem"]
    assert cfg.file_limits.implementation == 250


def test_partial_section_override_preserves_other_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    _write_config(tmp_path, {"models": {"oracle": "custom-oracle"}})
    cfg = load_config(tmp_path)
    assert cfg.models.oracle == "custom-oracle"
    assert cfg.models.worker == "claude-sonnet-4-6"  # default preserved
