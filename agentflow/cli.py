"""CLI entry point for agentflow."""

import argparse
import sys
from pathlib import Path

# Re-export for backward compatibility with tests and external imports
from agentflow.cli_cmds import cmd_init, cmd_shell, _check_shell_deps  # noqa: F401


def cmd_oracle(args: argparse.Namespace) -> int:
    print("agentflow oracle — start the oracle skill in your AI CLI (claude or agy)\n  Use /oracle in Claude Code or the agy CLI.")
    return 0


def cmd_orchestrate_start(args: argparse.Namespace) -> int:
    print("agentflow orchestrate start — not yet implemented"); return 0


def cmd_orchestrate_status(args: argparse.Namespace) -> int:
    print("agentflow orchestrate status — not yet implemented"); return 0


def cmd_orchestrate_merge(args: argparse.Namespace) -> int:
    print("agentflow orchestrate merge — not yet implemented"); return 0


def cmd_report(args: argparse.Namespace) -> int:
    if args.mode == "session":
        from agentflow.legacy_report import cmd_report as legacy_cmd_report
        legacy_cmd_report(args); return 0
    from agentflow.reporting.report_builder import build_report
    return build_report(project_root=Path.cwd(), mode=args.mode, output_path=args.output)


def cmd_validate(args: argparse.Namespace) -> int:
    print("agentflow validate — not yet implemented"); return 0


def cmd_scan(args: argparse.Namespace) -> int:
    print("agentflow scan — not yet implemented"); return 0


def cmd_install(args: argparse.Namespace) -> int:
    from agentflow.ip.installer import install
    install(project_root=Path.cwd())
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    from agentflow.ip.installer import uninstall
    uninstall()
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    print(f"agentflow hooks {args.name} — internal hook dispatch not yet wired")
    return 0


class AgentFlowParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if parsed.command == "report":
            if getattr(parsed, "agent", None) is not None and parsed.mode != "session":
                self.error("argument --agent is only valid when --mode is 'session'")
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = AgentFlowParser(
        prog="agentflow",
        description="AgentFlow — provider-agnostic multi-agent project management",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")

    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    sub.add_parser("init", help="Scaffold .agentflow/ in the current project")
    sub.add_parser("oracle", help="Print instructions for starting an oracle session")

    orch = sub.add_parser("orchestrate", help="Manage the agent orchestration lifecycle")
    orch_sub = orch.add_subparsers(dest="orch_command", metavar="subcommand")
    orch_sub.required = True
    orch_sub.add_parser("start", help="Read tasks.json and begin the lifecycle")
    orch_sub.add_parser("status", help="Show live progress dashboard")
    orch_sub.add_parser("merge", help="Trigger DAG-ordered merge of approved PRs")

    round_p = sub.add_parser("round", help="Manage round state (CLI-as-interface layer)")
    round_sub = round_p.add_subparsers(dest="round_command", metavar="subcommand")
    round_sub.required = True
    start_p = round_sub.add_parser("start", help="Atomically write current_round.json + tasks_in_flight.json")
    start_p.add_argument("--task-ids", nargs="+", required=True, dest="task_ids", metavar="TASK_ID")
    start_p.add_argument("--round-id", default=None, dest="round_id", metavar="ROUND_ID")
    start_p.add_argument("--sid", default=None, metavar="SESSION_ID")
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

    report = sub.add_parser("report", help="Show token usage report across sessions")
    report.add_argument("--mode", choices=["aggregate", "split", "session"], default="aggregate")
    report.add_argument("--output", default="combined_report.html")
    report.add_argument("--agent", choices=["claude", "agy"], default=None)

    validate = sub.add_parser("validate", help="Validate tasks.json schema and ownership rules")
    validate.add_argument("tasks_file", nargs="?", default="tasks.json", metavar="FILE")

    scan = sub.add_parser("scan", help="Scan an existing project and build the symbol index")
    scan.add_argument("path", nargs="?", default=".", metavar="PATH")

    shell = sub.add_parser("shell", help="Start the PTY overlay shell (wraps claude or agy)")
    shell.add_argument("--command", dest="shell_command", default="claude")

    sub.add_parser("install", help="Install agentflow hooks into ~/.claude/settings.json")
    sub.add_parser("uninstall", help="Remove agentflow hooks from ~/.claude/settings.json")

    hooks_p = sub.add_parser("hooks", help="Internal hook dispatch (used by hook commands)")
    hooks_p.add_argument("name", help="Hook name to dispatch")

    cache = sub.add_parser("cache", help="Manage the AgentFlow cache")
    cache_sub = cache.add_subparsers(dest="cache_command", metavar="subcommand")
    cache_sub.required = True
    prune_p = cache_sub.add_parser("prune", help="Remove stale cache entries")
    prune_p.add_argument("--older-than", type=int, default=30, metavar="DAYS",
                         help="Remove dirs not accessed in this many days (default: 30)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "oracle": cmd_oracle,
        "report": cmd_report,
        "validate": cmd_validate,
        "scan": cmd_scan,
        "shell": cmd_shell,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "hooks": cmd_hooks,
    }

    if args.command == "orchestrate":
        orch_handlers = {
            "start": cmd_orchestrate_start,
            "status": cmd_orchestrate_status,
            "merge": cmd_orchestrate_merge,
        }
        rc = orch_handlers[args.orch_command](args)
    elif args.command == "round":
        from agentflow.cli_db import cmd_round_start, cmd_round_status
        rc = {"start": cmd_round_start, "status": cmd_round_status}[args.round_command](args)
    elif args.command == "task":
        from agentflow.cli_db import cmd_task_start, cmd_task_done
        rc = {"start": cmd_task_start, "done": cmd_task_done}[args.task_command](args)
    elif args.command == "cache":
        from agentflow.cli_cmds import cmd_cache_prune
        rc = cmd_cache_prune(args)
    else:
        rc = handlers[args.command](args)

    sys.exit(rc)


if __name__ == "__main__":
    main()
