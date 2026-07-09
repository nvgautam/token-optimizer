"""Extracted CLI command implementations for agentflow."""

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


def _check_shell_deps() -> None:
    """Warn about missing or outdated runtime dependencies before shell starts."""
    try:
        import importlib.metadata
        importlib.metadata.version("headroom-ai")
    except importlib.metadata.PackageNotFoundError:
        print(
            "[agentflow] WARNING: headroom-ai not installed — proxy compression disabled.\n"
            "  Fix: pip install -e .\n"
            "  Or:  pip install -r requirements.lock\n",
            flush=True,
        )


def cmd_shell(args: argparse.Namespace) -> int:
    from agentflow.shell.pty_wrapper import PTYWrapper
    from agentflow.shell.session_manager import SessionManager
    from agentflow.shell import tokenizer as tokenizer_module
    from agentflow.shell.pty_shell import ProxyShell

    _check_shell_deps()

    cmd = args.shell_command
    if cmd == "gemini":
        cmd = "agy"
    elif cmd == "claude2":
        os.environ["CLAUDE_CONFIG_DIR"] = str(Path.home() / ".claude-2")
        cmd = "claude"

    proxy = ProxyShell(project_root=Path.cwd())
    proxy.start()
    print(proxy.banner())

    import uuid
    import json
    import datetime

    session_id = str(uuid.uuid4())
    os.environ["AGENTFLOW_SESSION_ID"] = session_id

    arm = None
    try:
        arm_file = Path.cwd() / ".agentflow" / "verbosity_ab_arm.txt"
        if arm_file.exists():
            arm = arm_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    session_data = {
        "arm": arm,
        "session_type": None,
        "started_at": datetime.datetime.now().isoformat(),
    }

    try:
        sessions_dir = Path.home() / ".agentflow" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / f"{session_id}.json").write_text(json.dumps(session_data), encoding="utf-8")
    except Exception:
        pass

    from agentflow.shell.usage_capture import capture_usage, write_usage_to_ledger

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    wrapper = None
    try:
        tty.setraw(fd)
        from agentflow.shell.state_machine import States
        wrapper = PTYWrapper([cmd])
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
                        if session_manager._state_machine.state != States.RESTARTING:
                            os.write(wrapper.master_fd, chunk)
                except OSError:
                    break

            if wrapper.master_fd in ready:
                chunk = wrapper.read_output()
                if chunk:
                    os.write(1, chunk)
            else:
                try:
                    pid, wstatus = os.waitpid(wrapper.child_pid, os.WNOHANG)
                    if pid == wrapper.child_pid:
                        wrapper._exited = True
                        wrapper._exit_code = os.waitstatus_to_exitcode(wstatus)
                        if wrapper._on_exit is not None:
                            wrapper._on_exit(wrapper._exit_code)
                            wrapper._on_exit = None
                        if wrapper._exited:
                            break
                        continue
                except ChildProcessError:
                    wrapper._exited = True
                    wrapper._exit_code = -1
                    break
                session_manager.on_idle_tick()

    finally:
        if wrapper is not None:
            _u = capture_usage(wrapper, timeout=2.0)
            if _u:
                write_usage_to_ledger(_u, Path.cwd() / "agentflow_ledger.json", "session_end")
        proxy.stop()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    sys.exit(wrapper._exit_code or 0)
