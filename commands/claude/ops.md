# /debug — AgentFlow Operator Triage

Structured, low-token protocol for diagnosing AgentFlow failures.
Invoke as a standalone skill: `/debug`. Do NOT nest inside oracle.

---

## Phase 1: Triage

Identify which symptom class applies (ask user or infer from context):

| Code | Symptom |
|------|---------|
| A | PTY stuck — session never restarts despite tasks complete |
| B | Drain missed — merge happened but PTY did not drain |
| C | Split-brain — `tasks.json` says complete, PTY thinks in-flight |

Load only the files relevant to the matched class. Do not pre-read everything.

---

## Phase 2: Evidence Inventory

Signal files for this project:

| File | Contents |
|------|---------|
| `.agentflow/hook_drain_debug.jsonl` | Post-tool use hook logs; every entry includes `sid` |
| `.agentflow/pty_audit.jsonl` | PTY state transitions, handoff status, token evaluations, cleanup events |
| `.agentflow/current_round.json` | Active session ID and round metadata |

Session-start record schema (first entry per session in hook_drain_debug.jsonl):
```json
{"sid": "<uuid>", "session_type": "orchestrator|oracle|worker|reviewer", "task_ids": ["T-NNN"], "ts": <ts>}
```

Key PTY audit events: `session_start_header`, `session_type_transition`, `trigger_handoff`,
`drain_check_skip`, `reset_ansi_write_error`.

Filter all logs for a session:
```bash
agentflow logs --session <SID>
```

---

## Phase 3: Session Context

Derive SID and read in-flight state for the matched class.

**All classes — derive SID from current_round.json:**
```bash
SID=$(python3 -c "
import json, sys
try:
    print(json.load(open('.agentflow/current_round.json'))['session_id'])
except Exception as e:
    print(f'ERROR: {e} — no active round; find SID manually: ls .agentflow/sessions/', file=sys.stderr)
    sys.exit(1)
")
```

**Class A & C — in-flight state for active session:**
```bash
cat .agentflow/sessions/$SID/tasks_in_flight.json
```

**Class C — task completion status:**
```bash
python3 -c "import json; d=json.load(open('tasks.json')); [print(t['task_id'], t['status']) for t in d.get('tasks',[])]"
```

**Class B — verify merge path:**
```bash
gh pr view <PR_NUMBER> --json mergedAt,mergedBy
```
If merged via GitHub UI rather than `gh pr merge`, the hook's command-match pattern may not have fired.

---

## Phase 4: Signal Trace

Read log files per symptom class.

**Class A — PTY audit:**
```bash
grep 'drain_check_skip' .agentflow/pty_audit.jsonl | tail -20
```
Note the `reason` field: `tasks_in_flight_nonempty`, `fill_stale`, or other.

**Class B — Drain events:**
```bash
grep -E '"event":\s*"(hook_fired|pr_merge_direct|drain_done)"' .agentflow/hook_drain_debug.jsonl | tail -40
```
Confirm `hook_fired` exists for the merge timestamp. If absent, hook was not triggered.

**Class C — drain_done signal results:**
```bash
grep 'drain_done' .agentflow/hook_drain_debug.jsonl | tail -5
grep '<TASK_ID>' .agentflow/hook_drain_debug.jsonl
```
Inspect `signal_results` for expected task IDs.

**Class A — Cross-check git log** (when drain events look incomplete):
```bash
git log --oneline --after="<hook_timestamp>" --before="<hook_timestamp+5min>" -- .
```
Note: the `cmd` field in hook events is truncated to 80 chars — a single command may have
merged multiple PRs; only the first PR number may be visible.

---

## Phase 5: Root Cause Determination

Match evidence to known failure patterns.

**Pattern A — PTY stuck:**
`drain_check_skip` with reason `tasks_in_flight_nonempty` → task stuck in session.
git log merge count > hook `pr_merge_direct` count → hook regex caught only the first PR
in a multi-PR merge command. Fix: widen regex or split multi-PR commands.

**Pattern B — Drain missed:**
No `hook_fired` entry → hook not registered or wrong event type.
`hook_fired` present but no `drain_done` → drain was skipped (check `pty_audit.jsonl` skip reason).
PR merged via GitHub UI → hook command-match pattern did not fire; check hook registration.

**Pattern C — Split-brain:**
`tasks.json` complete but `tasks_in_flight.json` still lists task → `task_done` was never
signalled for the active session.
No task ID in `hook_drain_debug.jsonl` → worker closed task directly in tasks.json without
calling the task_done hook. Fix: ensure worker calls task_done after confirming PR merge.

---

## Phase 6: Report

**Output format:** Root cause + fix recommendation in ≤ 3 sentences, followed by any open
hypotheses labeled explicitly.

### Epistemic Discipline

When log evidence is incomplete (truncated `cmd` fields, missing entries, timestamp gaps),
**state the gap explicitly** and propose a targeted read to close it.

- Treat unverified inferences as **hypotheses** — label them: "Hypothesis: ..."
- High-confidence claims require a log citation (file + event timestamp)
- If evidence is absent: "No log entry found — cannot confirm. To close this gap,
  run: `<specific command>`"
- Do NOT fill an evidence gap with a conclusion stated as fact
