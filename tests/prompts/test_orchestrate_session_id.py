"""
Tests for T-286: Ensure orchestrate skill files capture $AGENTFLOW_SESSION_ID
via Bash before the Write tool call, not as a literal shell variable.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
CLAUDE_ORCHESTRATE = REPO_ROOT / "commands" / "claude" / "orchestrate.md"
GEMINI_SKILL = REPO_ROOT / "commands" / "gemini" / "skills" / "orchestrate" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# commands/claude/orchestrate.md
# ---------------------------------------------------------------------------

class TestClaudeOrchestrateSessionId:
    def test_bash_capture_step_present(self):
        """orchestrate.md must instruct Bash capture of $AGENTFLOW_SESSION_ID."""
        content = _read(CLAUDE_ORCHESTRATE)
        assert "echo $AGENTFLOW_SESSION_ID" in content, (
            "commands/claude/orchestrate.md must contain 'echo $AGENTFLOW_SESSION_ID' "
            "to instruct Bash capture before Write tool call."
        )

    def test_literal_shell_var_absent(self):
        """The JSON template must NOT contain the literal string '$AGENTFLOW_SESSION_ID'."""
        content = _read(CLAUDE_ORCHESTRATE)
        # The fix replaces `"session_id": "$AGENTFLOW_SESSION_ID"` with a captured value
        assert '"$AGENTFLOW_SESSION_ID"' not in content, (
            "commands/claude/orchestrate.md must not contain '\"$AGENTFLOW_SESSION_ID\"' "
            "as a literal JSON value — use the Bash-captured variable instead."
        )

    def test_orchestrator_fallback_not_used(self):
        """'orchestrator' must not appear as the session_id value in Round Lifecycle."""
        content = _read(CLAUDE_ORCHESTRATE)
        # Check within a reasonable window around the Round Lifecycle section
        lifecycle_idx = content.find("### Round Lifecycle")
        assert lifecycle_idx != -1, "Round Lifecycle section not found"
        section = content[lifecycle_idx: lifecycle_idx + 800]
        assert '"orchestrator"' not in section, (
            "Round Lifecycle section must not use '\"orchestrator\"' as session_id fallback."
        )


# ---------------------------------------------------------------------------
# commands/gemini/skills/orchestrate/SKILL.md
# ---------------------------------------------------------------------------

class TestGeminiOrchestrateSKILL:
    def test_bash_capture_step_present(self):
        """Gemini SKILL.md must instruct Bash capture of $AGENTFLOW_SESSION_ID."""
        content = _read(GEMINI_SKILL)
        assert "echo $AGENTFLOW_SESSION_ID" in content, (
            "commands/gemini/skills/orchestrate/SKILL.md must contain "
            "'echo $AGENTFLOW_SESSION_ID' to instruct Bash capture."
        )

    def test_session_id_field_in_schema(self):
        """Gemini SKILL.md current_round.json schema must include session_id."""
        content = _read(GEMINI_SKILL)
        lifecycle_idx = content.find("### Round Lifecycle")
        assert lifecycle_idx != -1, "Round Lifecycle section not found in Gemini SKILL.md"
        section = content[lifecycle_idx: lifecycle_idx + 800]
        assert "session_id" in section, (
            "Gemini SKILL.md Round Lifecycle section must include 'session_id' "
            "in the current_round.json schema."
        )
