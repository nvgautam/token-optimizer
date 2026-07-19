"""Drain and restart orchestration for session management."""
from __future__ import annotations
import fcntl
import json
import os
import re
import tempfile
import time
from agentflow.shell.session_paths import session_file
from agentflow.shell.state_machine import States


def _write_merged_and_clear(manager) -> None:
	rid, tids = "", []
	try:
		cr = json.loads(manager._current_round_path.read_text("utf-8"))
		rid, tids = cr.get("round_id", ""), cr.get("task_ids", [])
	except FileNotFoundError as e:
		manager._log_audit({"event": "drain_no_current_round", "error": str(e)})
		# fall through — file genuinely absent, safe to unlink TIF and proceed
	except Exception as e:
		manager._log_audit({"event": "drain_no_current_round", "error": str(e)})
		return  # corrupt or mid-write race — preserve TIF, retry next 30s poll
	db = None
	try:
		from agentflow.tools.task_db import TaskDB
		db = TaskDB(manager._project_root / ".agentflow" / "tasks.db")
	except Exception:
		pass
	ep = manager._project_root / "execution_plan.md"
	lock = manager._project_root / "execution_plan.md.lock"
	try:
		with open(lock, "w", encoding="utf-8") as lf:
			fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
			lines = ep.read_text("utf-8").splitlines(keepends=True)
			changed = False
			for i, ln in enumerate(lines):
				for tid in tids:
					if re.match(rf"^## Addendum:\s+{re.escape(tid)}", ln) and "(MERGED)" not in ln:
						lines[i] = ln.rstrip("\n") + " (MERGED)\n"
						changed = True
				if rid and f"| {rid} |" in ln and "MERGED" not in ln:
					lines[i] = ln.rstrip("\n").rstrip() + " — MERGED\n"
					changed = True
			if changed:
				with tempfile.NamedTemporaryFile(mode="w", dir=ep.parent, delete=False, suffix=".tmp", encoding="utf-8") as t:
					t.write("".join(lines))
					tmp = t.name
				os.replace(tmp, ep)
				manager._log_audit({"event": "execution_plan_written", "round_id": rid, "task_ids": tids})
	except Exception as e:
		manager._log_audit({"event": "drain_execution_plan_write_error", "round_id": rid, "error": str(e)})
	try:
		if db:
			db.clear_active_round()
		tif_existed = manager._tasks_in_flight_path.exists()
		manager._tasks_in_flight_path.unlink(missing_ok=True)
		manager._log_audit({"event": "tif_unlinked", "round_id": rid, "existed": tif_existed})
		manager._current_round_path.unlink(missing_ok=True)
		manager._log_audit({"event": "current_round_unlinked", "round_id": rid})
	except Exception as e:
		manager._log_audit({"event": "drain_clear_error", "round_id": rid, "error": str(e)})
	try:
		manager._log_audit({"event": "drain_merged_written", "round_id": rid, "task_ids": tids})
	except Exception:
		pass


# Session-restart improvement (T-260): agentflow round start atomically writes
# current_round.json + tasks_in_flight.json in a single CLI call. This eliminates
# the previous race where drain could read current_round.json after the Write tool
# but before the PostToolUse hook populated tasks_in_flight.json — causing drain
# to see a round with no in-flight tasks and incorrectly trigger a restart.
def check_drain_restart(manager) -> None:
	"""Trigger restart when tasks_in_flight drains and context fill >= 80K."""
	def _skip(reason: str, **extra) -> None:
		key = f"_skip_last_{reason}"
		now = time.monotonic()
		if now - getattr(manager, key, 0.0) < 30.0:
			return
		setattr(manager, key, now)
		manager._log_audit({"event": "drain_check_skip", "reason": reason, **extra})

	if manager.session_type != "orchestrator":
		return
	cooldown_remaining = 30.0 - (time.monotonic() - getattr(manager, "_last_restart_ts", 0.0))
	if cooldown_remaining > 0:
		_skip("cooldown", cooldown_remaining=round(cooldown_remaining, 1))
		return
	state = manager._state_machine.state
	if state not in (States.IDLE, States.TASK_RUNNING):
		_skip("state_not_idle", state=str(state))
		return
	if manager._handoff_in_progress or manager._auto_handoff_disabled():
		_skip("handoff_in_progress_or_disabled", in_progress=manager._handoff_in_progress)
		return
	tif = manager._tasks_in_flight_path
	if not tif.exists():
		_skip("no_tasks_in_flight_file")
		return
	try:
		tif_content = json.loads(tif.read_text("utf-8"))
	except Exception as e:
		_skip("tif_read_error", error=str(e))
		return

	tif_is_tombstone = (not tif_content)
	round_exists = manager._current_round_path.exists()
	if not (round_exists or tif_is_tombstone):
		_skip("no_current_round")
		return

	if not tif_is_tombstone:
		_skip("tasks_in_flight_nonempty", tasks=tif_content)
		return

	threshold = manager._config.get("handoff_primary_tokens", 80000)
	fill_tokens = 0
	try:
		agentflow_dir = manager._project_root / ".agentflow"
		sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
		cf = session_file(agentflow_dir, "context_fill.json", sid)
		if cf.exists():
			data = json.loads(cf.read_text("utf-8"))
			fill_tokens = data.get("fill_tokens", 0)
			ts = data.get("ts")
			if ts is not None and time.time() - ts > 60:
				_skip("fill_stale", ts_age=round(time.time() - ts, 1))
				return
	except Exception as e:
		manager._log_audit({"event": "drain_restart_fill_tokens_read_error", "error": str(e)})
	if fill_tokens < threshold:
		_skip("fill_tokens_below_threshold", fill_tokens=fill_tokens, threshold=threshold)
		return
	manager._log_audit({"event": "drain_restart_triggered", "fill_tokens": fill_tokens, "threshold": threshold})
	try:
		_write_merged_and_clear(manager)
	except Exception as e:
		manager._log_audit({"event": "drain_merged_write_error", "error": str(e)})
	manager._log_audit({"event": "session_restart", "session_id": os.environ.get("AGENTFLOW_SESSION_ID")})
	manager._state_machine.transition("restart_session")
