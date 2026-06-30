---
name: orchestrate
description: Runs the agent orchestrator to implement milestone tasks, manage worker agents, run code reviews, and execute merges.
---

# /orchestrate — Agent Orchestration + Implementation

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
For `design_status.md` and `execution_plan.md`: if `.idx` absent or stale, regenerate (H2/H3 headers, `## Header:start-end`).

### Step 3 — Oracle gate
Read `design_status.md` (use `.idx` if present). Any `| UNRESOLVED |` row → stop:
> "Design has unresolved items. Run `/oracle` to resolve them first."

### Step 4 — Load execution state
Read `execution_plan.md` (use `.idx`) and `tasks.json`. **No `architecture.md` or `CLAUDE.md` at startup.**

Check `.agentflow/state.json`. Present → report resumed state and ask "Continue?". Absent → identify first incomplete milestone. `/orchestrate debug` → reveal grouping plan and ask "Proceed?".

### Step 5 — Load prior calibration
Load `~/.agentflow/rate_calibration_gemini.json` (if absent and `~/.agentflow/rate_calibration.json` exists, load `~/.agentflow/rate_calibration.json` as a one-time compat fallback); init EWMA: `ewma_mean_tokens=2500, ewma_cv=0.0, sample_count=0, ewma_alpha=0.3` if generic also absent.


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

Spawn one agent per group, `isolation: "worktree"`. Parallel only if no cross-dependencies and rate supports. Save `.agentflow/state.json` after each.

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

**Pass 2 — LLM (fresh haiku agent):**
Embed `commands/claude/reviewer/code_review.md`, `commands/claude/reviewer/security_review.md`, `commands/claude/reviewer/test_review.md`. Include pre-filter findings, changed files, diff (max 300 lines).

- `CRITICAL` → rework (one retry; escalate on second failure)
- `DRIFT` → surface at human gate; update `architecture.md` before merging if approved

---

## Human gate

```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
git diff main...<branch>
Worktree: <absolute path>
PR: <URL> (always push branch to remote and show PR URL, or PR creation link)
Reply: yes → merge | no [reason] → rework | skip → continue
```
Emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`

**Never merge without explicit "yes".**

---

## Merge

1. Replace in `tasks.json`: `{"task_id": "T-NNN", "status": "complete"}`
2. Append full definition to `.agentflow/tasks.archive.json`
3. Mark `MERGED` in `execution_plan.md`
4. Milestone complete → mark `COMPLETE`, decompose next milestone lazily
5. Save `.agentflow/state.json`
6. Emit: `HANDOFF RECOMMENDED: [task_id] merged — state saved, good stopping point before next round`

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
