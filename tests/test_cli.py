"""Smoke tests for T-001: package scaffold."""

import subprocess
import sys


def test_package_importable():
    import agentflow
    assert agentflow.__version__ == "2.0.0"


def test_all_subpackages_importable():
    import agentflow.cli
    import agentflow.oracle
    import agentflow.orchestrator
    import agentflow.worker
    import agentflow.reviewer
    import agentflow.tools
    import agentflow.telemetry
    import agentflow.config
    import agentflow.shell
    import agentflow.skills
    import agentflow.indexer


def test_cli_entry_point_importable():
    from agentflow.cli import main, build_parser
    assert callable(main)
    assert callable(build_parser)


def test_cli_help_exits_zero():
    result = subprocess.run(
        ["agentflow", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "agentflow" in result.stdout.lower()


def test_cli_module_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "agentflow.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "agentflow" in result.stdout.lower()


def test_cli_all_subcommands_present():
    from agentflow.cli import build_parser
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if hasattr(a, "_name_parser_map")
    )
    assert set(subparsers_action._name_parser_map) == {
        "init", "oracle", "orchestrate", "report", "validate", "scan", "shell"
    }


def test_orchestrate_subcommands_present():
    from agentflow.cli import build_parser
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if hasattr(a, "_name_parser_map")
    )
    orch_parser = subparsers_action._name_parser_map["orchestrate"]
    orch_sub = next(
        a for a in orch_parser._actions if hasattr(a, "_name_parser_map")
    )
    assert set(orch_sub._name_parser_map) == {"start", "status", "merge"}
