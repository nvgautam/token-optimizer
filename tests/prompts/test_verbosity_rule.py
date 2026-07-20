"""Test verbosity rule: never narrate internal mechanics."""
import pathlib


def test_verbosity_md_contains_no_narrate_mechanics_rule():
    """Assert verbosity.md contains rule about not narrating internal mechanics."""
    verbosity_file = pathlib.Path(
        __file__
    ).parent.parent.parent / "commands" / "claude" / "orchestrator" / "verbosity.md"

    content = verbosity_file.read_text()

    # Check for the specific rule about internal mechanics
    assert "internal mechanics" in content.lower(), (
        "verbosity.md must contain a rule about 'internal mechanics' "
        "(idx reads, hooks, cache paths, etc.)"
    )


def test_verbosity_md_under_150_lines():
    """Assert line count of verbosity.md does not exceed 150 lines."""
    verbosity_file = pathlib.Path(
        __file__
    ).parent.parent.parent / "commands" / "claude" / "orchestrator" / "verbosity.md"

    lines = verbosity_file.read_text().split('\n')
    line_count = len(lines)

    assert line_count <= 150, (
        f"verbosity.md has {line_count} lines, but must stay under 150. "
        f"Current limit allows {150 - line_count} more lines."
    )


def test_verbosity_md_no_strategy_leakage():
    """Assert verbosity.md contains a rule about not narrating strategy."""
    verbosity_file = pathlib.Path(
        __file__
    ).parent.parent.parent / "commands" / "claude" / "orchestrator" / "verbosity.md"

    content = verbosity_file.read_text()

    assert "strategy" in content.lower(), (
        "verbosity.md must contain a rule about 'strategy' leakage "
        "(round-sizing rationale, calibration values, EWMA/cv, etc.)"
    )


def test_oracle_no_strategy_leakage():
    """Assert oracle.md's first 5 lines forbid narrating internal decision logic."""
    oracle_file = pathlib.Path(
        __file__
    ).parent.parent.parent / "commands" / "claude" / "oracle.md"

    first_five = "\n".join(oracle_file.read_text().splitlines()[:5]).lower()

    assert "strategy" in first_five or "internal decision" in first_five, (
        "oracle.md's first 5 lines must reference 'strategy' or 'internal decision' "
        "to forbid narrating startup steps, phases, file reads, or internal decision logic"
    )


def test_orchestrate_no_strategy_leakage():
    """Assert orchestrate.md's first 5 lines forbid narrating strategy."""
    orchestrate_file = pathlib.Path(
        __file__
    ).parent.parent.parent / "commands" / "claude" / "orchestrate.md"

    first_five = "\n".join(orchestrate_file.read_text().splitlines()[:5]).lower()

    assert "strategy" in first_five, (
        "orchestrate.md's first 5 lines must reference 'strategy' to forbid narrating "
        "round-sizing rationale, calibration values, EWMA/cv, task-cost estimates, "
        "disjoint owns analysis"
    )
