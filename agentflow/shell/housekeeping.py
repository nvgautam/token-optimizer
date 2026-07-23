"""Startup housekeeping — round status auto-update when all tasks complete."""
from __future__ import annotations
import fcntl
import json
import os
import re
import tempfile
from pathlib import Path
from agentflow.indexer.index_manager import update_index


def parse_round_table(content: str) -> list[dict]:
	"""Parse execution_plan.md and extract round information.

	Returns a list of dicts with keys: round_id, task_ids, line_number
	"""
	rounds = []
	lines = content.splitlines()
	in_master_table = "## Master Round Table" not in content

	for i, line in enumerate(lines):
		if "## Master Round Table" in line:
			in_master_table = True
			continue
		if not in_master_table:
			continue
		if not line.startswith("|"):
			continue
		inner = line.strip().strip("|")
		parts = [p.strip() for p in inner.split("|")]
		if not parts or len(parts) < 2:
			continue
		first_col = parts[0]

		# Skip headers and separators
		if re.match(r"^(-+|Round|Task)$", first_col, re.IGNORECASE):
			continue
		if re.match(r"^T-", first_col):  # Skip task rows
			continue

		# This is a round row
		round_id = first_col
		tasks_str = parts[1] if len(parts) > 1 else ""
		cleaned = re.sub(r"\(.*?\)", "", tasks_str)
		task_ids = re.findall(r"\bT-\d+[a-zA-Z]?\b", cleaned)

		if task_ids:
			rounds.append({"round_id": round_id, "task_ids": task_ids, "line_number": i})

	return rounds


def get_tasks_by_id(project_root: Path) -> dict[str, str]:
	"""Load tasks.json and return dict mapping task_id -> status."""
	tasks_path = project_root / "tasks.json"
	if not tasks_path.exists():
		return {}

	try:
		data = json.loads(tasks_path.read_text(encoding="utf-8"))
		return {t["task_id"]: t["status"] for t in data.get("tasks", [])}
	except Exception:
		return {}


def is_round_complete(task_ids: list[str], tasks_by_id: dict[str, str]) -> bool:
	"""Check if all tasks in a round are marked complete."""
	for tid in task_ids:
		if tid not in tasks_by_id or tasks_by_id[tid] != "complete":
			return False
	return True


def run_startup_housekeeping(manager) -> None:
	"""Check round table on startup and mark rounds [MERGED] if all tasks complete.

	Scans from top of execution_plan.md, marks complete rounds [MERGED],
	and halts at the first pending round.
	"""
	ep = manager._project_root / "execution_plan.md"
	if not ep.exists():
		return

	try:
		content = ep.read_text(encoding="utf-8")
	except Exception as e:
		manager._log_audit({"event": "housekeeping_read_error", "error": str(e)})
		return

	rounds = parse_round_table(content)
	if not rounds:
		return

	tasks_by_id = get_tasks_by_id(manager._project_root)
	if not tasks_by_id:
		return

	lines = content.splitlines(keepends=True)
	changed = False

	for round_info in rounds:
		line_idx = round_info["line_number"]
		if line_idx < len(lines):
			parts = lines[line_idx].split("|")
			round_col = parts[1] if len(parts) > 1 else ""
			if "MERGED" in lines[line_idx] and "[PENDING]" not in round_col:
				continue

		if not is_round_complete(round_info["task_ids"], tasks_by_id):
			# Halt at first pending round
			break

		# All tasks complete — mark round as [MERGED]
		if line_idx < len(lines):
			line = lines[line_idx]
			parts = line.split("|")
			if len(parts) > 1 and "[PENDING]" in parts[1]:
				parts[1] = parts[1].replace("[PENDING]", "[MERGED]")
				lines[line_idx] = "|".join(parts)
				changed = True
			elif "MERGED" not in line:
				# Append — MERGED to the line
				lines[line_idx] = line.rstrip("\n").rstrip() + " — MERGED\n"
				changed = True

			if changed:
				manager._log_audit(
					{
						"event": "housekeeping_round_merged",
						"round_id": round_info["round_id"],
						"task_ids": round_info["task_ids"],
					}
				)

	if not changed:
		return

	# Write back with lock
	lock = manager._project_root / "execution_plan.md.lock"
	try:
		with open(lock, "w", encoding="utf-8") as lf:
			fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
			# Re-read to avoid race; re-parse and re-apply changes
			content = ep.read_text(encoding="utf-8")
			lines = content.splitlines(keepends=True)

			for round_info in rounds:
				line_idx = round_info["line_number"]
				if line_idx < len(lines):
					parts = lines[line_idx].split("|")
					round_col = parts[1] if len(parts) > 1 else ""
					if "MERGED" in lines[line_idx] and "[PENDING]" not in round_col:
						continue
				if not is_round_complete(round_info["task_ids"], tasks_by_id):
					break
				if line_idx < len(lines):
					line = lines[line_idx]
					parts = line.split("|")
					if len(parts) > 1 and "[PENDING]" in parts[1]:
						parts[1] = parts[1].replace("[PENDING]", "[MERGED]")
						lines[line_idx] = "|".join(parts)
					elif "MERGED" not in line:
						lines[line_idx] = line.rstrip("\n").rstrip() + " — MERGED\n"

			final_content = "".join(lines)
			with tempfile.NamedTemporaryFile(
				mode="w", dir=ep.parent, delete=False, suffix=".tmp", encoding="utf-8"
			) as t:
				t.write(final_content)
				tmp = t.name
			os.replace(tmp, ep)
			manager._log_audit({"event": "housekeeping_execution_plan_written"})
			update_index(manager._project_root, ep, final_content)
	except Exception as e:
		manager._log_audit({"event": "housekeeping_write_error", "error": str(e)})
