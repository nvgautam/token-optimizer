"""Tests for T-155: PTY session_type detection — oracle vs orchestrate threshold routing."""
from __future__ import annotations
import pathlib
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager, FakePTY, FakeTokenizer


def _write_signal_file(tmp_path: pathlib.Path, value: str) -> None:
    sig_dir = tmp_path / ".agentflow"
    sig_dir.mkdir(parents=True, exist_ok=True)
    (sig_dir / "session_type").write_text(value, encoding="utf-8")


def test_oracle_signal_file_sets_oracle_threshold(tmp_path):
    """Signal file containing 'oracle' → threshold_tokens == 50000."""
    _write_signal_file(tmp_path, "oracle")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 50000
    assert sm.session_type == "oracle"


def test_orchestrator_signal_file_sets_orchestrator_threshold(tmp_path):
    """Signal file containing 'orchestrator' → threshold_tokens == 80000."""
    _write_signal_file(tmp_path, "orchestrator")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 80000
    assert sm.session_type == "orchestrator"


def test_no_signal_file_leaves_threshold_unchanged(tmp_path):
    """No signal file → threshold stays at default 80000."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 80000
    assert sm.session_type is None


def test_signal_file_with_whitespace_is_stripped(tmp_path):
    """Signal file with surrounding whitespace/newlines is still parsed correctly."""
    _write_signal_file(tmp_path, "  oracle\n")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 50000
    assert sm.session_type == "oracle"


def test_unknown_signal_file_value_leaves_threshold_unchanged(tmp_path):
    """Unknown signal file value is ignored; threshold stays at default."""
    _write_signal_file(tmp_path, "unknown_type")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 80000
    assert sm.session_type is None


def test_sync_after_output_handler_sets_session_type(tmp_path):
    """Manually setting session_type to 'oracle' then calling _sync_session_type() applies threshold."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm._state_machine.threshold_tokens == 80000  # default
    sm.session_type = "oracle"
    sm._sync_session_type()
    assert sm._state_machine.threshold_tokens == 50000


def test_sync_orchestrator_after_output_handler_sets_session_type(tmp_path):
    """Manually setting session_type to 'orchestrator' then calling _sync_session_type() keeps 80000."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    sm.session_type = "orchestrator"
    sm._sync_session_type()
    assert sm._state_machine.threshold_tokens == 80000


def test_idle_tick_calls_sync(tmp_path):
    """on_idle_tick() applies threshold update if session_type is set."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    sm.session_type = "oracle"
    # threshold still at default before tick
    assert sm._state_machine.threshold_tokens == 80000
    with patch.object(sm, "poll"):
        sm.on_idle_tick()
    assert sm._state_machine.threshold_tokens == 50000


def test_idle_tick_picks_up_signal_file(tmp_path):
    """on_idle_tick() reads signal file if session_type is still None."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm.session_type is None
    # Write signal file after construction
    _write_signal_file(tmp_path, "oracle")
    with patch.object(sm, "poll"):
        sm.on_idle_tick()
    assert sm.session_type == "oracle"
    assert sm._state_machine.threshold_tokens == 50000


def test_apply_session_threshold_no_op_when_no_session_type(tmp_path):
    """_apply_session_threshold() is a no-op when session_type is None."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    initial = sm._state_machine.threshold_tokens
    sm._apply_session_threshold()
    assert sm._state_machine.threshold_tokens == initial


def test_apply_session_threshold_no_op_when_already_correct(tmp_path):
    """_apply_session_threshold() does not reassign when value is already correct."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    sm.session_type = "oracle"
    sm._state_machine.threshold_tokens = 50000  # already correct
    sm._apply_session_threshold()
    assert sm._state_machine.threshold_tokens == 50000


def test_oracle_threshold_uses_config_override(tmp_path):
    """oracle_threshold_tokens from config dict overrides default 50000."""
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager(config={"oracle_threshold_tokens": 30000})
    sm.session_type = "oracle"
    sm._sync_session_type()
    assert sm._state_machine.threshold_tokens == 30000


def test_signal_file_not_read_when_session_type_already_set(tmp_path):
    """T-189: sync_session_type re-reads signal file even when session_type is already set.

    This fixes the bug where a stale session_type value causes wrong-command injection.
    """
    _write_signal_file(tmp_path, "orchestrator")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    # After init, session_type should be "orchestrator" from signal file
    assert sm.session_type == "orchestrator"
    # Now overwrite signal file with different value
    _write_signal_file(tmp_path, "oracle")
    # T-189: _sync_session_type now re-reads even when session_type is already set
    sm._sync_session_type()
    assert sm.session_type == "oracle"  # Should update to new value
    assert sm._state_machine.threshold_tokens == 50000  # Threshold should update to oracle's threshold


def test_sync_session_type_reads_session_state_json(tmp_path):
    """session_manager reads session_state.json (JSON format) and sets session_type."""
    import json
    sig_dir = tmp_path / ".agentflow"
    sig_dir.mkdir(parents=True, exist_ok=True)
    session_state_file = sig_dir / "session_state.json"
    session_state_file.write_text(json.dumps({"session_type": "oracle"}), encoding="utf-8")

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm.session_type == "oracle"
    assert sm._state_machine.threshold_tokens == 50000


def test_sync_session_type_reads_orchestrator_from_session_state_json(tmp_path):
    """session_manager reads orchestrator type from session_state.json."""
    import json
    sig_dir = tmp_path / ".agentflow"
    sig_dir.mkdir(parents=True, exist_ok=True)
    session_state_file = sig_dir / "session_state.json"
    session_state_file.write_text(json.dumps({"session_type": "orchestrator"}), encoding="utf-8")

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm.session_type == "orchestrator"
    assert sm._state_machine.threshold_tokens == 80000


def test_sync_session_type_fallback_to_text_file_when_no_json(tmp_path):
    """When session_state.json doesn't exist, fall back to plain text session_type file."""
    _write_signal_file(tmp_path, "oracle")
    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm.session_type == "oracle"
    assert sm._state_machine.threshold_tokens == 50000


def test_sync_session_type_json_takes_precedence_over_text_file(tmp_path):
    """When both session_state.json and session_type exist, JSON takes precedence."""
    import json
    sig_dir = tmp_path / ".agentflow"
    sig_dir.mkdir(parents=True, exist_ok=True)
    # Write both files with different values
    (sig_dir / "session_type").write_text("oracle", encoding="utf-8")
    session_state_file = sig_dir / "session_state.json"
    session_state_file.write_text(json.dumps({"session_type": "orchestrator"}), encoding="utf-8")

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    # JSON should take precedence
    assert sm.session_type == "orchestrator"
    assert sm._state_machine.threshold_tokens == 80000


def test_sync_session_type_ignores_invalid_json(tmp_path):
    """When session_state.json contains invalid JSON, fall back to text file."""
    import json
    sig_dir = tmp_path / ".agentflow"
    sig_dir.mkdir(parents=True, exist_ok=True)
    # Write invalid JSON
    session_state_file = sig_dir / "session_state.json"
    session_state_file.write_text("not valid json", encoding="utf-8")
    # Write valid text file as fallback
    (sig_dir / "session_type").write_text("oracle", encoding="utf-8")

    with patch.object(pathlib.Path, "cwd", return_value=tmp_path):
        sm, _, _ = make_manager()
    assert sm.session_type == "oracle"
    assert sm._state_machine.threshold_tokens == 50000
