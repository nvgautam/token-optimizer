"""Tests for agentflow.shell.state_machine."""
from __future__ import annotations
import pytest
from agentflow.shell.state_machine import States, StateMachine

def test_state_machine_initial_state():
    sm = StateMachine()
    assert sm.state == States.IDLE

def test_state_machine_transitions():
    sm = StateMachine()
    
    # IDLE -> TASK_RUNNING
    sm.transition("current_round_written")
    assert sm.state == States.TASK_RUNNING

    # TASK_RUNNING -> TASK_COMPLETE
    sm.transition("task_complete_written")
    assert sm.state == States.TASK_COMPLETE

    # TASK_COMPLETE -> IDLE (no token guard)
    sm.state = States.TASK_COMPLETE
    sm.transition("task_round_complete")
    assert sm.state == States.IDLE

    sm.state = States.TASK_COMPLETE
    sm.transition("task_round_complete")
    assert sm.state == States.IDLE

    # HANDOFF_PENDING -> RESTARTING
    sm.state = States.HANDOFF_PENDING
    sm.transition("handoff_complete_written")
    assert sm.state == States.RESTARTING

    # RESTARTING -> IDLE
    sm.transition("restart_done")
    assert sm.state == States.IDLE

def test_state_machine_dead_child():
    for state in States:
        sm = StateMachine(initial_state=state)
        sm.transition("pty_eof")
        assert sm.state == States.DEAD_CHILD

def test_state_machine_hooks():
    entered_states = []
    
    class CustomSM(StateMachine):
        def on_enter_task_running(self):
            entered_states.append("TASK_RUNNING")
        def on_enter_dead_child(self):
            entered_states.append("DEAD_CHILD")

    sm = CustomSM()
    sm.transition("current_round_written")
    assert "TASK_RUNNING" in entered_states

    sm.transition("pty_eof")
    assert "DEAD_CHILD" in entered_states
