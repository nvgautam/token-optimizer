from datetime import datetime
from agentflow.constants import (
    CONTEXT_LIMIT, COMPACT_THRESHOLD, COMPACT_RETENTION,
    INPUT_PRICE, CACHE_READ_PRICE, OUTPUT_PRICE
)
from agentflow.telemetry.ledger import load_ledger
from agentflow.shadow_tracker import real_cost_from_usage, total_real_tokens
from agentflow.legacy_helpers import _session_usage

def cmd_report(args):
    ledger   = load_ledger()
    agent_filter = getattr(args, "agent", None)
    if agent_filter == "gemini":
        agent_filter = "agy"

    if agent_filter == "agy":
        match_agents = {"gemini", "agy"}
    elif agent_filter is not None:
        match_agents = {agent_filter}
    else:
        match_agents = None

    sessions = [s for s in ledger["sessions"]
                if s.get("status") == "closed"
                and (match_agents is None or s.get("agent") in match_agents)]

    if not sessions:
        suffix = f" for agent '{agent_filter}'" if agent_filter else ""
        print(f"\n── No completed sessions{suffix} yet ─────────────────────")
        print("   Run `handoff` to record a session.\n")
        return

    total_real   = sum(total_real_tokens(_session_usage(s)) for s in sessions)
    total_shadow = sum(s["shadow_event"]["shadow_input"] + s["shadow_event"]["shadow_output"]
                       for s in sessions)
    total_saved  = total_shadow - total_real
    saved_pct    = total_saved / total_shadow * 100 if total_shadow > 0 else 0

    total_real_cost   = sum(real_cost_from_usage(_session_usage(s)) for s in sessions)
    total_shadow_cost = sum(
        ((s["shadow_event"]["shadow_input"] - s["shadow_event"]["shadow_extra"]) * INPUT_PRICE +
          s["shadow_event"]["shadow_extra"]                                       * CACHE_READ_PRICE +
          s["shadow_event"]["shadow_output"]                                      * OUTPUT_PRICE)
        for s in sessions
    )

    compaction_events = ledger["shadow_state"]["compaction_events"]

    agent_label = f" — {agent_filter}" if agent_filter else " — all agents"
    print(f"\n{'═'*62}")
    print(f"  AgentFlow Savings Report{agent_label}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*62}")

    print(f"\n{'─'*62}")
    print(f"  {'Session':<22} {'Turns':>5} {'Real ctx':>10} {'Shadow':>10} {'Saved%':>7}")
    print(f"{'─'*62}")

    for s in sessions:
        u        = _session_usage(s)
        r_tok    = total_real_tokens(u)
        sh_tok   = s["shadow_event"]["shadow_input"] + s["shadow_event"]["shadow_output"]
        sv_pct   = (sh_tok - r_tok) / sh_tok * 100 if sh_tok > 0 else 0
        label    = s["session_id"][:22]
        turns    = s.get("n_turns", "?")
        print(f"  {label:<22} {str(turns):>5} {r_tok:>10,} {sh_tok:>10,} {sv_pct:>6.0f}%")

    print(f"{'─'*62}")
    print(f"  {'TOTAL':<22} {'':>5} {total_real:>10,} {total_shadow:>10,} {saved_pct:>6.0f}%")
    print(f"{'═'*62}")

    print(f"""
  Token savings (subscription: % = quota efficiency gain)
    Real tokens:    {total_real:>14,}   (${total_real_cost:.2f} API equiv.)
    Shadow tokens:  {total_shadow:>14,}   (${total_shadow_cost:.2f} API equiv.)
    ──────────────────────────────────────────────
    Saved:          {total_saved:>14,}   [{saved_pct:.0f}% reduction]

  What {saved_pct:.0f}% means: for the same output, you consumed {saved_pct:.0f}% fewer
  tokens than a typical session would have.

  Session stats
    Sessions recorded:    {len(sessions)}
    Shadow compactions:   {compaction_events}

  Shadow model assumptions
    Context limit:        {CONTEXT_LIMIT:,} tokens
    Compaction threshold: {int(COMPACT_THRESHOLD*100)}%  (shadow compacts when context exceeds this)
    Compaction retention: {int(COMPACT_RETENTION*100)}%  (keeps this fraction after compaction)
    Work input priced at:   ${INPUT_PRICE      * 1_000_000:.2f}/MTok
    Acc. context priced at: ${CACHE_READ_PRICE * 1_000_000:.2f}/MTok (prior-session ctx = cached)
""")
