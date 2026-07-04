import json
import pathlib

from agentflow.constants import (
    INPUT_PRICE, CACHE_WRITE_PRICE, CACHE_READ_PRICE, OUTPUT_PRICE,
    CONTEXT_LIMIT, COMPACT_THRESHOLD, COMPACT_RETENTION
)

_STATE_DOC_NAMES = frozenset({
    "design_status.md",
    "execution_plan.md",
    "tasks.json",
    "architecture.md",
})

_FALLBACK_P25 = 2750
_MIN_STATE_DOC_RECORDS = 10

_DEFAULT_SHADOW_READS = pathlib.Path(".agentflow/shadow_reads.jsonl")


def p25_state_doc_tokens(shadow_reads_path: pathlib.Path) -> int:
    """Return p25 token estimate for state doc reads from shadow_reads.jsonl.
    Falls back to 2750 if file absent or fewer than 10 state-doc records."""
    try:
        text = shadow_reads_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return _FALLBACK_P25

    estimates = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        rel = record.get("rel", "")
        if not any(name in rel for name in _STATE_DOC_NAMES):
            continue
        file_chars = record.get("file_chars")
        if file_chars is None:
            continue
        estimates.append(file_chars / 4)

    if len(estimates) < _MIN_STATE_DOC_RECORDS:
        return _FALLBACK_P25

    estimates.sort()
    return int(estimates[int(len(estimates) * 0.25)])


def real_cost_from_usage(u: dict) -> float:
    return (
        u["input_tokens"]          * INPUT_PRICE +
        u["cache_creation_tokens"] * CACHE_WRITE_PRICE +
        u["cache_read_tokens"]     * CACHE_READ_PRICE +
        u["output_tokens"]         * OUTPUT_PRICE
    )


def total_real_tokens(u: dict) -> int:
    return (u["input_tokens"] + u["cache_creation_tokens"] +
            u["cache_read_tokens"] + u["output_tokens"])


def update_shadow(
    ledger: dict,
    usage: dict,
    shadow_reads_path: pathlib.Path = _DEFAULT_SHADOW_READS,
) -> dict:
    """
    Advance the shadow model after a real session.

    The shadow is a hypothetical single continuous session that never resets.
    It carries the accumulated context from all prior sessions forward, so
    every turn in this session reads that extra accumulated context.

    Corrections applied here:
    1. Handoff turns excluded from shadow base — shadow never needs session handoffs.
    2. shadow_extra priced at CACHE_READ_PRICE in reports — accumulated prior-session
       context would sit as stable cached content, not fresh uncached input.
    3. context_growth uses pre_handoff_ctx so handoff tool activity doesn't inflate acc.
    4. last_turn_output added to context_growth — the final response carries forward
       into the shadow's next turn as conversation history.
    5. Post-compaction re-onboarding overhead: after each compaction the shadow session
       must re-read state docs to recover context; this overhead is added to shadow_input.
    """
    state = ledger["shadow_state"]
    acc   = state["accumulated_context"]

    n_turns           = usage["n_turns"]
    handoff_input     = usage.get("handoff_input_tokens", 0)
    pre_handoff_ctx   = usage.get("pre_handoff_ctx", usage["final_ctx"])
    last_turn_output  = usage.get("last_turn_output", 0)

    # Shadow base = work tokens only; shadow never needs handoffs
    real_total_input = (usage["input_tokens"] + usage["cache_creation_tokens"] +
                        usage["cache_read_tokens"])
    work_input   = real_total_input - handoff_input
    shadow_extra = n_turns * acc
    shadow_input = work_input + shadow_extra
    shadow_output = usage["output_tokens"]

    # Context growth: up to pre-handoff point + last work turn's output
    # (pre_handoff_ctx prevents handoff tool activity from inflating acc;
    #  last_turn_output captures the final response that would persist in shadow)
    context_growth = pre_handoff_ctx - usage["initial_ctx"] + last_turn_output
    acc = max(0, acc + context_growth)

    compaction_note = None
    if acc > CONTEXT_LIMIT * COMPACT_THRESHOLD:
        compaction_input  = acc
        compaction_output = int(acc * COMPACT_RETENTION)
        shadow_input  += compaction_input
        shadow_output += compaction_output
        acc = compaction_output
        state["compaction_events"] += 1

        # Re-onboarding overhead: after compaction the shadow session re-reads
        # state docs on every subsequent turn until the next compaction.
        state_doc_p25 = p25_state_doc_tokens(shadow_reads_path)
        avg_growth = context_growth / max(n_turns, 1)
        avg_growth = max(avg_growth, 1)
        turns_until_next = int(
            (CONTEXT_LIMIT * COMPACT_THRESHOLD - acc) / avg_growth
        )
        reonboarding_overhead = state_doc_p25 * turns_until_next
        shadow_input += reonboarding_overhead

        compaction_note = {
            "before":                compaction_input,
            "after":                 compaction_output,
            "cost_tokens":           compaction_output,
            "reonboarding_overhead": reonboarding_overhead,
        }

    state["accumulated_context"] = acc

    return {
        "shadow_input":  shadow_input,
        "shadow_output": shadow_output,
        "shadow_extra":  shadow_extra,
        "compaction":    compaction_note,
    }
