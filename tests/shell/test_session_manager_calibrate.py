"""T-164: Tests for calibrate_capacity wiring in on_enter_handoff_pending."""
from __future__ import annotations
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager


def test_handoff_wiring_calls_calibrate_capacity(tmp_path):
    """on_enter_handoff_pending() calls calibrate_capacity with project_root and float pct."""
    sm, _, _ = make_manager()

    with patch("agentflow.shadow.capacity_calibrator.calibrate_capacity") as mock_cal, \
         patch("agentflow.shell.handoff_handler.handle_enter_handoff_pending"):
        sm.on_enter_handoff_pending()

    mock_cal.assert_called_once()
    args, kwargs = mock_cal.call_args
    assert len(args) >= 2
    project_root_arg, start_pct_arg = args[0], args[1]
    assert isinstance(project_root_arg, pathlib.Path)
    assert isinstance(start_pct_arg, float)


def test_handoff_wiring_uses_latest_session_start_snapshot(tmp_path):
    """current_start_pct is read from the most recent session_start snapshot."""
    sm, _, _ = make_manager()
    sm._project_root = tmp_path

    ledger = {
        "usage_snapshots": [
            {"label": "session_start", "ts": "2026-07-10T09:00:00", "start_pct_5hr": 5.0},
            {"label": "session_end",   "ts": "2026-07-10T09:30:00", "start_pct_5hr": 18.0},
            {"label": "session_start", "ts": "2026-07-10T10:00:00", "start_pct_5hr": 42.0},
        ]
    }
    (tmp_path / "agentflow_ledger.json").write_text(json.dumps(ledger))

    with patch("agentflow.shadow.capacity_calibrator.calibrate_capacity") as mock_cal, \
         patch("agentflow.shell.handoff_handler.handle_enter_handoff_pending"):
        sm.on_enter_handoff_pending()

    args = mock_cal.call_args[0]
    assert abs(args[1] - 42.0) < 1e-9


def test_handoff_wiring_defaults_start_pct_to_zero_when_no_snapshots(tmp_path):
    """Falls back to 0.0 when ledger has no usage_snapshots."""
    sm, _, _ = make_manager()
    sm._project_root = tmp_path

    (tmp_path / "agentflow_ledger.json").write_text(json.dumps({}))

    with patch("agentflow.shadow.capacity_calibrator.calibrate_capacity") as mock_cal, \
         patch("agentflow.shell.handoff_handler.handle_enter_handoff_pending"):
        sm.on_enter_handoff_pending()

    args = mock_cal.call_args[0]
    assert args[1] == 0.0


def test_handoff_wiring_nonfatal(tmp_path):
    """calibrate_capacity raising must not prevent handle_enter_handoff_pending from running."""
    sm, _, _ = make_manager()

    with patch("agentflow.shadow.capacity_calibrator.calibrate_capacity",
               side_effect=RuntimeError("boom")), \
         patch("agentflow.shell.handoff_handler.handle_enter_handoff_pending") as mock_handler:
        sm.on_enter_handoff_pending()  # must not raise

    mock_handler.assert_called_once_with(sm)
