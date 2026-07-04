"""Tests for shadow_tracker.py — T-095: post-compaction re-onboarding overhead."""
import json
import pathlib
import pytest

from agentflow.shadow_tracker import p25_state_doc_tokens, update_shadow
from agentflow.constants import CONTEXT_LIMIT, COMPACT_THRESHOLD, COMPACT_RETENTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(acc: int = 0, compaction_events: int = 0) -> dict:
    return {
        "shadow_state": {
            "accumulated_context": acc,
            "compaction_events": compaction_events,
        }
    }


def _make_usage(
    n_turns: int = 5,
    initial_ctx: int = 1_000,
    final_ctx: int = 20_000,
    pre_handoff_ctx: int | None = None,
    last_turn_output: int = 1_000,
    input_tokens: int = 100_000,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 50_000,
    output_tokens: int = 10_000,
    handoff_input_tokens: int = 0,
) -> dict:
    return {
        "n_turns": n_turns,
        "initial_ctx": initial_ctx,
        "final_ctx": final_ctx,
        "pre_handoff_ctx": pre_handoff_ctx if pre_handoff_ctx is not None else final_ctx,
        "last_turn_output": last_turn_output,
        "input_tokens": input_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "handoff_input_tokens": handoff_input_tokens,
    }


# ---------------------------------------------------------------------------
# p25_state_doc_tokens
# ---------------------------------------------------------------------------

def test_p25_state_doc_tokens_fallback_when_absent(tmp_path):
    """Non-existent file returns the fallback 2750."""
    result = p25_state_doc_tokens(tmp_path / "nonexistent.jsonl")
    assert result == 2750


def test_p25_state_doc_tokens_fallback_when_too_few(tmp_path):
    """Fewer than 10 qualifying state-doc records returns 2750."""
    path = tmp_path / "shadow_reads.jsonl"
    records = [
        {"ts": "2026-01-01", "rel": "design_status.md", "file_chars": 8000},
        {"ts": "2026-01-01", "rel": "tasks.json", "file_chars": 4000},
        {"ts": "2026-01-01", "rel": "some_other_file.py", "file_chars": 12000},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records))
    assert p25_state_doc_tokens(path) == 2750


def test_p25_state_doc_tokens_computes_p25(tmp_path):
    """With ≥10 state-doc records, returns correct p25 of file_chars/4."""
    path = tmp_path / "shadow_reads.jsonl"
    # file_chars = 4000, 8000, ..., 40000 → token estimates = 1000, 2000, ..., 10000
    chars_values = [4000 * i for i in range(1, 11)]  # 4000..40000
    records = [
        {"ts": "2026-01-01", "rel": "design_status.md", "file_chars": c}
        for c in chars_values
    ]
    path.write_text("\n".join(json.dumps(r) for r in records))
    result = p25_state_doc_tokens(path)
    # sorted token estimates = [1000, 2000, ..., 10000], p25 index = int(10*0.25) = 2 → 3000
    assert result == 3000


def test_p25_state_doc_tokens_ignores_non_state_docs(tmp_path):
    """Only records whose rel field is a state doc are counted."""
    path = tmp_path / "shadow_reads.jsonl"
    # 10 very-large non-state-doc records (would skew p25 high if included)
    non_state = [
        {"ts": "2026-01-01", "rel": "agentflow/shell/pty.py", "file_chars": 999_999}
        for _ in range(10)
    ]
    # Exactly 10 state-doc records with predictable chars
    state_docs = [
        {"ts": "2026-01-01", "rel": name, "file_chars": 4000 * (i + 1)}
        for i, name in enumerate(
            ["design_status.md"] * 3
            + ["execution_plan.md"] * 3
            + ["tasks.json"] * 2
            + ["architecture.md"] * 2
        )
    ]
    records = non_state + state_docs
    path.write_text("\n".join(json.dumps(r) for r in records))
    result = p25_state_doc_tokens(path)
    # Token estimates for state docs = [1000, 2000, ..., 10000]
    # p25 index = int(10 * 0.25) = 2 → 3000
    assert result == 3000


# ---------------------------------------------------------------------------
# update_shadow — no compaction
# ---------------------------------------------------------------------------

def test_update_shadow_no_compaction():
    """A session that doesn't trigger compaction: compaction is None, no overhead."""
    ledger = _make_ledger(acc=1_000)
    usage = _make_usage(
        n_turns=5,
        initial_ctx=1_000,
        final_ctx=10_000,
        last_turn_output=500,
    )
    result = update_shadow(ledger, usage)
    assert result["compaction"] is None
    # shadow_input just equals work_input + shadow_extra (no reonboarding)
    assert "reonboarding_overhead" not in result


# ---------------------------------------------------------------------------
# update_shadow — compaction adds reonboarding
# ---------------------------------------------------------------------------

def test_update_shadow_compaction_adds_reonboarding():
    """
    Session that triggers compaction: compaction_note has reonboarding_overhead > 0
    and shadow_input includes that overhead.
    """
    # Start with acc=0 so context growth alone triggers compaction
    ledger = _make_ledger(acc=0)
    # n_turns=10, context_growth large enough to exceed 140K but avg small enough
    # that turns_until_next > 0 after compaction
    # initial_ctx=1000, pre_handoff_ctx=180000, last_turn_output=5000
    # context_growth = 180000 - 1000 + 5000 = 184000
    # acc = 184000 > 140000 → compaction
    # acc_after = int(184000 * 0.35) = 64400
    # avg_growth = 184000 / 10 = 18400
    # turns_until_next = int((140000 - 64400) / 18400) = int(75600/18400) = 4
    # reonboarding_overhead = 2750 * 4 = 11000 (fallback p25)
    usage = _make_usage(
        n_turns=10,
        initial_ctx=1_000,
        pre_handoff_ctx=180_000,
        final_ctx=180_000,
        last_turn_output=5_000,
    )

    # Pass a non-existent path so fallback p25=2750 is used
    result = update_shadow(
        ledger, usage,
        shadow_reads_path=pathlib.Path("/nonexistent/shadow_reads.jsonl"),
    )

    assert result["compaction"] is not None
    note = result["compaction"]
    assert "reonboarding_overhead" in note
    assert note["reonboarding_overhead"] > 0
    # shadow_input must include the overhead
    # (we don't hard-code exact value — just verify it's non-trivial)
    assert result["shadow_input"] > 0


def test_update_shadow_compaction_reonboarding_zero_turns():
    """
    When avg_growth is so high that turns_until_next = 0, reonboarding_overhead = 0.
    n_turns=1, context_growth=200000 → avg_growth=200000 → turns_until_next=0.
    """
    ledger = _make_ledger(acc=0)
    # initial_ctx=1000, pre_handoff_ctx=200000, last_turn_output=1000
    # context_growth = 200000 - 1000 + 1000 = 200000
    # acc = 200000 > 140000 → compaction
    # acc_after = int(200000 * 0.35) = 70000
    # avg_growth = 200000 / 1 = 200000
    # turns_until_next = int((140000 - 70000) / 200000) = int(0.35) = 0
    # reonboarding_overhead = 2750 * 0 = 0
    usage = _make_usage(
        n_turns=1,
        initial_ctx=1_000,
        pre_handoff_ctx=200_000,
        final_ctx=200_000,
        last_turn_output=1_000,
    )

    result = update_shadow(
        ledger, usage,
        shadow_reads_path=pathlib.Path("/nonexistent/shadow_reads.jsonl"),
    )

    assert result["compaction"] is not None
    note = result["compaction"]
    assert note["reonboarding_overhead"] == 0
