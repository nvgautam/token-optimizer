"""Debug restart trigger — creates a manual PTY restart for testing."""

from pathlib import Path


_TRIGGER_FILE = Path(".agentflow/debug_restart_trigger")


def check_debug_restart_trigger(manager) -> None:
    if not _TRIGGER_FILE.exists():
        return
    try:
        _TRIGGER_FILE.unlink()
    except FileNotFoundError:
        return
    manager._log_audit({"event": "debug_restart_trigger", "source": "debug_trigger_file"})
    manager.trigger_handoff(trigger="debug")
