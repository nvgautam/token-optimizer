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
    else:
        rc = handlers[args.command](args)

    sys.exit(rc)


if __name__ == "__main__":
    main()
