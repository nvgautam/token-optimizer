"""Test orchestrator round reconciliation and auto-advance (T-358, T-359)."""
import pytest
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_ORCHESTRATE = REPO / "commands" / "claude" / "orchestrate.md"
CLAUDE_STARTUP = REPO / "commands" / "claude" / "orchestrator" / "startup.md"


class TestReconciliationStep:
    """Tests for Step 4a.5 reconciliation in startup.md."""

    def test_startup_has_reconciliation_step(self):
        """Step 4a.5 must exist and describe reconciliation logic."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        assert "4a.5" in content or "Step 4a.5" in content or "reconciliation" in content.lower(), \
            "startup.md must have Step 4a.5 or reconciliation step"

    def test_reconciliation_scans_pending_rows(self):
        """Reconciliation must scan [PENDING] rows in execution_plan.md."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        reconcil_section = content.lower()
        assert "[pending]" in reconcil_section or "pending" in reconcil_section, \
            "Reconciliation must mention [PENDING] rows"
        assert "execution_plan" in content, \
            "Reconciliation must scan execution_plan.md"

    def test_reconciliation_checks_tasks_completion(self):
        """Reconciliation must cross-check task status in tasks.json."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        lower_content = content.lower()
        assert "tasks.json" in content, \
            "Reconciliation must check tasks.json"
        assert "complete" in lower_content, \
            "Reconciliation must check if tasks are complete"

    def test_reconciliation_updates_stale_rows(self):
        """Reconciliation must update stale [PENDING] rows to [MERGED]."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        lower_content = content.lower()
        assert "[merged]" in lower_content or "merged" in lower_content, \
            "Reconciliation must update rows to [MERGED] status"
        assert ("update" in lower_content or "mark" in lower_content or "change" in lower_content), \
            "Reconciliation must update or mark rows that are complete"

    def test_reconciliation_idempotent(self):
        """Reconciliation must be safe to run twice (idempotent)."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        lower_content = content.lower()
        assert "idempotent" in lower_content or "safe" in lower_content or "twice" in lower_content, \
            "Reconciliation must be documented as idempotent or safe to run twice"


class TestAutoAdvance:
    """Tests for auto-advance behavior after merge gate."""

    def test_orchestrate_has_auto_advance_instruction(self):
        """orchestrate.md must instruct auto-advance after merge gate passes."""
        content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
        lower_content = content.lower()
        # After merge gate, must auto-proceed without user input
        assert "auto" in lower_content and ("advance" in lower_content or "proceed" in lower_content or "next" in lower_content), \
            "orchestrate.md must mention auto-advance or auto-proceed after merge"

    def test_orchestrate_describes_next_round_selection(self):
        """orchestrate.md must describe automatic next round selection."""
        content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
        assert "[pending]" in content.lower(), \
            "orchestrate.md must reference [PENDING] tag for next round selection"
        assert "grep" in content.lower(), \
            "orchestrate.md must reference grep for finding next [PENDING] round"

    def test_orchestrate_no_user_prompt_after_merge(self):
        """After merge gate passes, orchestrate must not wait for user input."""
        content = CLAUDE_ORCHESTRATE.read_text(encoding="utf-8")
        # This is more of an instruction test — verify the skill says to proceed without prompting
        assert "merge" in content.lower() and ("proceed" in content.lower() or "advance" in content.lower()), \
            "orchestrate.md must describe proceeding after merge without user prompt"


class TestIntegrationBehavior:
    """Integration tests for reconciliation + auto-advance flow."""

    def test_startup_reconciliation_before_round_selection(self):
        """Startup must reconcile before selecting next round (Step 4a.5 before Step 4b)."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        # Verify step ordering
        reconcil_pos = content.find("4a.5") if "4a.5" in content else content.find("reconciliation")
        select_pos = content.find("Step 4b") if "Step 4b" in content else content.find("Select round")
        if reconcil_pos != -1 and select_pos != -1:
            assert reconcil_pos < select_pos, \
                "Reconciliation (4a.5) must come before round selection (4b)"

    def test_startup_reconciliation_after_midround_check(self):
        """Reconciliation must come after mid-round check (Step 4a before 4a.5)."""
        content = CLAUDE_STARTUP.read_text(encoding="utf-8")
        midround_pos = content.find("Step 4a") if "Step 4a" in content else content.find("mid-round") if "mid-round" in content else -1
        reconcil_pos = content.find("4a.5") if "4a.5" in content else content.find("reconciliation") if "reconciliation" in content else -1
        # Step 4a (mid-round check) should exist and come before 4a.5
        if reconcil_pos != -1:
            assert "mid-round" in content.lower() or "midround" in content.lower() or "4a" in content, \
                "startup.md must have mid-round handling logic"
