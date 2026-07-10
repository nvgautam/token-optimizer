"""PTY session state machine.

Defines explicit states and transitions driven by file/PTY events.
"""
from __future__ import annotations
from enum import Enum
import os

class States(Enum):
    IDLE = "IDLE"
    TASK_RUNNING = "TASK_RUNNING"
    TASK_COMPLETE = "TASK_COMPLETE"
    HANDOFF_PENDING = "HANDOFF_PENDING"
    RESTARTING = "RESTARTING"
    DEAD_CHILD = "DEAD_CHILD"

class StateMachine:
    """Explicit state machine for managing PTY shell transitions."""

    def __init__(self, initial_state: States = States.IDLE, threshold_tokens: int = 80000) -> None:
        self.state = initial_state
        self.threshold_tokens = threshold_tokens

    def transition(self, event: str, **kwargs) -> States:
        """Transitions state based on event and current state, running hooks."""
        old_state = self.state

        # PTY master fd EOF transitions any state to DEAD_CHILD
        if event == "pty_eof":
            new_state = States.DEAD_CHILD
        elif event == "trigger_handoff":
            new_state = States.HANDOFF_PENDING
        elif event == "handoff_aborted":
            new_state = States.IDLE
        elif event == "restart_session":
            new_state = States.RESTARTING
        else:
            new_state = self._get_next_state(event, **kwargs)

        if new_state != old_state:
            self.state = new_state
            self._trigger_hook(new_state)

        return self.state

    def _get_next_state(self, event: str, **kwargs) -> States:
        """Determines the next state based on the current state and event, applying guards."""
        state = self.state

        if state == States.IDLE:
            if event == "current_round_written":
                return States.TASK_RUNNING

        elif state == States.TASK_RUNNING:
            if event == "task_complete_written":
                return States.TASK_COMPLETE

        elif state == States.TASK_COMPLETE:
            if event == "check_tokens":
                tokens = kwargs.get("tokens", 0)
                if self.guard_tokens_threshold(tokens):
                    return States.HANDOFF_PENDING
                return States.IDLE

        elif state == States.HANDOFF_PENDING:
            if event == "handoff_complete_written":
                return States.RESTARTING

        elif state == States.RESTARTING:
            if event == "restart_done":
                return States.IDLE

        elif state == States.DEAD_CHILD:
            # Fallback: restart_child completed despite the PTY-EOF race winning first.
            if event == "restart_done":
                return States.IDLE

        return state

    def guard_tokens_threshold(self, tokens: int) -> bool:
        """Guard function checking if accumulated tokens meet or exceed the threshold."""
        return tokens >= self.threshold_tokens

    def _trigger_hook(self, state: States) -> None:
        """Dynamically calls the on_enter_<state_name> hook if it exists."""
        hook_name = f"on_enter_{state.name.lower()}"
        hook = getattr(self, hook_name, None)
        if hook and callable(hook):
            try:
                hook()
            except Exception:
                pass

    # Hook placeholders that subclasses or callers can override
    def on_enter_idle(self) -> None:
        pass

    def on_enter_task_running(self) -> None:
        pass

    def on_enter_task_complete(self) -> None:
        pass

    def on_enter_handoff_pending(self) -> None:
        pass

    def on_enter_restarting(self) -> None:
        pass

    def on_enter_dead_child(self) -> None:
        pass
