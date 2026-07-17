# /debug — AgentFlow Diagnostic Skill

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

## Phase 2: File State Audit

Read core state files for the matched symptom class.

**All classes — derive SID:**
```bash
SID=$(python3 -c "import json; print(json.load(open('.agentflow/current_round.json'))['session_id'])")
```

**Class A & C — in-flight state for the active session:**
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
If the PR was merged via GitHub UI rather than `gh pr merge`, the hook's
command-match pattern may not have fired.

---

## Phase 3: Signal Trace

Read the relevant log files per symptom class.

**Class A — PTY audit:**
```bash
grep 'drain_check_skip' .agentflow/pty_audit.jsonl | tail -20
```
Note the `reason` field: `tasks_in_flight_nonempty`, `fill_stale`, or other.

**Class B — Drain events:**
```bash
grep -E '"event":\s*"(hook_fired|pr_merge_direct|drain_done)"' .agentflow/hook_drain_debug.jsonl | tail -40
```
Confirm `hook_fired` exists for the merge timestamp. If absent, hook was not
triggered (hook registration issue, not a drain-logic bug).

**Class C — drain_done signal results:**
```bash
grep 'drain_done' .agentflow/hook_drain_debug.jsonl | tail -5
grep '<TASK_ID>' .agentflow/hook_drain_debug.jsonl
```
Inspect `signal_results` for expected task IDs. No entries for TASK_ID →
`task_done` was never emitted for that task.

**Class A — Cross-check git log** (when drain events look incomplete):
```bash
git log --oneline --after="<hook_timestamp>" --before="<hook_timestamp+5min>" -- .
```
Note: the `cmd` field in hook events is truncated to 80 chars — a single command
may have merged multiple PRs; only the first PR number may be visible.

---

## Phase 4: Root Cause Determination

Match evidence to known failure patterns:

**Pattern A — PTY stuck:**
`drain_check_skip` with reason `tasks_in_flight_nonempty` → task stuck in session.
git log merge count > hook `pr_merge_direct` count → hook regex caught only the
first PR in a multi-PR merge command. Fix: widen regex or split multi-PR commands.

**Pattern B — Drain missed:**
No `hook_fired` entry → hook not registered or wrong event type.
`hook_fired` present but no `drain_done` → drain was skipped (check
`pty_audit.jsonl` skip reason). PR merged via GitHub UI → hook command-match
pattern did not fire; check hook registration and event type.

**Pattern C — Split-brain:**
`tasks.json` complete but `tasks_in_flight.json` still lists task →
`task_done` was never signalled for the active session.
No task ID in `hook_drain_debug.jsonl` → worker closed task directly in
tasks.json without calling the task_done hook.
Fix: ensure worker calls task_done after confirming PR merge, not before.

---

## Phase 5: Report

**Output format:** Root cause + fix recommendation in ≤ 3 sentences, followed
by any open hypotheses labeled explicitly.

### Epistemic Discipline

When log evidence is incomplete (truncated `cmd` fields, missing entries, gaps
in timestamps), **state the gap explicitly** and propose a targeted read to
close it.

- Treat unverified inferences as **hypotheses** — label them: "Hypothesis: ..."
- High-confidence claims require a log citation (file + event timestamp)
- If evidence is absent: "No log entry found — cannot confirm. To close this
  gap, run: `<specific command>`"
- Do NOT fill an evidence gap with a conclusion stated as fact
