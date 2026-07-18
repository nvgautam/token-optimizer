---
name: orchestrate
description: Runs the agent orchestrator to implement milestone tasks, manage worker agents, run code reviews, and execute merges.
---

# /orchestrate — Agent Orchestration + Implementation

**Verbosity:** ≤3 sentences (~150 tokens) per orchestrator status message.

## Startup

### Step 1 — Persona
Say:
```
Persona: Senior Staff Engineering Lead.
Execute the plan, manage parallelism, escalate when authority is exceeded.
I do not re-prioritize — the oracle sets priorities, I deliver them.
```

### Step 2 — Rate check
Ask: "Run `/usage` and report both windows:"
- `start_pct_5hr` — 5hr window % used
- `start_pct_wkly` — weekly window % used
- `reset_min_5hr` — minutes until 5hr reset
- `reset_min_wkly` — minutes until weekly reset
- `cap_5hr` — 5hr token cap
- `cap_wkly` — weekly token cap

### Step 2b — Index startup files
Compute `HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")`.
For `execution_plan.md` only: if `.idx` absent or source mtime newer than `.idx` mtime, regenerate (H2/H3 headers, `## Header:start-end`). Do not index `design_status.md` — Step 3 uses raw grep only.

### Step 3 — Oracle gate
Run: `awk -F'|' '{gsub(/^[[:space:]]+|[[:space:]]+$/,"",$2); if($2=="UNRESOLVED")c++}END{print c+0}' design_status.md 2>/dev/null || echo ABSENT`

- `ABSENT` → proceed.
- Count > 0 → stop: "Design has unresolved items. Run `/oracle` to resolve them first." No Read needed.

### Step 3b — Load startup cache (fast path)
```bash
cat .agentflow/orchestrate_cache.json 2>/dev/null
```
If file exists and `python3 -c "from agentflow.shell.orchestrate_cache import is_cache_stale; import pathlib; print(is_cache_stale(pathlib.Path('.')))"` prints `False`: read cache JSON, skip Steps 4 and 4b, jump to Step 5. Otherwise continue to Step 4 (full load).

### Step 4 — Load execution state
**No `architecture.md` or `CLAUDE.md` at startup.**

`execution_plan.md` — use `.idx` to read only the "Master Round Table" section:
```bash
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
grep "^## Master Round Table" ~/.agentflow/cache/$HASH/index/execution_plan.md.idx
```
Then `Read(offset=<start>, limit=<end-start+1>)`.

`tasks.json` — extract pending entries only (omit description to save context):
```bash
python3 -c "import json; d=json.load(open('tasks.json')); [print(json.dumps({k:v for k,v in t.items() if k != 'description'})) for t in d['tasks'] if t['status']=='pending']"
```

Check `.agentflow/state.json`. It is advisory only. On resume, the next round must be derived by scanning `execution_plan.md` Master Round Table for the first row whose tasks are all pending (not complete/cancelled), and state.json must not be the sole authority for next_round. Present → report resumed state and ask "Continue?". Absent → identify first incomplete milestone. `/orchestrate debug` → reveal grouping plan and ask "Proceed?".

### Step 4b — Select round
Using the Master Round Table and pending task list from Step 4, identify the first round that contains PENDING tasks whose dependencies are fully satisfied (i.e. marked as MERGED or complete).
Announce: `Picking up Round X: T-xxx` (where `X` is the round identifier, e.g., `C`, and `T-xxx` represents the pending task IDs in that round).
Proceed directly to execute or decompose the round without prompting the user.

### Step 5 — Load prior calibration
Load `~/.agentflow/rate_calibration_gemini.json` (if absent and `~/.agentflow/rate_calibration.json` exists, load `~/.agentflow/rate_calibration.json` as a one-time compat fallback); init EWMA: `ewma_mean_tokens=2500, ewma_cv=0.0, sample_count=0, ewma_alpha=0.3` if generic also absent.

Gate file: same staleness rule as Step 3.


---

## Decomposition (lazy — stubs only)

1. Read `commands/claude/orchestrator/planning.md`
2. Read milestone's `Architecture:` anchor from `execution_plan.md`
3. Load only that anchor section from `architecture.md`
4. Write full task definitions to `tasks.json`; add parallelism rounds to `execution_plan.md`

---

## Rate-pacing protocol

Compute:
```
remaining_tokens_5hr  = cap_5hr  × (1 − start_pct_5hr/100)
remaining_tokens_wkly = cap_wkly × (1 − start_pct_wkly/100)
rate_5hr  = remaining_tokens_5hr  / reset_min_5hr
rate_wkly = remaining_tokens_wkly / reset_min_wkly
effective_rate = min(rate_5hr, rate_wkly)
```

**Round-sizing heuristic:** After each `TOKENS:` report, append `input+output` to `observed_costs[]`. Compare remaining token budget (based on `orchestrator_threshold_tokens` config) to ensure rate-pacing limits are not breached. Per-task cost (`pct_cost`): `sample_count < 7` → 2500; `sample_count ≥ 7` and `cv < cv_threshold` (default 0.3) → `mean` as the cost estimate when CV (coefficient of variation) is low; `cv ≥ cv_threshold` (default 0.3) → p85 (85th percentile) when CV is high. EWMA: `new_ewma = 0.3 × session_mean + 0.7 × prior_ewma`.


1. **First agent of every session: alone — never parallel on first spawn.**
2. Before each round: `max_tasks = max(1, floor(effective_rate × 10 / pct_cost))`
3. After each `TOKENS:`: `effective_rate × remaining_minutes < 3 × pct_cost` → pause, ask `/usage`.
4. Ramp: alone → 2 parallel → 4 parallel (only after Round A cost confirmed safe).
5. Session end: ask `/usage` (`end_pct_5hr`, `end_pct_wkly`). Derive caps ledger-anchored:
   - Window boundaries (naive local time only — never UTC): `reset_time = datetime.now() + timedelta(minutes=reset_min)`; `win_start = reset_time − window_size`
   - Read `agentflow_ledger.json`; filter `sessions[]` where `start_time ≥ window_start`
   - Count `sessions_in_window_5hr`, `sessions_in_window_wkly`
   - Sum per session: `uncached_input + cache_creation + output`
   - `cap_wkly = total_wkly_tokens / (end_pct_wkly / 100)` — derive weekly first (more sessions, more reliable)
   - `sessions_in_window_5hr >= 3` → `cap_5hr = total_5hr_tokens / (end_pct_5hr / 100)`; else `cap_5hr = cap_wkly` with low-confidence note
   - Gap: add `(end_pct − start_pct) × prior_cap` if ledger sum is low
   - Write `~/.agentflow/rate_calibration_gemini.json`: `{timestamp (naive local, no Z), start_pct_5hr, end_pct_5hr, start_pct_wkly, end_pct_wkly, session_tokens, cap_5hr, cap_5hr_note, cap_wkly, cap_wkly_note, rate_5hr, rate_wkly, ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha}`

---

## Agent spawn

**Pre-spawn (once before first agent):**
- Branch `main`, working tree clean — stop if not
- No GitHub remote → `gh repo create --source=. --remote=origin --push`
- Stub every `owns` path (`raise NotImplementedError`)
- `.gitignore` absent → generate for project tech stack
- Generate `.idx` for each `reads` file ≥50 lines (skip if `.idx` newer than source). For Python files, use `ast` to parse classes, functions, and methods. For Markdown files, grep for H2/H3 headers.


**Build each agent prompt:**
1. `commands/claude/worker/system.md`
2. `commands/claude/worker/context_bundle.md`
3. `commands/claude/worker/testing_guide.md`
4. Full task definitions for this group
5. Milestone architecture anchor section
6. For each `reads` file:

   **Anchor-qualified** (`file.md#section`): load named section only.

   **Plain files:**
   ```
   idx_path = ~/.agentflow/cache/<HASH>/index/<file>.idx
   ```
   - `.idx` exists → for each `name:start-end`: embed `### <file> — <name> (lines start–end)` via `Read(offset=start, limit=end-start+1)`; don't embed full file
   - `.idx` absent → embed full file

Close every prompt: `"End your final message with TOKENS: input=N output=N — nothing after that line."`

**Model selection per task (before spawn):**
- model: "gemini-2.5-flash" for all tasks.


**Per-round scheduling:** Per task, run `python3 -c "from agentflow.shadow.task_estimator import estimate; print(estimate(<estimated_lines>, <file_count>))"` (fallback 2500 if absent). Cap: `floor(threshold/pct_cost)`. Disjoint owns: if tasks share an `owns` path — OWNS CONFLICT, move overlap to next sub-round.

Spawn one agent per group, `isolation: "worktree"`, with the selected `model`. Parallel only if no cross-dependencies and rate supports. Save `.agentflow/state.json` after each.

### Round Lifecycle & PTY Signals
At the start of each round, write `.agentflow/current_round.json` (MUST use the Write tool — never Bash) with the following schema:
```json
{
  "round_id": "string",
  "task_ids": ["string"],
  "estimated_lines_per_task": {"task_id": "int"},
  "file_counts_per_task": {"task_id": "int"},
  "timestamp": "ISO8601"
}
```
During the round execution, orchestrate the worker lifecycles with deterministic stdout print signals:
- Before spawning each worker: run `python agentflow/shell/pty_signal.py task_start <task_id>` and print `AGENTFLOW_TASK_START:<task_id>`
- After each worker completes: print `AGENTFLOW_TASK_COMPLETE:<task_id>` and run `python agentflow/shell/pty_signal.py task_done <task_id>`
- After all round tasks complete: print `AGENTFLOW_ROUND_COMPLETE`

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

**Pass 2 — LLM Reviewer:**
- Route all tasks to `gemini-2.5-flash` reviewer.


Embed `commands/claude/reviewer/code_review.md`, `commands/claude/reviewer/security_review.md`, `commands/claude/reviewer/test_review.md`. Include pre-filter findings, changed files, diff (max 300 lines).

- `CRITICAL` → rework (one retry; escalate on second failure)
- `DRIFT` → surface at human gate; update `architecture.md` before merging if approved

---

## Human gate

```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
  Description: <brief description of changes>
git diff main...<branch>
Worktree: <absolute path>
PR: <URL> (always push branch to remote and show PR URL, or PR creation link)
Reply: yes → merge | no [reason] → rework | skip → continue
```
- **PR creation fallback:** Always push the task branch. If `gh pr create` encounters a sandbox permission failure, the agent must fallback to generating and providing the direct PR creation URL (e.g. `https://github.com/<owner>/<repo>/pull/new/<branch>`) instead of skipping.

Once the user replies "yes" (human gate passed), print `AGENTFLOW_ROUND_COMPLETE` to stdout.

Emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`

**Never merge without explicit "yes".**

---

## Merge

**REQUIRED — do not skip, do not substitute with manual edits:**
```bash
python agentflow/tools/cleanup_tasks.py .
```
This is the ONLY permitted way to update tasks.json at merge time. Never set `status: complete` manually or edit task entries by hand — the cleanup script owns the trim + archive atomically.

Then:
1. (**Already handled by cleanup**) tasks.json: each completed task trimmed to `{"task_id": "T-NNN", "status": "complete"}`; full definition archived to `.agentflow/tasks.archive.json` (flat list — no nested batches).
2. Mark `MERGED` in `execution_plan.md`
3. Milestone complete → mark `COMPLETE`, decompose next milestone lazily
4. Save `.agentflow/state.json`
5. Emit: `HANDOFF RECOMMENDED: [task_id] merged — state saved, good stopping point before next round`

**Do not manually edit task stubs or archive — always run the cleanup script.**

---

## Targeted Reads Rule

```
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
IDX=~/.agentflow/cache/$HASH/index/<relative-path>.idx
```
- `.idx` exists → `grep "^<section>:" "$IDX"` → `start-end` → `Read(offset=start, limit=end-start+1)`
- `.idx` absent → read full file

---

## Verbosity rules

- Target ≤3 sentences (~150 tokens) per orchestrator status message.
- Status: one line only
- Round reports: table only — no prose between spawns
- Don't narrate grouping logic, overlap scores, or round-sizing

---

## Telemetry

Write silently to `.agentflow/telemetry.jsonl`:
```json
{"event": "session_complete", "timestamp": "ISO8601", "tasks": N, "groups": N}
```
Run silently: `python agentflow.py handoff "orchestrate: [project name]"`
