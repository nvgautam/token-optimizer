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
- `reset_min_5hr` — minutes until 5hr window resets
- `reset_min_wkly` — minutes until weekly window resets
- `cap_5hr` — total tokens in your 5hr tier (e.g. 1000000; PTY auto-detects in v2)
- `cap_wkly` — total tokens in your weekly tier (e.g. 5000000; PTY auto-detects in v2)

### Step 2b — Index startup files
Before reading startup files, generate or refresh their `.idx` if absent or stale:
```
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
```
For `design_status.md` and `execution_plan.md`: if `~/.agentflow/cache/<HASH>/index/<file>.idx` is absent OR older than the source file, regenerate it. Same format as pre-spawn: Markdown H2/H3 headers, `## Header:start-end`, one per line.

### Step 3 — Oracle gate
Read `design_status.md` (use `.idx` if present — see Targeted Reads Rule below). If any row contains `| UNRESOLVED |`, stop:
> "Design has unresolved items. Run `/oracle` to resolve them first."

### Step 4 — Load execution state
Read `execution_plan.md` (use `.idx` if present — see Targeted Reads Rule below) and `tasks.json`. **Do not read `architecture.md` or `CLAUDE.md` at startup.**

Check `.agentflow/state.json`. If present, report resumed state (milestone, complete/in-progress/pending task_ids) and ask "Continue?". Otherwise identify the first incomplete milestone and report it. If invoked as `/orchestrate debug`, reveal task grouping plan and ask "Proceed?" before continuing.

### Step 5 — Load prior calibration
Load `~/.agentflow/rate_calibration.json` if present; init EWMA state: `ewma_mean_tokens`, `ewma_cv`, `sample_count`, `ewma_alpha` (defaults: 2500, 0.0, 0, 0.3 if absent).

---

## Decomposition (lazy — only when milestone tasks are stubs in `tasks.json`)

1. Read `commands/orchestrator/planning.md`
2. Read the milestone's `Architecture:` anchor from `execution_plan.md`
3. Load **only that anchor section** from `architecture.md` — never the full document
4. Write full task definitions into `tasks.json`; add parallelism rounds to `execution_plan.md`

---

## Rate-pacing protocol

Compute on receipt of startup data:
  remaining_tokens_5hr  = cap_5hr  × (1 − start_pct_5hr/100)
  remaining_tokens_wkly = cap_wkly × (1 − start_pct_wkly/100)
  rate_5hr  = remaining_tokens_5hr  / reset_min_5hr
  rate_wkly = remaining_tokens_wkly / reset_min_wkly
  effective_rate = min(rate_5hr, rate_wkly)

**Round-sizing heuristic:** After each `TOKENS:` report, append `input+output` to `observed_costs[]`; compute `mean`, `stddev`, `cv = stddev/mean`. Per-task cost (`pct_cost`): `sample_count < 7` → `orchestrator_threshold_tokens` (static 2500); `sample_count ≥ 7` and `cv < cv_threshold` (`shell.cv_threshold`, default 0.3) → `mean`; `cv ≥ cv_threshold` → `p85` (85th-percentile of `observed_costs`). EWMA: `new_ewma = ewma_alpha × session_mean + (1−ewma_alpha) × prior_ewma`, α = 0.3.
1. **First agent of every session: spawn alone — never parallel on the first spawn.**
2. Before each round: `max_tasks = max(1, floor(effective_rate × 10 / pct_cost))` (10 = default round minutes; `pct_cost` from round-sizing heuristic above)
3. After each `TOKENS:` report: if `effective_rate × remaining_minutes < 3 × pct_cost`, pause and ask user to run `/usage` to refresh.
4. Ramp: first agent alone → 2 parallel (if rate supports) → 4 parallel (only after Round A cost confirmed safe).
5. At session end: ask user to run `/usage` (report `end_pct_5hr`, `end_pct_wkly`). Derive caps ledger-anchored:
   - Window boundaries use naive local time only: `reset_time_5hr = datetime.now() + timedelta(minutes=reset_min_5hr)`; `win_5hr = reset_time_5hr − 5h`. Same pattern for weekly. Never use UTC or timezone-aware datetimes — ledger `start_time` values are naive local; mixing UTC with naive causes sessions to be excluded from the filter.
   - Read `agentflow_ledger.json`; filter `sessions[]` where `start_time ≥ window_start` (naive local comparison)
   - Count `sessions_in_window_5hr` and `sessions_in_window_wkly` (number of sessions passing the filter)
   - Sum billable per session: `uncached_input + cache_creation + output`
   - `cap_wkly = total_wkly_tokens / (end_pct_wkly / 100)` (derive weekly cap first — it has more sessions and is more reliable)
   - If `sessions_in_window_5hr >= 3`: `cap_5hr = total_5hr_tokens / (end_pct_5hr / 100)`; else: `cap_5hr = cap_wkly`; note: `cap_5hr_note = 'low-confidence — fewer than 3 sessions in window; using cap_wkly as proxy'`
   - Gap: current session not yet in ledger — add `(end_pct − start_pct) × prior_cap_estimate` to totals if ledger sum is visibly low
   - Write `~/.agentflow/rate_calibration.json`: `{timestamp: datetime.now().isoformat(), start_pct_5hr, end_pct_5hr, start_pct_wkly, end_pct_wkly, session_tokens, cap_5hr, cap_5hr_note (if low-confidence), cap_wkly, cap_wkly_note, rate_5hr, rate_wkly, ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha}` — `timestamp` must be naive local (no 'Z' suffix)

---

## Agent spawn

**Pre-spawn checks (run once before the first agent):**
- Branch must be `main` and working tree clean — stop if not
- If no GitHub remote: `gh repo create --source=. --remote=origin --push`
- Write a stub file for every `owns` path across all tasks (interface stubs with `raise NotImplementedError`)
- If `.gitignore` absent: generate an appropriate one for the project's tech stack and write it
- Generate `.idx` for each file in the round's `reads` lists with ≥ 50 lines: write to `~/.agentflow/cache/<sha256(cwd)>/index/<path>.idx`; one symbol per line as `name:start-end`; Python: ast functions, classes, class methods (`ClassName.method:start-end`); Markdown: H2/H3 headers (`## Header:start-end`); skip if `.idx` newer than source

**Build each agent prompt** — read and embed in order:
1. `commands/worker/system.md` — persona and no-re-read rule
2. `commands/worker/context_bundle.md` — bundle format
3. `commands/worker/testing_guide.md` — TDD rules
4. Full task definitions for this group (from `tasks.json`)
5. The milestone's architecture anchor section (already loaded in Decomposition step)
6. For each file in the group's `reads` list, embed its content using targeted reads where available:

   **Anchor-qualified reads** (e.g. `architecture.md#symbol-indexer`): use section-only loading as before — load only the named anchor section. Skip the .idx logic for these.

   **Plain file reads** (no `#anchor` suffix):
   ```
   HASH = sha256(cwd)
   idx_path = ~/.agentflow/cache/<HASH>/index/<file-path>.idx
   ```
   - If `idx_path` exists:
     1. Read the `.idx` file — each line is `name:start-end`
     2. For each symbol entry, embed a labelled excerpt:
        ```
        ### <file-path> — <name> (lines <start>–<end>)
        <Read file-path offset=start limit=(end-start+1)>
        ```
     3. Emit all excerpts in order; do **not** embed the full file
   - If `idx_path` is absent (file < 50 lines or index not yet generated):
     - Fall back: embed the full file contents (current behaviour)

Close every spawn prompt with:
> "End your final message with `TOKENS: input=N output=N` — nothing after that line."

Spawn one agent per group with `isolation: "worktree"`. Run groups with no cross-dependencies in parallel (subject to rate-pacing). Save `.agentflow/state.json` after each agent completes.

---

## Review

**Pass 1 — Programmatic (bash, no LLM):**
```bash
git diff main...<branch> --name-only > /tmp/rf.txt && git diff main...<branch> > /tmp/rd.txt
grep -n "NotImplementedError" $(cat /tmp/rf.txt) | grep -v "stub\|test"
grep -n "shell=True" $(cat /tmp/rf.txt)
grep -n "except:" $(cat /tmp/rf.txt)
wc -l $(cat /tmp/rf.txt) | awk '$1 > 250 {print}'
grep -nE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}" $(cat /tmp/rf.txt)
```
CRITICAL: hardcoded secrets, signal injection. WARNING: bare except, file size > 250 lines.

**Pass 2 — LLM review (fresh haiku agent):**
Read and embed `commands/reviewer/code_review.md`, `commands/reviewer/security_review.md`, `commands/reviewer/test_review.md` into the review agent prompt. Include pre-filter findings, changed files list, and diff (max 300 lines — keep security-relevant sections if truncating).

- `CRITICAL` → rework (one retry; escalate to user on second failure)
- `DRIFT` → surface at human gate; update `architecture.md` before merging if approved

---

## Human gate

```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
git diff main...<branch>
Worktree: <absolute path>
PR: <URL>
Reply: yes → merge | no [reason] → rework | skip → continue
```
Emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`

**Never merge without explicit "yes".**

---

## Merge

1. Replace merged task in `tasks.json` with slim stub: `{"task_id": "T-NNN", "status": "complete"}`
2. Append full definition to `.agentflow/tasks.archive.json`
3. Mark `MERGED` in `execution_plan.md`
4. If milestone complete: mark `COMPLETE`, decompose next milestone lazily, report to user
5. Save `.agentflow/state.json`
6. Emit: `HANDOFF RECOMMENDED: [task_id] merged — state saved, good stopping point before next round`

---

## Targeted Reads Rule

Before reading any file (other than agent-prompt embeds which are read in full), check for a `.idx`:
```
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
IDX=~/.agentflow/cache/$HASH/index/<relative-path>.idx
```
- If `.idx` exists: `grep "^<section>:" "$IDX"` → `section:start-end` → `Read(offset=start, limit=end-start+1)`
- If absent (file < 50 lines or not yet indexed): read the full file without `offset`/`limit`

---

## Verbosity rules

- Status updates: one line only
- Round reports: table format only — no prose between agent spawns
- Do not narrate grouping logic, overlap scores, or round-sizing calculations

---

## Telemetry

After all tasks complete, write silently to `.agentflow/telemetry.jsonl`:
```json
{"event": "session_complete", "timestamp": "ISO8601", "tasks": N, "groups": N}
```
Run silently: `python agentflow.py handoff "orchestrate: [project name]"`
