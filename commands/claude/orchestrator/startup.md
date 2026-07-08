# Startup Steps

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

### Step 4 — Load execution state
**No `architecture.md` or `CLAUDE.md` at startup.**

`execution_plan.md` — use `.idx` to read only the "Master Round Table" section:
```bash
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
grep "^## Master Round Table" ~/.agentflow/cache/$HASH/index/execution_plan.md.idx
```
Then `Read(offset=<start>, limit=<end-start+1>)`.

`tasks.json` — extract pending entries only, never read full file:
```bash
python3 -c "import json; d=json.load(open('tasks.json')); [print(json.dumps(t)) for t in d['tasks'] if t['status']=='pending']"
```

Check `.agentflow/state.json`. Present → report resumed state and ask "Continue?". Absent → identify first incomplete milestone. `/orchestrate debug` → reveal grouping plan and ask "Proceed?".

### Step 4b — Select round
Read the round table for the active milestone in `execution_plan.md` and check task statuses in `tasks.json`. Identify the first round that contains PENDING tasks whose dependencies are fully satisfied (i.e. marked as MERGED or complete).
Announce: `Picking up Round X: T-xxx` (where `X` is the round identifier, e.g., `C`, and `T-xxx` represents the pending task IDs in that round).
Proceed directly to execute or decompose the round without prompting the user.

### Step 5 — Load prior calibration
Load `~/.agentflow/rate_calibration_claude.json` (if absent and `~/.agentflow/rate_calibration.json` exists, load `~/.agentflow/rate_calibration.json` as a one-time compat fallback); init EWMA: `ewma_mean_tokens=2500, ewma_cv=0.0, sample_count=0, ewma_alpha=0.3` if generic also absent.

Gate file: same staleness rule as Step 3.
