"""Tests for T-009: contract and test skeleton generator."""

import importlib
from pathlib import Path

import pytest

from agentflow.oracle.contract_generator import (
    GeneratedArtifacts,
    generate_contracts,
    generate_mock_fixtures,
    generate_stub,
    generate_test_skeleton,
)

SAMPLE_TASK = {
    "task_id": "T-TEST",
    "title": "Sample module",
    "description": "Expose compute(x, y) and validate(data) functions.",
    "owns": ["agentflow/sample/module.py", "tests/sample/test_module.py"],
    "reads": ["agentflow/tools/git.py"],
    "test_requirements": {
        "unit": [
            "compute returns correct sum",
            "validate raises on invalid input",
            "empty input returns zero",
        ],
        "integration": [],
        "coverage_threshold": 85,
    },
    "security_constraints": [],
}


def test_generate_stub_creates_py_file(tmp_path):
    path = generate_stub("agentflow/sample/module.py", tmp_path, SAMPLE_TASK)
    assert path.exists()
    assert path.suffix == ".py"


def test_stub_contains_not_implemented(tmp_path):
    path = generate_stub("agentflow/sample/module.py", tmp_path, SAMPLE_TASK)
    assert "NotImplementedError" in path.read_text()


def test_stub_is_valid_python(tmp_path):
    path = generate_stub("agentflow/sample/module.py", tmp_path, SAMPLE_TASK)
    source = path.read_text()
    compile(source, str(path), "exec")  # raises SyntaxError if invalid


def test_generate_test_skeleton_creates_file(tmp_path):
    path = generate_test_skeleton(SAMPLE_TASK, tmp_path)
    assert path is not None
    assert path.exists()


def test_skeleton_has_one_method_per_scenario(tmp_path):
    path = generate_test_skeleton(SAMPLE_TASK, tmp_path)
    source = path.read_text()
    for scenario in SAMPLE_TASK["test_requirements"]["unit"]:
        # each scenario produces a test_ method
        assert "def test_" in source
    # count test methods
    method_count = source.count("def test_")
    assert method_count == len(SAMPLE_TASK["test_requirements"]["unit"])


def test_skeleton_method_names_are_snake_case(tmp_path):
    path = generate_test_skeleton(SAMPLE_TASK, tmp_path)
    source = path.read_text()
    # method names should not contain spaces
    import re
    methods = re.findall(r'def (test_\w+)', source)
    for m in methods:
        assert ' ' not in m
        assert m == m.lower()


def test_skeleton_is_valid_python(tmp_path):
    path = generate_test_skeleton(SAMPLE_TASK, tmp_path)
    source = path.read_text()
    compile(source, str(path), "exec")


def test_mock_fixtures_generated_for_tools_reads(tmp_path):
    path = generate_mock_fixtures(SAMPLE_TASK, tmp_path)
    assert path is not None
    assert path.exists()
    assert "fixture" in path.read_text() or "pytest.fixture" in path.read_text()


def test_generate_contracts_is_idempotent(tmp_path):
    result1 = generate_contracts(SAMPLE_TASK, tmp_path)
    # capture mtimes
    mtimes1 = {p: p.stat().st_mtime for p in result1.stubs + result1.skeletons + result1.mocks}

    result2 = generate_contracts(SAMPLE_TASK, tmp_path)
    for p, mtime in mtimes1.items():
        assert p.stat().st_mtime == mtime, f"{p} was overwritten on second call"


def test_non_py_owned_file_creates_empty_file(tmp_path):
    task = {**SAMPLE_TASK, "owns": ["agentflow/config/something.yaml"]}
    path = generate_stub("agentflow/config/something.yaml", tmp_path, task)
    assert path.exists()
    assert path.suffix == ".yaml"


def test_no_unit_scenarios_returns_none_skeleton(tmp_path):
    task = {**SAMPLE_TASK, "test_requirements": {"unit": [], "integration": []}}
    result = generate_test_skeleton(task, tmp_path)
    assert result is None


def test_no_tools_reads_returns_none_mock(tmp_path):
    task = {**SAMPLE_TASK, "reads": ["agentflow/config/loader.py"]}
    result = generate_mock_fixtures(task, tmp_path)
    assert result is None


def test_generate_contracts_returns_artifacts_dataclass(tmp_path):
    result = generate_contracts(SAMPLE_TASK, tmp_path)
    assert isinstance(result, GeneratedArtifacts)
    assert len(result.stubs) >= 1
    assert len(result.skeletons) >= 1
