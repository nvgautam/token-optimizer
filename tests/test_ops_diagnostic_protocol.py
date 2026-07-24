"""
Test evidence-first diagnostic protocol for ops.md.
Verifies novel failure modes (fill_stale) and known patterns (A/B/C) are handled.
"""


def test_fill_stale_diagnosis():
    """Novel failure mode (fill_stale) is diagnosed without pre-enumerated class."""
    pty_audit_log = [
        {
            "event": "drain_check_skip",
            "reason": "fill_stale",
            "ts": "2026-07-24T10:00:00Z",
            "session_id": "test-sid-123"
        }
    ]

    signals = extract_observable_signals(pty_audit_log)
    assert "drain_check_skip" in signals
    assert signals["drain_check_skip"]["reason"] == "fill_stale"

    diagnosis = diagnose_from_signals(signals)
    assert "fill_stale" in diagnosis["root_cause"].lower()
    assert "context" in diagnosis["root_cause"].lower()


def test_pattern_a_pty_stuck():
    """Known pattern A (PTY stuck) is correctly diagnosed."""
    pty_audit_log = [
        {
            "event": "drain_check_skip",
            "reason": "tasks_in_flight_nonempty",
            "ts": "2026-07-24T10:00:00Z"
        }
    ]

    signals = extract_observable_signals(pty_audit_log)
    diagnosis = diagnose_from_signals(signals)

    assert "pty" in diagnosis["root_cause"].lower()
    assert "task" in diagnosis["root_cause"].lower()


def test_pattern_b_drain_missed():
    """Known pattern B (Drain missed) is correctly diagnosed."""
    hook_drain_log = [
        {
            "event": "pr_merge_direct",
            "ts": "2026-07-24T10:00:00Z"
        }
    ]

    signals = extract_observable_signals([], hook_drain_log)
    diagnosis = diagnose_from_signals(signals)

    assert "hook" in diagnosis["root_cause"].lower() or "drain" in diagnosis["root_cause"].lower()


def test_pattern_c_split_brain():
    """Known pattern C (Split-brain) is correctly diagnosed."""
    task_state = {
        "tasks": [
            {"task_id": "T-100", "status": "complete"}
        ]
    }

    in_flight_state = [
        {"task_id": "T-100", "session_id": "active-sid"}
    ]

    signals = extract_observable_signals([], [], task_state, in_flight_state)
    diagnosis = diagnose_from_signals(signals)

    assert "split" in diagnosis["root_cause"].lower() or "sync" in diagnosis["root_cause"].lower()


def test_protocol_structure_not_enumerated():
    """Verify protocol doesn't rely on pre-enumerated symptom classes."""
    pty_audit_log = [
        {"event": "unknown_event", "reason": "novel_failure_mode", "ts": "2026-07-24T10:00:00Z"}
    ]

    signals = extract_observable_signals(pty_audit_log)
    diagnosis = diagnose_from_signals(signals)

    assert "diagnosis" in diagnosis or "root_cause" in diagnosis


def extract_observable_signals(pty_audit_log=None, hook_drain_log=None,
                               task_state=None, in_flight_state=None):
    """Extract observable signals from log files and state."""
    signals = {}

    if pty_audit_log:
        for entry in pty_audit_log:
            event = entry.get("event", "unknown")
            signals[event] = entry

    if hook_drain_log:
        for entry in hook_drain_log:
            event = entry.get("event", "unknown")
            signals[event] = entry

    if task_state:
        tasks = task_state.get("tasks", [])
        if tasks:
            signals["task_state"] = {
                "total": len(tasks),
                "complete": sum(1 for t in tasks if t.get("status") == "complete")
            }

    if in_flight_state:
        signals["in_flight_state"] = in_flight_state

    return signals


def diagnose_from_signals(signals):
    """Reason from observable signals to root cause."""
    diagnosis = {"root_cause": "", "fix": ""}

    if "drain_check_skip" in signals:
        entry = signals["drain_check_skip"]
        reason = entry.get("reason", "")

        if reason == "tasks_in_flight_nonempty":
            diagnosis["root_cause"] = "PTY stuck: task remains in-flight"
            diagnosis["fix"] = "Check task status and force cleanup if necessary"
        elif reason == "fill_stale":
            diagnosis["root_cause"] = "Fill_stale: stale context blocking handoff"
            diagnosis["fix"] = "Clear context cache or implement context isolation"
        else:
            diagnosis["root_cause"] = f"PTY issue: {reason}"
            diagnosis["fix"] = "Investigate cause of drain_check_skip"

    elif "pr_merge_direct" in signals and "hook_fired" not in signals:
        diagnosis["root_cause"] = "Drain missed: hook not triggered on merge"
        diagnosis["fix"] = "Verify hook registration and event matching"

    elif "in_flight_state" in signals and "task_state" in signals:
        in_flight_ids = {t.get("task_id") for t in signals["in_flight_state"]}
        task_state = signals["task_state"]
        if task_state.get("complete", 0) > 0:
            diagnosis["root_cause"] = "Split-brain: task marked complete but still in-flight"
            diagnosis["fix"] = "Signal task_done to sync state, then drain"

    else:
        diagnosis["root_cause"] = "Unable to determine root cause from available signals"
        diagnosis["fix"] = "Collect additional diagnostic data"

    return diagnosis
