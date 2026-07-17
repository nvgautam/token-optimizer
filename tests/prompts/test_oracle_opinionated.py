"""T-267: oracle Phase 2 must include opinionated-expert behavior guidance."""
from pathlib import Path

ORACLE_MD = Path(__file__).parents[2] / "commands" / "claude" / "oracle.md"


def test_oracle_phase2_contains_opinionated_note():
    text = ORACLE_MD.read_text()
    assert "opinionated" in text, (
        "oracle.md Phase 2 must contain an opinionated-expert behavior note"
    )


def test_oracle_phase2_contains_recommendation_guidance():
    text = ORACLE_MD.read_text()
    assert "recommendation" in text.lower(), (
        "oracle.md Phase 2 must direct oracle to state a direct recommendation"
    )
