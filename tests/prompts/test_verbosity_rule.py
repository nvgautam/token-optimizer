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
