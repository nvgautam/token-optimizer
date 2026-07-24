"""Oracle session consent prompt and handoff UX (T-301).

When an oracle session accumulates oracle_consent_threshold_tokens the PTY
injects a user-facing consent prompt.  The session restarts only on explicit
confirmation; decline (any other response) keeps the session running.

PTY shell: stdlib-only, zero LLM calls.
"""
from __future__ import annotations
import os

from agentflow.shell.state_machine import States
from agentflow.config.constants import is_oracle_session

_CONSENT_THRESHOLD_DEFAULT = 90_000
_CONSENT_PROMPT = (
    "For crisp decision making, taking forward the context into a new session"
    " is important. Session restart with context carried forward?"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_oracle_idle(manager) -> bool:
    return is_oracle_session(manager.session_type) and manager._state_machine.state == States.IDLE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def should_prompt_consent(manager) -> bool:
    """Return True when oracle reaches threshold and consent hasn't fired."""
    if not _is_oracle_idle(manager):
        return False
    if getattr(manager, "_oracle_consent_fired", False):
        return False
    if manager._auto_handoff_disabled():
        return False
    threshold = manager._config.get(
        "oracle_consent_threshold_tokens", _CONSENT_THRESHOLD_DEFAULT
    )
    from agentflow.shell.output_handler import _read_fill_tokens
    fill = _read_fill_tokens(manager._project_root)
    tokens = fill if fill is not None else manager._last_accumulated_tokens
    return tokens >= threshold


def inject_consent_prompt(manager) -> None:
    """Display consent prompt on the terminal and inject it into oracle stdin."""
    display = f"\r\n\x1b[33m[AgentFlow] {_CONSENT_PROMPT}\x1b[0m\r\n"
    try:
        os.write(1, display.encode("utf-8"))
    except OSError as e:
        manager._log_audit({"event": "oracle_consent_display_error", "error": str(e)})
    try:
        manager._pty.write_input(_CONSENT_PROMPT + "\r")
    except OSError as e:
        manager._log_audit({"event": "oracle_consent_inject_error", "error": str(e)})
        return
    manager._oracle_consent_pending = True
    manager._oracle_consent_fired = True
    manager._log_audit({
        "event": "oracle_consent_prompt_injected",
        "tokens": manager._last_accumulated_tokens,
    })


def check_oracle_consent_threshold(manager) -> None:
    """Called from on_idle_tick — injects consent prompt when threshold crossed."""
    if should_prompt_consent(manager):
        inject_consent_prompt(manager)


def check_oracle_consent_output(manager, chunk: bytes) -> None:  # noqa: ARG001
    """Called from _handle_output — detect handoff_complete when consent is pending.

    When oracle runs /handoff after the user confirms, the handoff_complete
    signal file is written.  Detecting it here lets us transition to
    HANDOFF_PENDING without injecting a redundant /handoff command.
    """
    if not getattr(manager, "_oracle_consent_pending", False):
        return
    if getattr(manager, "_oracle_consent_confirmed", False):
        return
    if not manager._handoff_complete_path.exists():
        return
    manager._oracle_consent_confirmed = True
    manager._oracle_consent_pending = False
    manager._log_audit({
        "event": "oracle_consent_confirmed_via_handoff_complete",
        "tokens": manager._last_accumulated_tokens,
    })
    try:
        manager.trigger_handoff(trigger="oracle_consent")
    except Exception as e:
        manager._log_audit({"event": "oracle_consent_trigger_handoff_error", "error": str(e)})


def on_enter_handoff_pending_oracle(manager) -> bool:
    """Pre-hook for on_enter_handoff_pending.

    Returns True to skip the normal handler when oracle consent was already
    confirmed (handoff ran via oracle skill; don't inject /handoff again).
    """
    if getattr(manager, "_oracle_consent_confirmed", False) and is_oracle_session(manager.session_type):
        manager._log_audit({"event": "oracle_consent_handoff_pending_skip"})
        return True
    return False


def on_session_exit_oracle(manager) -> bool:
    """Pre-hook for _on_session_exit.

    Returns True to handle the exit directly for oracle consent restarts,
    bypassing the orchestrator-only gate in session_manager_handlers.
    """
    if not getattr(manager, "_oracle_consent_confirmed", False):
        return False
    if not is_oracle_session(manager.session_type):
        return False
    if manager._state_machine.state != States.HANDOFF_PENDING:
        return False
    if not manager._handoff_complete_path.exists():
        return False
    manager._state_machine.transition("handoff_complete_written")
    return True


def on_enter_restarting_oracle(manager) -> None:
    """Pre-hook for on_enter_restarting — adds --permission-mode auto for oracle consent."""
    if not getattr(manager, "_oracle_consent_confirmed", False):
        return
    if not is_oracle_session(manager.session_type):
        return
    cmd = list(getattr(manager._pty, "_command", []) or [])
    if "--permission-mode" not in cmd:
        manager._pty._command = cmd + ["--permission-mode", "auto"]
        manager._log_audit({"event": "oracle_consent_auto_mode_set"})
