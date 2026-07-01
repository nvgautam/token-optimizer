import sys
from datetime import datetime
from pathlib import Path
from agentflow.constants import (
    CONTEXT_LIMIT, CTX_WARN_THRESHOLD, COMPACT_THRESHOLD, COMPACT_RETENTION,
    INPUT_PRICE, CACHE_READ_PRICE, OUTPUT_PRICE, CLAUDE_PROJECTS_DIR
)
from agentflow.telemetry.ledger import (
    ledger_lock, load_ledger, save_ledger, active_session,
    set_ledger_override, _active_ledger_path
)
from agentflow.classification import classify_task, batch_decision
from agentflow.usage_parser import (
    read_jsonl_usage, read_gemini_db_usage, _get_mtime
)
from agentflow.shadow_tracker import (
    real_cost_from_usage, total_real_tokens, update_shadow
)

def cmd_start(args):
    print("\n── AgentFlow Session Start ──────────────────────────────")
    agent    = input("Agent backend  (claude / agy / other): ").strip() or "claude"
    if agent == "gemini":
        agent = "agy"
    task_ids = input("Task IDs being worked on (e.g. C-024, G-091): ").strip()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    with ledger_lock():
        ledger = load_ledger()
        if active_session(ledger):
            print("⚠  There is already an open session. Run `end` first.")
            sys.exit(1)
        session = {
            "session_id":       session_id,
            "agent":            agent,
            "task_ids":         task_ids,
            "start_time":       datetime.now().isoformat(),
            "context_at_start": 0,
            "status":           "open",
        }
        ledger["sessions"].append(session)
        save_ledger(ledger)

    print(f"\n✅ Session {session_id} started.")
    print(f"   Agent: {agent}   Tasks: {task_ids}")
    print("\nRun `python agentflow.py end` when the session completes.\n")


def cmd_end(args):
    with ledger_lock():
        ledger  = load_ledger()
        session = active_session(ledger)
        if not session:
            print("⚠  No open session found. Run `start` first.")
            sys.exit(1)
        session_id = session["session_id"]

    print(f"\n── AgentFlow Session End  [{session_id}] ──────────────────")

    usage = read_jsonl_usage()
    if usage:
        print(f"\n   Auto-detected: {usage['session_file']}")
        _print_token_breakdown(usage)
    else:
        print("\n⚠  Could not auto-detect JSONL. Falling back to manual entry.")
        usage = _manual_usage_entry()

    end_reason = input("\n   End reason [task_complete/handoff/manual]: ").strip() or "task_complete"
    notes      = input("   Notes (Enter to skip): ").strip()

    with ledger_lock():
        ledger  = load_ledger()
        session = active_session(ledger)
        if not session:
            print("⚠  Session was closed by another process while entering data.")
            sys.exit(1)
        shadow_event = update_shadow(ledger, usage)
        session.update({
            "end_time":       datetime.now().isoformat(),
            "input_tokens":   total_real_tokens(usage) - usage["output_tokens"],
            "output_tokens":  usage["output_tokens"],
            "token_detail":   _token_detail(usage),
            "n_turns":        usage["n_turns"],
            "final_ctx":      usage["final_ctx"],
            "end_reason":     end_reason,
            "notes":          notes,
            "shadow_event":   shadow_event,
            "status":         "closed",
        })
        save_ledger(ledger)

    _print_summary(usage, shadow_event, ledger)


def cmd_handoff(args):
    print("\n── AgentFlow Handoff ────────────────────────────────────")

    forced_agent = getattr(args, "agent", None)

    if forced_agent == "claude":
        usage = read_jsonl_usage()
        detected_agent = "claude"
    elif forced_agent in ("gemini", "agy"):
        usage = read_gemini_db_usage()
        detected_agent = "agy"
    else:
        claude_usage = read_jsonl_usage()
        gemini_usage = read_gemini_db_usage()

        claude_mtime = 0
        if claude_usage:
            cwd = Path.cwd().resolve()
            slug = str(cwd).replace("/", "-")
            claude_file = CLAUDE_PROJECTS_DIR / slug / claude_usage["session_file"]
            claude_mtime = _get_mtime(claude_file)

        gemini_mtime = 0
        if gemini_usage:
            gemini_file = Path.home() / ".gemini" / "antigravity-cli" / "conversations" / gemini_usage["session_file"]
            gemini_mtime = _get_mtime(gemini_file)

        if gemini_usage and (gemini_mtime > claude_mtime or not claude_usage):
            usage = gemini_usage
            detected_agent = "agy"
        else:
            usage = claude_usage
            detected_agent = "claude"

    if usage:
        print(f"\n   Auto-detected: {usage['session_file']} ({detected_agent})")
        _print_token_breakdown(usage)
    else:
        print("\n⚠  Could not auto-detect session logs. Falling back to manual entry.")
        usage = _manual_usage_entry()

    def _prompt(msg, default=""):
        try:
            return input(msg).strip() or default
        except EOFError:
            return default

    agent = _prompt(f"\n   Agent backend [{detected_agent}]: ", detected_agent)
    notes = _prompt("   Notes (Enter to skip): ", "")

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    with ledger_lock():
        ledger = load_ledger()
        shadow_event = update_shadow(ledger, usage)
        session = {
            "session_id":       session_id,
            "agent":            agent,
            "task_ids":         "",
            "start_time":       datetime.now().isoformat(),
            "end_time":         datetime.now().isoformat(),
            "context_at_start": usage["initial_ctx"],
            "input_tokens":     total_real_tokens(usage) - usage["output_tokens"],
            "output_tokens":    usage["output_tokens"],
            "token_detail":     _token_detail(usage),
            "n_turns":          usage["n_turns"],
            "final_ctx":        usage["final_ctx"],
            "end_reason":       "handoff",
            "notes":            notes,
            "shadow_event":     shadow_event,
            "status":           "closed",
        }
        ledger["sessions"].append(session)
        save_ledger(ledger)

    _print_summary(usage, shadow_event, ledger)


def cmd_status(args):
    ledger  = load_ledger()
    session = active_session(ledger)

    if not session:
        print("\n── No open session ──────────────────────────────────────")
        print("   Run `python agentflow.py start` to begin a session.\n")
        return

    elapsed      = datetime.now() - datetime.fromisoformat(session["start_time"])
    hours, rem   = divmod(int(elapsed.total_seconds()), 3600)
    mins         = rem // 60

    print(f"\n── Open Session [{session['session_id']}] ──────────────────────")
    print(f"   Agent:              {session['agent']}")
    print(f"   Tasks:              {session['task_ids']}")
    print(f"   Running for:        {hours}h {mins}m")
    print(f"   Shadow accumulated: {ledger['shadow_state']['accumulated_context']:,} tokens")
    print(f"   Shadow compactions: {ledger['shadow_state']['compaction_events']}")
    print()


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


def cmd_ctx_watch(args):
    import json as _json
    import os

    try:
        proj_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())).resolve()
        slug = str(proj_dir).replace("/", "-")
        proj = CLAUDE_PROJECTS_DIR / slug

        if not proj.exists():
            return

        jsonl_files = sorted(proj.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jsonl_files:
            return

        latest = jsonl_files[0]
        ctx_tokens = 0

        lines = latest.read_text(errors="replace").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = _json.loads(line)
            except Exception:
                continue
            msg = entry.get("message", {})
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if usage:
                ctx_tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
                break

        if ctx_tokens == 0:
            return

        pct = ctx_tokens / CONTEXT_LIMIT
        if pct >= CTX_WARN_THRESHOLD:
            bar_filled = int(pct * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            msg = (
                f"⚠  Context at {pct*100:.0f}%  [{bar}]  {ctx_tokens:,}/{CONTEXT_LIMIT:,} tokens"
            )
            print(_json.dumps({"systemMessage": msg}), flush=True)

    except Exception:
        pass


def cmd_classify(args):
    subjects = args.subjects
    if not subjects:
        print("\n── Task Classifier (Ctrl-C to quit) ────────────────────")
        print("   Enter task subjects to classify (empty line to quit):\n")
        while True:
            try:
                line = input("   Subject: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            kind = classify_task(line)
            icon = "⚙" if kind == "mechanical" else "🔍"
            print(f"   {icon}  {kind}\n")
    else:
        print()
        for s in subjects:
            kind = classify_task(s)
            icon = "⚙ " if kind == "mechanical" else "🔍"
            print(f"  {icon} {kind:<12}  {s}")
        print()


def cmd_batch_check(args):
    subject = " ".join(args.subjects)
    if not subject:
        print("⚠  Usage: agentflow.py batch-check \"task subject\" [--ctx N] "
              "[--files a,b] [--next-files c,d]")
        sys.exit(1)

    if args.ctx is not None:
        current_ctx = args.ctx
        ctx_source  = "provided via --ctx"
    else:
        usage = read_jsonl_usage()
        if usage:
            current_ctx = usage["final_ctx"]
            ctx_source  = f"live session ({usage['session_file']})"
        else:
            ledger  = load_ledger()
            closed  = [s for s in ledger["sessions"] if s.get("status") == "closed"]
            if closed:
                current_ctx = closed[-1].get("final_ctx", 0)
                ctx_source  = f"last recorded session ({closed[-1]['session_id']})"
            else:
                current_ctx = 0
                ctx_source  = "unknown — no sessions recorded"

    current_files = set(args.files.split(","))      if args.files      else None
    next_files    = set(args.next_files.split(",")) if args.next_files else None

    result    = batch_decision(subject, current_ctx, current_files, next_files)
    task_type = classify_task(subject)
    ctx_pct   = current_ctx / CONTEXT_LIMIT

    decision_icon = "✅ BATCH" if result["decision"] == "batch" else "🔄 FRESH SESSION"

    print(f"\n── Batch Check ──────────────────────────────────────────")
    print(f"   Task:     {subject}")
    print(f"   Type:     {task_type}")
    print(f"   Context:  {current_ctx:,} / {CONTEXT_LIMIT:,}  "
          f"({ctx_pct*100:.0f}% — threshold {int(CTX_WARN_THRESHOLD*100)}%)  [{ctx_source}]")
    if current_files:
        print(f"   Session files: {', '.join(sorted(current_files))}")
    if next_files:
        print(f"   Task files:    {', '.join(sorted(next_files))}")
    print(f"\n   {decision_icon}")
    print(f"   {result['reason']}")
    print()


def _token_detail(u: dict) -> dict:
    return {
        "uncached_input":    u["input_tokens"],
        "cache_creation":    u["cache_creation_tokens"],
        "cache_read":        u["cache_read_tokens"],
        "output":            u["output_tokens"],
        "n_turns":           u["n_turns"],
        "initial_ctx":       u["initial_ctx"],
        "final_ctx":         u["final_ctx"],
    }


def _session_usage(s: dict) -> dict:
    td = s.get("token_detail", {})
    return {
        "input_tokens":          td.get("uncached_input", s.get("input_tokens", 0)),
        "cache_creation_tokens": td.get("cache_creation", 0),
        "cache_read_tokens":     td.get("cache_read", 0),
        "output_tokens":         td.get("output", s.get("output_tokens", 0)),
        "n_turns":               td.get("n_turns", s.get("n_turns", 1)),
        "initial_ctx":           td.get("initial_ctx", s.get("context_at_start", 0)),
        "final_ctx":             td.get("final_ctx", s.get("final_ctx", 0)),
    }


def _manual_usage_entry() -> dict:
    inp = int(input("   Input tokens (uncached): ").strip() or "0")
    cw  = int(input("   Cache write tokens:      ").strip() or "0")
    cr  = int(input("   Cache read tokens:       ").strip() or "0")
    out = int(input("   Output tokens:           ").strip())
    ctx = inp + cw + cr
    return {
        "input_tokens": inp, "cache_creation_tokens": cw,
        "cache_read_tokens": cr, "output_tokens": out,
        "n_turns": 1, "initial_ctx": ctx, "final_ctx": ctx,
        "pre_handoff_ctx": ctx, "last_turn_output": out, "handoff_input_tokens": 0,
        "session_file": "manual",
    }


def _print_token_breakdown(u: dict):
    cost = real_cost_from_usage(u)
    print(f"\n   Turns: {u['n_turns']}  |  Context: {u['initial_ctx']:,} → {u['final_ctx']:,} tokens")
    print(f"   {'input (uncached)':<22} {u['input_tokens']:>10,}")
    print(f"   {'cache writes':<22} {u['cache_creation_tokens']:>10,}")
    print(f"   {'cache reads':<22} {u['cache_read_tokens']:>10,}")
    print(f"   {'output':<22} {u['output_tokens']:>10,}")
    print(f"   {'est. API cost':<22} ${cost:.4f}")


def _print_summary(u: dict, shadow_event: dict, ledger: dict):
    real_tok    = total_real_tokens(u)
    shadow_tok  = shadow_event["shadow_input"] + shadow_event["shadow_output"]
    saved_tok   = shadow_tok - real_tok
    saved_pct   = saved_tok / shadow_tok * 100 if shadow_tok > 0 else 0
    real_cost   = real_cost_from_usage(u)
    shadow_base_input = shadow_event["shadow_input"] - shadow_event["shadow_extra"]
    shadow_cost = (shadow_base_input                  * INPUT_PRICE +
                   shadow_event["shadow_extra"]        * CACHE_READ_PRICE +
                   shadow_event["shadow_output"]       * OUTPUT_PRICE)

    acc = ledger["shadow_state"]["accumulated_context"]

    print(f"\n── Session Summary ──────────────────────────────────────")
    print(f"   Real tokens:    {real_tok:>12,}  (${real_cost:.4f} API equiv.)")
    print(f"   Shadow tokens:  {shadow_tok:>12,}  (${shadow_cost:.4f} API equiv.)")
    if shadow_event["shadow_extra"] > 0:
        n   = u["n_turns"]
        acc_before = shadow_event["shadow_extra"] // n if n else 0
        print(f"   Shadow extra:   {shadow_event['shadow_extra']:>12,}  "
              f"({n} turns × {acc_before:,} acc. context)")
    print(f"   Saved:          {saved_tok:>12,}  [{saved_pct:.0f}% token reduction]")

    if shadow_event.get("compaction"):
        c = shadow_event["compaction"]
        print(f"\n   Shadow compaction fired:")
        print(f"     Context {c['before']:,} → {c['after']:,} tokens")

    print(f"\n   Shadow accumulated context: {acc:,} tokens")
    print("\nRun `python agentflow.py report` for cumulative savings.\n")
