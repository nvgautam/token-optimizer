import sys
from datetime import datetime
from agentflow.telemetry.ledger import (
    ledger_lock, load_ledger, save_ledger, active_session
)
from agentflow.usage_parser import (
    read_jsonl_usage, read_gemini_db_usage, _get_mtime
)
from agentflow.shadow_tracker import (
    update_shadow, total_real_tokens
)
from agentflow.legacy_helpers import (
    _manual_usage_entry, _print_token_breakdown, _print_summary,
    _token_detail, CLAUDE_PROJECTS_DIR,
    Path
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
        import select
        if not sys.stdin.isatty():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.0)
                if not r:
                    return default
            except Exception:
                return default
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

    try:
        from agentflow.shell.pty_signal import handoff_complete
        handoff_complete()
    except Exception as e:
        print(f"Warning: failed to signal handoff complete: {e}", file=sys.stderr)



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
