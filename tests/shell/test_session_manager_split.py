"""Test that SessionManager split maintains backward compatibility."""
import pytest
from agentflow.shell.session_manager import SessionManager


def test_session_manager_import():
    """SessionManager must still be importable from session_manager module."""
    assert SessionManager is not None
    assert callable(SessionManager)


def test_session_manager_has_expected_methods():
    """SessionManager should have all expected public/protected methods."""
    expected_methods = [
        "on_idle_tick",
        "poll",
        "on_enter_handoff_pending",
        "on_enter_restarting",
        "on_enter_idle",
        "on_enter_dead_child",
        "restart_child",
        "trigger_handoff",
    ]
    for method_name in expected_methods:
        assert hasattr(SessionManager, method_name), f"SessionManager missing {method_name}"


def test_session_manager_has_properties():
    """SessionManager should have expected properties."""
    expected_props = [
        "_project_root",
        "_current_round_path",
        "_task_complete_path",
        "_handoff_complete_path",
        "_handoff_in_progress",
    ]
    for prop_name in expected_props:
        assert hasattr(SessionManager, prop_name), f"SessionManager missing property {prop_name}"
