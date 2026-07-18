"""agentflow.cli_db — CLI-as-interface layer for state mutations (T-259 spike stub)."""
from __future__ import annotations
import argparse
import sys


def cmd_round_start(args: argparse.Namespace) -> int:
    print(f"round start: round_id={args.round_id!r} task_ids={args.task_ids} sid={args.sid!r}")
    print("not implemented"); return 1


def cmd_round_status(args: argparse.Namespace) -> int:
    print("round status: not implemented"); return 1


def cmd_task_start(args: argparse.Namespace) -> int:
    print(f"task start: task_id={args.task_id!r} sid={args.sid!r}")
    print("not implemented"); return 1


def cmd_task_done(args: argparse.Namespace) -> int:
    print(f"task done: task_id={args.task_id!r} sid={args.sid!r}")
    print("not implemented"); return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentflow-db",
        description="AgentFlow state mutation CLI (CLI-as-interface layer)",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    round_p = sub.add_parser("round", help="Manage round state")
    round_sub = round_p.add_subparsers(dest="round_command", metavar="subcommand")
    round_sub.required = True

    start_p = round_sub.add_parser(
        "start", help="Atomically write current_round.json + tasks_in_flight.json"
    )
    start_p.add_argument("--task-ids", nargs="+", required=True, metavar="TASK_ID",
                         help="Task IDs entering this round")
    start_p.add_argument("--round-id", default=None, metavar="ROUND_ID",
                         help="Round label (defaults to timestamp slug)")
    start_p.add_argument("--sid", default=None, metavar="SESSION_ID",
                         help="Session ID (falls back to $AGENTFLOW_SESSION_ID)")
    round_sub.add_parser("status", help="Print current round state")

    task_p = sub.add_parser("task", help="Manage task in-flight state")
    task_sub = task_p.add_subparsers(dest="task_command", metavar="subcommand")
    task_sub.required = True

    for verb, hlp in [
        ("start", "Add task to tasks_in_flight.json"),
        ("done",  "Remove task; write task_complete.json if drained"),
    ]:
        vp = task_sub.add_parser(verb, help=hlp)
        vp.add_argument("task_id", metavar="TASK_ID")
        vp.add_argument("--sid", default=None, metavar="SESSION_ID",
                        help="Session ID (falls back to $AGENTFLOW_SESSION_ID)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "round":
        rc = {"start": cmd_round_start, "status": cmd_round_status}[args.round_command](args)
    else:
        rc = {"start": cmd_task_start, "done": cmd_task_done}[args.task_command](args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
