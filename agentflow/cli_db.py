"""agentflow.cli_db — CLI-as-interface layer for state mutations."""
from __future__ import annotations
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agentflow.shell.session_paths import session_file


def _atomic_write(path: Path, data_str: str) -> None:
    """Write data_str to path atomically via tempfile + os.replace."""
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data_str)
        os.replace(tmp, str(path))
    except Exception as e:
        print(f"atomic_write_error: {e}", file=sys.stderr)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def cmd_round_start(args: argparse.Namespace) -> int:
    """Atomically write current_round.json + tasks_in_flight.json."""
    sid: str = args.sid if args.sid else os.environ.get("AGENTFLOW_SESSION_ID", "")
    round_id: str = (
        args.round_id if args.round_id
        else "round-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    task_ids: list[str] = list(args.task_ids)
    timestamp: str = datetime.now(timezone.utc).isoformat()

    agentflow_dir = Path(".agentflow")
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    round_data = {
        "round_id": round_id,
        "task_ids": task_ids,
        "estimated_lines_per_task": {},
        "file_counts_per_task": {},
        "session_id": sid,
        "timestamp": timestamp,
    }
    current_round_path = agentflow_dir / "current_round.json"
    _atomic_write(current_round_path, json.dumps(round_data, indent=2))

    tif_path = session_file(agentflow_dir, "tasks_in_flight.json", sid or None)
    _atomic_write(tif_path, json.dumps(task_ids))

    print(round_id)
    return 0


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
