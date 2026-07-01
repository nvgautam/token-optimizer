import os
import json
from pathlib import Path
from agentflow.constants import (
    CONTEXT_LIMIT, CTX_WARN_THRESHOLD, COMPACT_THRESHOLD, COMPACT_RETENTION,
    INPUT_PRICE, CACHE_READ_PRICE, OUTPUT_PRICE, CLAUDE_PROJECTS_DIR
)
from agentflow.classification import classify_task, batch_decision
from agentflow.usage_parser import read_jsonl_usage, read_gemini_db_usage
from agentflow.shadow_tracker import real_cost_from_usage, total_real_tokens
from agentflow.telemetry.ledger import load_ledger, active_session

def cmd_ctx_watch(args):
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
                entry = json.loads(line)
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
            print(json.dumps({"systemMessage": msg}), flush=True)

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
        import sys
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
