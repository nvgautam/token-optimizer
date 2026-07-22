# /orchestrate — Agent Orchestration + Implementation

**Verbosity:** ≤3 sentences (~150 tokens) per orchestrator status message. Never narrate strategy: round-sizing rationale, calibration values, EWMA/cv, task-cost estimates, disjoint owns analysis — status is round+task only. **Exception: the Human gate block must be emitted in full — no lines may be omitted.**

## Startup
Execute `commands/claude/orchestrator/startup.md` steps: Step 1 (Persona), Step 2 (Rate check), Step 2b (Index execution_plan.md only), Step 3 (Oracle gate on design_status.md UNRESOLVED items; stop if count > 0), Step 3b (Cache), Step 4 (Load state: state.json is advisory only, on resume derive next round from execution_plan.md Master Round Table for the first row with at least one pending task; read round table, identify pending tasks, state.json is not the sole authority for next_round), Step 4a (Startup reconciliation: if .agentflow/current_round.json exists, read its task_ids and check each against tasks.json. If ALL task_ids are complete → stale, unlink current_round.json and tasks_in_flight.json, log 'startup_reconciliation_cleaned'. If SOME task_ids are complete and SOME are pending → filter to pending subset, log 'startup_mid_round_resumed', continue from that round. If all are pending → trust the file and continue), Step 4b (Select round: run `grep -m 1 '\[PENDING\]'` on execution_plan.md Master Round Table to find first pending round; announce "Picking up Round X: T-xxx"), and Step 5 (Load prior calibration from rate_calibration_claude.json).
For details, see `commands/claude/orchestrator/startup.md`.

**Rate-pacing & EWMA:** Spawn first agent alone. Track observed_costs via TOKENS: reports. Per-task cost: sample_count < 7 → 2500 (static default); sample_count ≥ 7 and cv < cv_threshold → mean; cv ≥ cv_threshold → p85. EWMA: load ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha from rate_calibration_claude.json at startup. Round-sizing heuristic: max_tasks_by_budget = floor(orchestrator_threshold_tokens / pct_cost); pause if effective_rate × remaining_minutes < 3 × pct_cost. Details in `commands/claude/orchestrator/rate_pacing.md`.

---

**See `commands/claude/orchestrator/decomposition.md` for decomposition details (lazy — stubs only).**

## Agent spawn
> **HARD RULE:** Orchestrator MUST NEVER write code, edit source files, or implement tasks. If you are writing code, STOP — spawn a worker agent instead. Violating this rule breaks the drain-restart chain.

### Round Lifecycle & PTY Signals
First: run `Bash(echo $AGENTFLOW_SESSION_ID)` to capture the session ID into a variable (e.g. `SID`). Before spawning any Agent, register the round via CLI — **NEVER use the Write tool for current_round.json**: `Bash: agentflow round start --task-ids T-NNN [T-MMM ...] --round-id <round_id> --sid $SID`. This atomically writes `current_round.json` and `tasks_in_flight.json` — drain sees it even if spawn fails. Schema:
```json
{
  "round_id": "string",
  "task_ids": ["string"],
  "estimated_lines_per_task": {"task_id": "int"},
  "file_counts_per_task": {"task_id": "int"},
  "session_id": "<captured SID>",
  "timestamp": "ISO8601"
}
```
Worker lifecycle stdout signals:
- Before spawning: print `AGENTFLOW_TASK_START:<task_id>`
- After worker completes: print `AGENTFLOW_TASK_COMPLETE:<task_id>`

**Pre-spawn (once before first agent):**
- Branch `main`, working tree clean. No GitHub remote → `gh repo create --source=. --remote=origin --push`.
- Stub every `owns` path (`raise NotImplementedError`). `.gitignore` absent → generate.
- Generate `.idx` in ~/.agentflow/cache/ for reads files ≥50 lines (using ast for Python files, grep H2/H3 for Markdown files). Pre-create branch: `git worktree add .claude/worktrees/<branch> -b <branch> main`.
- Capture worktree path: `git worktree list | grep <branch> | awk '{print $1}'` as `worktree_abs_path`.
- **Never** run `git checkout` in root — inspect via `git show` or `gh pr diff`.
**Context bundle delivery (ONLY permitted way to build agent prompt):**
Run `Bash: agentflow bundle <task_id> --agent-type <worker|reviewer|test>` — prints an output path. Pass that path string as the Agent `prompt` arg — nothing else. Do NOT inline skill content, task definitions, or file reads into the prompt. The bundle contains everything; the worker reads and deletes it on startup.

Close prompt: "End your final message with TOKENS: input=N output=N — nothing after that line."
- **Model selection:** Mechanical (lines ≤ 80 or test/fix/stub/lint/config) → `model: "haiku"`; Default → `model: "sonnet"`.
- **Scheduling:** Run `task_estimator` to estimate task cost (fallback 2500). Disjoint owns check: if tasks share an owns path, OWNS CONFLICT, move overlap to next round.
- **Execution:** Spawn worker with selected model and `worktree_abs_path`. Do not call `EnterWorktree`. Save `.agentflow/state.json`.

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
**Pass 2 — LLM Reviewer:** Select opposite tier: Haiku-implemented → Sonnet; Sonnet-implemented → Haiku. Embed `commands/claude/reviewer/code_review.md`, `security_review.md`, `test_review.md`, and diff (max 300 lines). **MANDATORY**: Invoke `/review` before opening a PR. Reviewer must return zero BLOCKERs. If BLOCKERs found → rework (one retry maximum), then ESCALATE if BLOCKERs persist.

---

## Human gate
```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
  Description: <brief description>
git diff main...<branch>
Worktree: <absolute path>
PR: <URL>  ← HARD RULE: emit even if URL was shown earlier; never omit
Reply: yes → merge | no [reason] → rework | skip → continue
```
PR creation fallback: always push branch, show direct PR URL on permission failure. Once user replies "yes", emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`
Never merge without explicit "yes".

**Post-merge conflict resolution:** After user replies "yes" and before final merge, fetch origin/main and merge into the PR branch. Auto-resolve additive conflicts — accept both sides (no content loss). On same-line conflicts, escalate to the user. Push resolved branch, then re-merge into main. OWNS conflict gate is intentionally preserved.

---

## Merge
**REQUIRED:** run `python agentflow/tools/cleanup_tasks.py .` to update tasks.json.
Acquire `.agentflow/tasks.json.lock` (or state.json.lock or execution_plan.md.lock) via `fcntl.flock` before writing tasks.json, state.json, or execution_plan.md.
Then:
1. tasks.json completed tasks trimmed to `{"task_id": "T-NNN", "status": "complete"}`; archived to `.agentflow/tasks.archive.json`.
2. Milestone complete → mark COMPLETE, decompose next milestone lazily.
Do not manually edit task stubs or archive — always run cleanup_tasks.py.

**See `commands/claude/orchestrator/targeted_reads.md`, `verbosity.md`, and `telemetry.md`.**
