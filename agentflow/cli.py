"""CLI entry point for agentflow."""

import argparse
import sys
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
    print("agentflow oracle — start the oracle skill in your AI CLI (claude or gemini)")
    print("  Use /oracle in Claude Code or the Gemini CLI.")
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
    print("agentflow report — not yet implemented")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    print("agentflow validate — not yet implemented")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    print("agentflow scan — not yet implemented")
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    print("agentflow shell — not yet implemented")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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

    sub.add_parser("report", help="Show token usage report across sessions")

    validate = sub.add_parser("validate", help="Validate tasks.json schema and ownership rules")
    validate.add_argument("tasks_file", nargs="?", default="tasks.json", metavar="FILE")

    scan = sub.add_parser("scan", help="Scan an existing project and build the symbol index")
    scan.add_argument("path", nargs="?", default=".", metavar="PATH",
                      help="Project root to scan (default: current directory)")

    shell = sub.add_parser("shell", help="Start the PTY overlay shell (wraps claude or gemini)")
    shell.add_argument("--command", default="claude",
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
