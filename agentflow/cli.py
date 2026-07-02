"""CLI entry point for agentflow."""

import argparse
import os
import select
import sys
import termios
import tty
from pathlib import Path

_PROJECT_CONFIG_TEMPLATE = """\
# AgentFlow project configuration
# All fields are optional — omit to inherit from user config (~/.agentflow/config.yaml) or defaults.

models:
  oracle: claude-opus-4-8
  worker: claude-sonnet-4-6
  reviewer_code: claude-sonnet-4-6
  reviewer_security: claude-opus-4-8

token_budget:
  per_worker: 50000
  reviewer: 20000

testing:
  coverage_threshold: 85
  require_integration_tests: true

parallelism: 4
"""


def cmd_init(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    af_dir = cwd / ".agentflow"

    if af_dir.exists():
        print(f"Already initialised: {af_dir}")
        return 0

    af_dir.mkdir()
    config_path = af_dir / "config.yaml"
    config_path.write_text(_PROJECT_CONFIG_TEMPLATE, encoding="utf-8")

    try:
        from agentflow.telemetry.logger import get_logger
        logger = get_logger(output_path=af_dir / "telemetry.jsonl")
        logger.emit("init", status="ok", metadata={"cwd": str(cwd)})
    except Exception:
        pass

    print(f"Initialised AgentFlow in {af_dir}")
    print(f"  config  → {config_path}")
    print(f"  telemetry → {af_dir / 'telemetry.jsonl'}")
    print("\nEdit .agentflow/config.yaml to customise models, budgets, and parallelism.")
    return 0


def cmd_oracle(args: argparse.Namespace) -> int:
    print("agentflow oracle — start the oracle skill in your AI CLI (claude or agy)")
    print("  Use /oracle in Claude Code or the agy CLI.")
    return 0


def cmd_orchestrate_start(args: argparse.Namespace) -> int:
    print("agentflow orchestrate start — not yet implemented")
    return 0


def cmd_orchestrate_status(args: argparse.Namespace) -> int:
    print("agentflow orchestrate status — not yet implemented")
    return 0


def cmd_orchestrate_merge(args: argparse.Namespace) -> int:
    print("agentflow orchestrate merge — not yet implemented")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if args.mode == "session":
        from agentflow.legacy_report import cmd_report as legacy_cmd_report
        legacy_cmd_report(args)
        return 0
    from agentflow.reporting.report_builder import build_report
    return build_report(
        project_root=Path.cwd(),
        mode=args.mode,
        output_path=args.output
    )


def cmd_validate(args: argparse.Namespace) -> int:
    print("agentflow validate — not yet implemented")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    print("agentflow scan — not yet implemented")
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    from agentflow.shell.pty_wrapper import PTYWrapper
    from agentflow.shell.session_manager import SessionManager
    from agentflow.shell import tokenizer as tokenizer_module
    import shutil

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        cmd = args.shell_command
        if cmd == "gemini":
            cmd = "agy"

        cmd_args = [cmd]
        if shutil.which("headroom"):
            cmd_args = ["headroom", "wrap", cmd]
            os.environ["HEADROOM_WORKSPACE_DIR"] = str(Path.cwd().resolve() / ".headroom")

        wrapper = PTYWrapper(cmd_args)
        session_manager = SessionManager(wrapper, tokenizer_module, config={})

        while not wrapper._exited:
            try:
                ready, _, _ = select.select([fd, wrapper.master_fd], [], [], 0.05)
            except (ValueError, OSError):
                break

            if fd in ready:
                try:
                    chunk = os.read(fd, 1024)
                    if chunk:
                        os.write(wrapper.master_fd, chunk)
                except OSError:
                    break

            if wrapper.master_fd in ready:
                chunk = wrapper.read_output()
                if chunk:
                    os.write(1, chunk)
            else:
                session_manager.on_idle_tick()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    sys.exit(wrapper._exit_code or 0)


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
    report.add_argument(
        "--mode",
        choices=["aggregate", "split", "session"],
        default="aggregate",
        help="Report mode (default: aggregate)",
    )
    report.add_argument(
        "--output",
        default="combined_report.html",
        help="Path to write the HTML report (default: combined_report.html)",
    )
    report.add_argument(
        "--agent",
        choices=["claude", "agy"],
        default=None,
        help="Filter by agent (valid only with --mode session)",
    )

    validate = sub.add_parser("validate", help="Validate tasks.json schema and ownership rules")
    validate.add_argument("tasks_file", nargs="?", default="tasks.json", metavar="FILE")

    scan = sub.add_parser("scan", help="Scan an existing project and build the symbol index")
    scan.add_argument("path", nargs="?", default=".", metavar="PATH",
                      help="Project root to scan (default: current directory)")

    shell = sub.add_parser("shell", help="Start the PTY overlay shell (wraps claude or agy)")
    shell.add_argument("--command", dest="shell_command", default="claude",
                       help="AI CLI command to wrap (default: claude)")

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
