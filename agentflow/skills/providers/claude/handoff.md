# /handoff — Session State Flush

Flush current session state to the living state document and signal the PTY shell that handoff is complete.

---

## Compact format rule

When writing `architecture.md` or `execution_plan.md`, use tables and bullet points only — no prose paragraphs. Aim for 35-40% fewer tokens than prose equivalents. Every status entry must fit in a table row or a two-line bullet.

---

## Step 1 — Determine session type

Check which session is active:
- **Oracle session**: `architecture.md` exists and contains design items with `Status:` fields, OR the current conversation involves resolving design checklist items.
- **Orchestrator session**: `execution_plan.md` exists and the current conversation involves managing task lifecycle (PENDING → MERGED), OR `.agentflow/state.json` exists.
- **Ambiguous**: default to oracle session type.

---

## Step 2 — Oracle session: flush to architecture.md

Read the current conversation context. For each design item discussed this session:

1. Classify as `RESOLVED`, `UNRESOLVED`, or `DEFERRED`.
2. Read `architecture.md` if it exists. Update or append each item using this exact format:

```
## <Item Name>
Status: RESOLVED | UNRESOLVED | DEFERRED
Decision: <one-line decision> (RESOLVED only)
Open: <bullet list of open questions> (UNRESOLVED only)
Reason: <why deferred> (DEFERRED only)
```

3. Write the updated `architecture.md`. Use compact format throughout — tables and bullets, no prose paragraphs.

4. Print exactly:
```
HANDOFF_COMPLETE: architecture.md
```

---

## Step 3 — Orchestrator session: flush to execution_plan.md

Read the current task states from conversation context and `.agentflow/state.json` (if present).

1. Read `execution_plan.md` if it exists.
2. Update the task status table to reflect the last known state of each task worked on this session. Use this table format:

```
| Task ID | Description | Status | PR |
|---------|-------------|--------|----|
| T-001   | one-line    | MERGED | #4 |
| T-002   | one-line    | PR_OPEN| #5 |
```

3. Write the updated `execution_plan.md`. Use compact format — tables and bullets only.

4. Print exactly:
```
HANDOFF_COMPLETE: execution_plan.md
```

---

## State file paths

All state files live under `.agentflow/` in the project root:
- `.agentflow/state.json` — orchestrator task state
- `.agentflow/telemetry.jsonl` — token telemetry
- `.agentflow/tasks.archive.json` — completed task archive

Do NOT use `.claude/memory/` paths for state — that is the user's personal memory, not the project state. The living state documents (`architecture.md`, `execution_plan.md`) are the session state for AgentFlow sessions.

---

## HANDOFF RECOMMENDED — proactive signal

This signal fires during normal `/oracle` and `/orchestrate` operation — it does NOT require `/handoff` to be invoked. The purpose is to give the user a natural stopping point before context grows too large.

**Oracle** — after each batch of checklist items is resolved, emit:
```
HANDOFF RECOMMENDED: <N> items resolved, context growing — good stopping point
```

**Orchestrator** — after each task reaches `PR_OPEN` or `MERGED` state, emit:
```
HANDOFF RECOMMENDED: <task_id> at <state> — good stopping point before next round
```

When the PTY shell is active, it detects this signal and injects `/handoff` automatically when the token threshold is crossed. In manual (pre-PTY) mode, the user sees the signal and decides when to run `/handoff`.

---

## After printing HANDOFF_COMPLETE

Do not take any further action. The PTY shell will inject `/clear` and restart the session. If running manually (no PTY), tell the user:

```
State flushed. Start a new session and run /oracle or /orchestrate to resume.
```
