# /debug — AgentFlow Diagnostic Skill

Structured, low-token protocol for diagnosing AgentFlow failures.
Invoke as a standalone skill: `/debug`. Do NOT nest inside oracle.

---

## Intake

Ask the user (or infer from context) which symptom class applies:

| Code | Symptom |
|------|---------|
| A | PTY stuck — session never restarts despite tasks complete |
| B | Drain missed — merge happened but PTY did not drain |
| C | Split-brain — `tasks.json` says complete, PTY thinks in-flight |

Load ONLY the files listed under the matching class. Do not pre-read all logs.

---

## Symptom Class A — PTY Stuck

**Step 1 — pty_audit.jsonl**
```bash
grep 'drain_check_skip' .agentflow/pty_audit.jsonl | tail -20
```
Note the `reason` field: `tasks_in_flight_nonempty`, `fill_stale`, or other.

**Step 2 — tasks_in_flight.json**
Identify the active session SID from `.agentflow/state.json` (`active_session_id`).
```bash
cat .agentflow/sessions/<SID>/tasks_in_flight.json
```
List which task IDs are stuck in-flight.

**Step 3 — hook_drain_debug.jsonl**
```bash
grep -E '"event":\s*"(hook_fired|pr_merge_direct)"' .agentflow/hook_drain_debug.jsonl | tail -30
```
Note: the `cmd` field is **truncated to 80 chars**. A single command may have merged
multiple PRs; only the first PR number may be visible in the truncated field.

**Step 4 — Cross-check with git log**
```bash
git log --oneline --after="<hook_timestamp>" --before="<hook_timestamp+5min>" -- .
```
Count how many merge commits appear vs. how many `pr_merge_direct` events the hook
emitted. If git shows more merges than hook events → the hook's regex caught only
the first PR in a multi-PR merge command.

**Root cause pattern:** If git log merge count > `pr_merge_direct` event count,
the drain was never triggered for the additional PRs. Fix: widen the regex or
split multi-PR commands before invoking.

---

## Symptom Class B — Drain Missed

**Step 1 — hook_drain_debug.jsonl**
```bash
grep -E '"event":\s*"(hook_fired|pr_merge_direct|drain_done)"' .agentflow/hook_drain_debug.jsonl | tail -40
```
Confirm whether `hook_fired` exists for the merge timestamp. If absent, the hook
was not triggered at all (hook registration issue, not a drain-logic bug).

**Step 2 — pty_audit.jsonl**
```bash
grep 'drain' .agentflow/pty_audit.jsonl | tail -20
```
Check whether drain was attempted but skipped (skip reason recorded) or never
attempted (no entry near the merge timestamp).

**Step 3 — Verify merge path**
```bash
gh pr view <PR_NUMBER> --json mergedAt,mergedBy
```
If the PR was merged via `gh pr view` / GitHub UI rather than `gh pr merge`, the
hook's command-match pattern may not have fired.

**Root cause pattern:** No `hook_fired` entry → hook not registered or wrong
event type. `hook_fired` present but no `drain_done` → drain was skipped (see
`pty_audit.jsonl` skip reason).

---

## Symptom Class C — Split-Brain

**Step 1 — Compare task status**
```bash
# tasks.json reported status
python3 -c "import json; d=json.load(open('tasks.json')); [print(t['task_id'], t['status']) for t in d.get('tasks',[])]"

# In-flight state for active session
SID=$(python3 -c "import json; print(json.load(open('.agentflow/state.json'))['active_session_id'])")
cat .agentflow/sessions/$SID/tasks_in_flight.json
```
Identify tasks where `tasks.json` is `complete` but `tasks_in_flight.json` still
lists them as in-flight.

**Step 2 — Check drain_done signal_results**
```bash
grep 'drain_done' .agentflow/hook_drain_debug.jsonl | tail -5
```
Inspect `signal_results` — verify it includes the expected task IDs. If a task ID
is absent, `task_done` was never called for it by the worker.

**Step 3 — Check if task_done was bypassed**
If the worker read PR status via `gh pr view` instead of the merge hook path,
`task_done` may never have been called. Confirm:
```bash
grep '<TASK_ID>' .agentflow/hook_drain_debug.jsonl
```
No entries → task_done was never emitted for this task.

**Root cause pattern:** task_done absent → worker closed task in tasks.json
directly without signalling the session. Fix: ensure worker calls task_done hook
after confirming PR merge, not before.

---

## Epistemic Discipline

When log evidence is incomplete (truncated `cmd` fields, missing entries, gaps in
timestamps), **state the gap explicitly** and propose a targeted read to close it.

- Treat unverified inferences as **hypotheses** — label them: "Hypothesis: ..."
- High-confidence claims require a log citation (file + line or event timestamp)
- If evidence is absent, say so: "No log entry found — cannot confirm. To close
  this gap, run: `<specific command>`"
- Do NOT fill an evidence gap with a conclusion stated as fact

**Output format:** Root cause + fix recommendation in ≤ 3 sentences, followed by
any open hypotheses labeled as such with the specific read needed to confirm them.
