# /debug — AgentFlow Operator Triage

Structured, low-token protocol for diagnosing AgentFlow failures.
Invoke as a standalone skill: `/debug`. Do NOT nest inside oracle.
Evidence-first diagnostic protocol: collect observable signals → reason to anomaly → trace root cause → recommend fix.

---

## Phase 1: Collect Observable Signals

Gather evidence from all available sources without pre-classification.

**Derive SID from current_round.json:**
```bash
SID=$(python3 -c "
import json, sys
try:
    print(json.load(open('.agentflow/current_round.json'))['session_id'])
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr); sys.exit(1)
")
```

**Collect signals from all sources:**
- PTY audit: `grep 'drain_check_skip' .agentflow/pty_audit.jsonl | tail -20`
- Drain events: `grep -E '"event":\s*"(hook_fired|pr_merge_direct|drain_done)"' .agentflow/hook_drain_debug.jsonl | tail -20`
- In-flight state: `cat .agentflow/sessions/$SID/tasks_in_flight.json 2>/dev/null`
- Task completion: `python3 -c "import json; d=json.load(open('tasks.json')); print([t['task_id']+':'+t['status'] for t in d.get('tasks',[])])"`

---

## Phase 2: Analyze Signals to Identify Anomaly

Map observable evidence to patterns — reason forward, not backward from class.

**Drain blocked** (pty_audit has `drain_check_skip`):
- Reason `tasks_in_flight_nonempty` → PTY has unfinished task
- Reason `fill_stale` → stale context blocking handoff (novel mode, not pre-enumerated)
- Any other reason → document for investigation

**Hook/merge mismatch** (PR merge but no `drain_done`):
- No `hook_fired` for merge timestamp → hook not triggered
- `hook_fired` present but no `drain_done` → drain skipped (check pty_audit skip reason)

**Sync desync** (tasks.json complete but tasks_in_flight still lists task):
- `task_done` signal was never sent for active session

---

## Phase 3: Root Cause Determination

Match evidence to patterns and recommend fixes.

**PTY stuck** (drain_check_skip, reason `tasks_in_flight_nonempty`):
Task stuck in session. Check git log merge count vs. `pr_merge_direct` count in hook logs.
If merge count > hook count, PR regex caught only first of multi-PR merge.
Fix: split multi-PR commands or widen regex pattern.

**Fill_stale** (drain_check_skip, reason `fill_stale`):
Stale context from previous session blocking handoff.
Fix: clear context cache or implement context isolation between sessions.

**Drain missed** (no `hook_fired` or `hook_fired` but no `drain_done`):
Hook registration failure or wrong event type.
Fix: verify hook is registered and command-match pattern is correct.

**Split-brain** (tasks.json complete but tasks_in_flight lists same task):
`task_done` signal was never sent for active session.
Fix: ensure worker calls task_done hook after confirming PR merge.

---

## Phase 4: Report

**Output format:** Root cause + fix in ≤ 3 sentences. Label unconfirmed inferences explicitly.
State evidence gaps explicitly; propose targeted reads to close them.

---

## Appendix: Example Incidents (Historical A/B/C)

**Pattern A — PTY stuck:** Session never restarts despite tasks complete.
Observable: `drain_check_skip` reason `tasks_in_flight_nonempty`.

**Pattern B — Drain missed:** Merge happened but PTY did not drain.
Observable: `pr_merge_direct` but no `hook_fired` entry.

**Pattern C — Split-brain:** `tasks.json` complete, PTY thinks in-flight.
Observable: task complete in tasks.json but still in tasks_in_flight.json.
