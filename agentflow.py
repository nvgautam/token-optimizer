#!/usr/bin/env python3
"""
AgentFlow Session Logger
Tracks real token usage vs shadow (single-session) token usage
to measure savings from session cycling.

Usage:
  python agentflow.py start   -- begin a new session
  python agentflow.py end     -- end current session, record tokens
  python agentflow.py handoff -- record session auto-reading from JSONL (no prior start needed)
  python agentflow.py report  -- show savings report
  python agentflow.py status  -- show current session status
"""

import fcntl
import json
import os
import sys
import argparse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

LEDGER_FILE       = Path(__file__).parent / "agentflow_ledger.json"
CONTEXT_LIMIT     = 200_000          # Claude's context window
COMPACT_THRESHOLD = 0.70             # Shadow compacts at 70% of context window
CTX_WARN_THRESHOLD = 0.40            # Stop hook warns to handoff at this context %
COMPACT_RETENTION = 0.35             # Compaction keeps ~35% of context

# Sonnet 4.6 pricing per token
INPUT_PRICE       = 3.00  / 1_000_000
CACHE_WRITE_PRICE = 3.75  / 1_000_000
CACHE_READ_PRICE  = 0.30  / 1_000_000
OUTPUT_PRICE      = 15.00 / 1_000_000

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# ── Task type classifier ──────────────────────────────────────────────────────
# Conservative rule: any exploratory signal wins; ambiguous → exploratory.
# "implement" is exploratory because scope is rarely bounded in practice.

_MECHANICAL = {
    "fix", "add", "remove", "delete", "rename", "update", "change",
    "extract", "move", "replace", "export", "import", "wire", "hook",
    "bump", "pin", "revert", "restore", "patch", "correct", "adjust",
    "set", "register", "expose", "skip", "drop", "trim", "guard",
    "convert", "mark", "tag", "log", "emit", "send", "wrap", "expand",
    "collapse", "hide", "show", "enable", "disable", "sort", "filter",
    "format", "parse", "validate", "sanitize", "index", "dedupe",
}

_EXPLORATORY = {
    "investigate", "debug", "design", "refactor", "implement", "review",
    "understand", "audit", "analyze", "analyse", "explore", "rethink",
    "plan", "migrate", "port", "rebuild", "rewrite", "overhaul",
    "architect", "research", "evaluate", "assess", "profile", "spike",
    "prototype",
}


def classify_task(subject: str) -> str:
    """
    Return 'mechanical' or 'exploratory' for a task subject line.

    Mechanical tasks have short, predictable conversation histories and are
    good candidates for session batching. Exploratory tasks generate long
    histories and should always start a fresh session.
    """
    words = set(subject.lower().replace("-", " ").split())
    has_exploratory = bool(words & _EXPLORATORY)
    has_mechanical  = bool(words & _MECHANICAL)

    if has_exploratory:
        return "exploratory"
    if has_mechanical:
        return "mechanical"
    return "exploratory"  # default: conservative


def batch_decision(next_subject: str, current_ctx: int,
                   current_files: set | None = None,
                   next_files: set | None = None) -> dict:
    """
    Decide whether the next task should run in the current session or start fresh.

    Rules applied in order (first match wins):
      1. Exploratory task        → always fresh
      2. Context over threshold  → fresh (not enough headroom)
      3. No file overlap         → fresh (unrelated work)
      4. All checks pass         → batch

    Returns dict with keys:
      decision  : 'batch' | 'fresh'
      reason    : human-readable explanation
    """
    task_type = classify_task(next_subject)
    if task_type == "exploratory":
        return {
            "decision": "fresh",
            "reason":   f"task classified as exploratory — always start fresh",
        }

    ctx_pct = current_ctx / CONTEXT_LIMIT
    if ctx_pct >= CTX_WARN_THRESHOLD:
        return {
            "decision": "fresh",
            "reason":   (f"context at {ctx_pct*100:.0f}% ({current_ctx:,} tokens) "
                         f"exceeds {int(CTX_WARN_THRESHOLD*100)}% batch threshold"),
        }

    if current_files is not None and next_files is not None:
        overlap = current_files & next_files
        if not overlap:
            return {
                "decision": "fresh",
                "reason":   "no file overlap between current session and next task",
            }
        overlap_note = f", shared: {', '.join(sorted(overlap))}"
    else:
        overlap_note = " (file overlap not checked)"

    return {
        "decision": "batch",
        "reason":   (f"mechanical task, context at {ctx_pct*100:.0f}% "
                     f"({current_ctx:,} tokens){overlap_note}"),
    }

# ── Ledger helpers ────────────────────────────────────────────────────────────

LOCK_FILE = Path(str(LEDGER_FILE) + ".lock")

@contextmanager
def ledger_lock():
    with open(LOCK_FILE, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

def load_ledger() -> dict:
    if not Path(LEDGER_FILE).exists():
        return {"sessions": [], "shadow_state": {"accumulated_context": 0, "compaction_events": 0}}
    with open(LEDGER_FILE) as f:
        return json.load(f)

def save_ledger(ledger: dict):
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)

def active_session(ledger: dict) -> dict | None:
    for s in reversed(ledger["sessions"]):
        if s.get("status") == "open":
            return s
    return None

# ── JSONL reader ──────────────────────────────────────────────────────────────

def read_jsonl_usage() -> dict | None:
    """
    Find the most recently modified JSONL session file for the current project
    and sum all unique per-turn usage records.

    Returns dict with:
      session_file, n_turns, input_tokens, cache_creation_tokens,
      cache_read_tokens, output_tokens, initial_ctx, final_ctx
    or None if no file found.
    """
    cwd   = Path.cwd().resolve()
    slug  = str(cwd).replace("/", "-")
    project_dir = CLAUDE_PROJECTS_DIR / slug

    if not project_dir.exists():
        return None

    jsonl_files = list(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)

    seen              = set()
    turns             = []
    handoff_turn_idx  = None   # index of the first turn that contains the handoff invocation

    with open(latest) as f:
        for raw_line in f:
            # Fast string check before JSON parse — tracks the LAST handoff turn.
            # Always overwrite so repeated /handoff calls in one session don't
            # misclassify early work turns as handoff overhead.
            if "agentflow.py handoff" in raw_line:
                handoff_turn_idx = len(turns)  # will be this turn's index once appended
            try:
                obj = json.loads(raw_line)
            except Exception:
                continue
            usage = obj.get("message", {}).get("usage") or obj.get("usage")
            if not usage:
                continue
            key = (
                usage.get("input_tokens", 0),
                usage.get("cache_creation_input_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
                usage.get("output_tokens", 0),
            )
            if key in seen:
                continue
            seen.add(key)
            turns.append({
                "inp": usage.get("input_tokens", 0),
                "cw":  usage.get("cache_creation_input_tokens", 0),
                "cr":  usage.get("cache_read_input_tokens", 0),
                "out": usage.get("output_tokens", 0),
            })

    if not turns:
        return None

    def ctx(t): return t["inp"] + t["cw"] + t["cr"]

    # Split turns into work vs handoff overhead.
    # handoff_turn_idx > 0 means we found the handoff turn and there's work before it.
    if handoff_turn_idx is not None and handoff_turn_idx > 0:
        work_turns    = turns[:handoff_turn_idx]
        handoff_turns = turns[handoff_turn_idx:]
    else:
        work_turns    = turns
        handoff_turns = []

    pre_handoff_ctx    = ctx(work_turns[-1])
    last_turn_output   = work_turns[-1]["out"]
    handoff_input_toks = sum(ctx(t) for t in handoff_turns)

    return {
        "session_file":           latest.name,
        "n_turns":                len(turns),
        "input_tokens":           sum(t["inp"] for t in turns),
        "cache_creation_tokens":  sum(t["cw"]  for t in turns),
        "cache_read_tokens":      sum(t["cr"]  for t in turns),
        "output_tokens":          sum(t["out"] for t in turns),
        "initial_ctx":            ctx(turns[0]),
        "final_ctx":              ctx(turns[-1]),
        "pre_handoff_ctx":        pre_handoff_ctx,
        "last_turn_output":       last_turn_output,
        "handoff_input_tokens":   handoff_input_toks,
    }

def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0

def read_gemini_db_usage() -> dict | None:
    """
    Find the most recently modified SQLite session DB for Gemini/Antigravity
    and extract prompt and candidates token counts from the gen_metadata table.

    Returns dict with:
      session_file, n_turns, input_tokens, cache_creation_tokens,
      cache_read_tokens, output_tokens, initial_ctx, final_ctx
    or None if no file found.
    """
    import sqlite3
    gemini_dir = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
    if not gemini_dir.exists():
        return None

    db_files = list(gemini_dir.glob("*.db"))
    if not db_files:
        return None

    latest = max(db_files, key=lambda f: f.stat().st_mtime)

    try:
        conn = sqlite3.connect(latest)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata'")
        if not cursor.fetchone():
            conn.close()
            return None
        
        cursor.execute("SELECT data FROM gen_metadata ORDER BY idx ASC")
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return None

    if not rows:
        return None

    def parse_varint(data, pos):
        val, shift = 0, 0
        while True:
            b = data[pos]
            val |= (b & 0x7f) << shift
            pos += 1
            if not (b & 0x80): break
            shift += 7
        return val, pos

    def parse_proto(data, pos=0, end=None):
        if end is None: end = len(data)
        res = {}
        while pos < end:
            try:
                key, pos = parse_varint(data, pos)
            except IndexError:
                break
            wt, fn = key & 7, key >> 3
            if wt == 0:
                val, pos = parse_varint(data, pos)
                res[fn] = val
            elif wt == 2:
                length, pos = parse_varint(data, pos)
                val = data[pos:pos+length]
                pos += length
                try: res[fn] = parse_proto(val)
                except Exception: res[fn] = val
            elif wt == 1: pos += 8
            elif wt == 5: pos += 4
        return res

    turns = []
    for (blob,) in rows:
        try:
            d = parse_proto(blob)
            f4 = d.get(1, {}).get(4, {})
            inp = f4.get(2)
            out = f4.get(3)
            if inp is not None and out is not None:
                turns.append({
                    "inp":    inp,          # 1.4.2 — uncached prompt
                    "cached": f4.get(5, 0), # 1.4.5 — cached/thinking tokens
                    "cw":     0,
                    "cr":     0,
                    "out":    out,          # 1.4.3
                })
        except Exception:
            continue

    if not turns:
        return None

    def ctx(t): return t["inp"] + t["cached"]

    return {
        "session_file":           latest.name,
        "n_turns":                len(turns),
        "input_tokens":           sum(t["inp"]    for t in turns),
        "cache_creation_tokens":  0,
        "cache_read_tokens":      sum(t["cached"] for t in turns),
        "output_tokens":          sum(t["out"]    for t in turns),
        "initial_ctx":            ctx(turns[0]),
        "final_ctx":              ctx(turns[-1]),
        # Gemini has no handoff detection yet; defaults keep update_shadow correct
        "pre_handoff_ctx":        ctx(turns[-1]),
        "last_turn_output":       turns[-1]["out"],
        "handoff_input_tokens":   0,
    }

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

# ── Shadow counter ────────────────────────────────────────────────────────────

def update_shadow(ledger: dict, usage: dict) -> dict:
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
        compaction_note   = {
            "before":      compaction_input,
            "after":       compaction_output,
            "cost_tokens": compaction_output,
        }
        shadow_input  += compaction_input
        shadow_output += compaction_output
        acc = compaction_output
        state["compaction_events"] += 1

    state["accumulated_context"] = acc

    return {
        "shadow_input":  shadow_input,
        "shadow_output": shadow_output,
        "shadow_extra":  shadow_extra,
        "compaction":    compaction_note,
    }

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args):
    print("\n── AgentFlow Session Start ──────────────────────────────")
    agent    = input("Agent backend  (claude / gemini / other): ").strip() or "claude"
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
    # Collect user input and token data before acquiring the lock
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
    elif forced_agent == "gemini":
        usage = read_gemini_db_usage()
        detected_agent = "gemini"
    else:
        # Auto-detect: pick whichever session file was modified most recently
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
            detected_agent = "gemini"
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
    sessions = [s for s in ledger["sessions"]
                if s.get("status") == "closed"
                and (agent_filter is None or s.get("agent") == agent_filter)]

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
  tokens than a continuous non-cycling session would have.

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    """Reconstruct a usage dict from a stored session record."""
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
    # shadow_extra would be cached content (stable prior-session context),
    # so price it at CACHE_READ_PRICE; remaining work input at INPUT_PRICE.
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


def cmd_ctx_watch(args):
    """
    Stop hook: reads the latest turn's token usage from the current session JSONL
    and prints a handoff warning if context exceeds CTX_WARN_THRESHOLD.
    Exits silently with code 0 in all cases so it never blocks Claude.
    """
    import json as _json

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

        # Walk lines in reverse to find the last assistant message with usage
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
        pass  # Never block Claude on a watch failure


def cmd_classify(args):
    subjects = args.subjects
    if not subjects:
        # interactive mode
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

    # Resolve current context: explicit flag > live JSONL > last ledger entry
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


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AgentFlow — session token logger and savings tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  start              Begin a new agent session
  end                End the current session (auto-reads JSONL)
  handoff            Record a session without a prior start
  handoff --agent claude   Force Claude JSONL reader
  handoff --agent gemini   Force Gemini DB reader
  status             Show current open session
  report             Show cumulative savings report
  report --agent claude    Report for Claude sessions only
  report --agent gemini    Report for Gemini sessions only
  classify [subject ...]   Classify tasks as mechanical or exploratory
  batch-check "subject"    Should next task batch into current session or start fresh?
    --ctx N                Override current context token count
    --files a,b            Comma-separated files touched in current session
    --next-files c,d       Comma-separated files the next task will touch
  ctx-watch          Stop hook: warn if context exceeds threshold (run automatically)
        """
    )
    parser.add_argument("command",
                        choices=["start", "end", "handoff", "status", "report",
                                 "classify", "batch-check", "ctx-watch"])
    parser.add_argument("--agent", choices=["claude", "gemini"], default=None,
                        help="Force agent backend (handoff) or filter by agent (report)")
    parser.add_argument("subjects", nargs="*",
                        help="Task subjects (classify / batch-check commands)")
    parser.add_argument("--ctx", type=int, default=None,
                        help="Current context token count (batch-check)")
    parser.add_argument("--files", default=None,
                        help="Comma-separated files in current session (batch-check)")
    parser.add_argument("--next-files", default=None,
                        help="Comma-separated files next task will touch (batch-check)")
    args = parser.parse_args()

    dispatch = {
        "start":       cmd_start,
        "end":         cmd_end,
        "handoff":     cmd_handoff,
        "status":      cmd_status,
        "report":      cmd_report,
        "classify":    cmd_classify,
        "batch-check": cmd_batch_check,
        "ctx-watch":   cmd_ctx_watch,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
