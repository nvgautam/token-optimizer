# /orchestrate — Agent Orchestration + Implementation

**Verbosity:** ≤3 sentences (~150 tokens) per orchestrator status message.

## Startup
Execute `commands/claude/orchestrator/startup.md` steps: Step 1 (Persona), Step 2 (Rate check), Step 2b (Index execution_plan.md only), Step 3 (Oracle gate on design_status.md UNRESOLVED items; stop if count > 0), Step 3b (Cache), Step 4 (Load state: state.json is advisory only, on resume derive next round from execution_plan.md Master Round Table for the first row whose tasks are all pending; read round table, identify pending tasks, state.json is not the sole authority for next_round), Step 4a (Startup reconciliation: if .agentflow/current_round.json exists, read its task_ids and check each against tasks.json. If any task_id has status 'complete', the file is stale — unlink current_round.json and tasks_in_flight.json, log 'startup_reconciliation_cleaned'. If all task_ids are still 'pending', trust the file and continue from that round), Step 4b (Select round: run `grep -m 1 '\[PENDING\]'` on execution_plan.md Master Round Table to find first pending round; announce "Picking up Round X: T-xxx"), and Step 5 (Load prior calibration from rate_calibration_claude.json).
For details, see `commands/claude/orchestrator/startup.md`.

**Rate-pacing & EWMA:** Spawn first agent alone. Track observed_costs via TOKENS: reports. Per-task cost: sample_count < 7 → 2500 (static default); sample_count ≥ 7 and cv < cv_threshold → mean; cv ≥ cv_threshold → p85. EWMA: load ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha from rate_calibration_claude.json at startup. Round-sizing heuristic: max_tasks_by_budget = floor(orchestrator_threshold_tokens / pct_cost); pause if effective_rate × remaining_minutes < 3 × pct_cost. Details in `commands/claude/orchestrator/rate_pacing.md`.

---

**See `commands/claude/orchestrator/decomposition.md` for decomposition details (lazy — stubs only).**

## Agent spawn
> **HARD RULE:** Orchestrate MUST NEVER implement tasks directly. Dispatch a worker agent. Write `.agentflow/current_round.json` BEFORE spawning any worker (MUST use the Write tool — never Bash). Drain watches for this file; if spawn fails before it's written, drain misfires.
**Pre-spawn (once before first agent):**
- Branch `main`, working tree clean. No GitHub remote → `gh repo create --source=. --remote=origin --push`.
- Stub every `owns` path (`raise NotImplementedError`). `.gitignore` absent → generate.
- Generate `.idx` in ~/.agentflow/cache/ for reads files ≥50 lines (using ast for Python files, grep H2/H3 for Markdown files). Pre-create branch: `git worktree add .claude/worktrees/<branch> -b <branch> main`.
- Capture worktree path: `git worktree list | grep <branch> | awk '{print $1}'` as `worktree_abs_path`.
- **Never** run `git checkout` in root — inspect via `git show` or `gh pr diff`.
**Build each agent prompt:**
1. `commands/claude/worker/system.md`
2. `commands/claude/worker/context_bundle.md` (include `worktree_abs_path` in the context bundle)
3. `commands/claude/worker/testing_guide.md`
4. Full task definitions (grep `^## Addendum: <task_id>` in execution_plan.md or idx)
5. Milestone architecture anchor section
6. Reads files: `.idx` exists → embed `### <file> — <name> (lines start-end)` via Read; else embed full file.
Close prompt: "End your final message with TOKENS: input=N output=N — nothing after that line."
- **Model selection:** Mechanical (lines ≤ 80 or test/fix/stub/lint/config) → `model: "haiku"`; Default → `model: "sonnet"`.
- **Scheduling:** Run `task_estimator` to estimate task cost (fallback 2500). Disjoint owns check: if tasks share an owns path, OWNS CONFLICT, move overlap to next round.
- **Execution:** Spawn worker with selected model and `worktree_abs_path`. Do not call `EnterWorktree`. Save `.agentflow/state.json`.

### Round Lifecycle & PTY Signals
First: run `Bash(echo $AGENTFLOW_SESSION_ID)` to capture the session ID into a variable (e.g. `SID`). Then write `.agentflow/current_round.json` BEFORE spawning any Agent (immediately before the Agent spawn call — drain must see it even if spawn fails) using the Write tool (never Bash for the write itself): `{"round_id": "str", "task_ids": ["str"], "estimated_lines_per_task": {}, "file_counts_per_task": {}, "session_id": "<captured SID>", "timestamp": "ISO8601"}`.
Worker lifecycles stdout signals:
- Before spawning: run `pty_signal.py task_start <task_id>` and print `AGENTFLOW_TASK_START:<task_id>`
- After worker completes: print `AGENTFLOW_TASK_COMPLETE:<task_id>`

---

## Review
**Pass 1 — Programmatic:**
```bash
git diff main...<branch> --name-only > /tmp/rf.txt && git diff main...<branch> > /tmp/rd.txt
grep -n "NotImplementedError" $(cat /tmp/rf.txt) | grep -v "stub\|test"
grep -n "shell=True" $(cat /tmp/rf.txt)
grep -n "except:" $(cat /tmp/rf.txt)
wc -l $(cat /tmp/rf.txt) | awk '$1 > 250 {print}'
grep -nE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}" $(cat /tmp/rf.txt)
```
CRITICAL: hardcoded secrets, signal injection. WARNING: bare except, size > 250 lines.
**Pass 2 — LLM Reviewer:** Select opposite tier: Haiku-implemented → Sonnet; Sonnet-implemented → Haiku. Embed `commands/claude/reviewer/code_review.md`, `security_review.md`, `test_review.md`, and diff (max 300 lines). Rework on CRITICAL.

---

## Human gate
```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
  Description: <brief description>
git diff main...<branch>
Worktree: <absolute path>
PR: <URL> (always push and show PR/new URL)
Reply: yes → merge | no [reason] → rework | skip → continue
```
PR creation fallback: always push branch, show direct PR URL on permission failure. Once user replies "yes", emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`
Never merge without explicit "yes".

---

## Merge
**REQUIRED:** run `python agentflow/tools/cleanup_tasks.py .` to update tasks.json.
Acquire `.agentflow/tasks.json.lock` (or state.json.lock or execution_plan.md.lock) via `fcntl.flock` before writing tasks.json, state.json, or execution_plan.md.
Then:
1. tasks.json completed tasks trimmed to `{"task_id": "T-NNN", "status": "complete"}`; archived to `.agentflow/tasks.archive.json`.
2. Milestone complete → mark COMPLETE, decompose next milestone lazily.
Do not manually edit task stubs or archive — always run cleanup_tasks.py.

**See `commands/claude/orchestrator/targeted_reads.md`, `verbosity.md`, and `telemetry.md`.**
