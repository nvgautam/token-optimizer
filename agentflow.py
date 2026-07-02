#!/usr/bin/env python3
"""
AgentFlow Session Logger
Tracks real token usage vs shadow (single-session) token usage
to measure savings from session cycling.

Usage:
  python agentflow.py start   -- begin a new session
  python agentflow.py end     -- end current session, record tokens
  python agentflow.py handoff -- record session auto-reading from JSONL (no prior start needed)
  python agentflow.py status  -- show current session status
"""

import argparse
from agentflow.telemetry.ledger import (
    _ledger_override, set_ledger_override, load_ledger, save_ledger, active_session
)
from agentflow.legacy_commands import (
    cmd_start, cmd_end, cmd_handoff, cmd_status
)
from agentflow.legacy_helpers import (
    cmd_classify, cmd_batch_check, cmd_ctx_watch,
    _print_token_breakdown, _print_summary, _manual_usage_entry
)
from agentflow.usage_parser import (
    read_jsonl_usage, read_gemini_db_usage, _get_mtime
)
from agentflow.shadow_tracker import (
    real_cost_from_usage, total_real_tokens, update_shadow
)

def cmd_report(args):
    """Exposed for backward compatibility and testing."""
    from agentflow.legacy_report import cmd_report as legacy_cmd_report
    return legacy_cmd_report(args)

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
  handoff --agent agy      Force agy/Gemini DB reader
  status             Show current open session
  classify [subject ...]   Classify tasks as mechanical or exploratory
  batch-check "subject"    Should next task batch into current session or start fresh?
    --ctx N                Override current context token count
    --files a,b            Comma-separated files touched in current session
    --next-files c,d       Comma-separated files next task will touch
  ctx-watch          Stop hook: warn if context exceeds threshold (run automatically)

Global flags:
  --ledger PATH      Use a project-specific ledger instead of the default.
        """
    )
    parser.add_argument("command",
                        choices=["start", "end", "handoff", "status",
                                 "classify", "batch-check", "ctx-watch"])
    parser.add_argument("--agent", choices=["claude", "gemini", "agy"], default=None,
                        help="Force agent backend (handoff) or filter by agent (report)")
    parser.add_argument("subjects", nargs="*",
                        help="Task subjects (classify / batch-check commands)")
    parser.add_argument("--ctx", type=int, default=None,
                        help="Current context token count (batch-check)")
    parser.add_argument("--files", default=None,
                        help="Comma-separated files in current session (batch-check)")
    parser.add_argument("--next-files", default=None,
                        help="Comma-separated files next task will touch (batch-check)")
    parser.add_argument("--ledger", default=None,
                        help="Path to a project-specific ledger file (default: agentflow_ledger.json next to this script)")
    args = parser.parse_args()

    if args.ledger:
        set_ledger_override(args.ledger)

    dispatch = {
        "start":       cmd_start,
        "end":         cmd_end,
        "handoff":     cmd_handoff,
        "status":      cmd_status,
        "classify":    cmd_classify,
        "batch-check": cmd_batch_check,
        "ctx-watch":   cmd_ctx_watch,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
