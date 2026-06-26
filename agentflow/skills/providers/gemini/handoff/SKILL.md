# Handoff Skill — Gemini CLI

Flush current session state to the living state document and signal the PTY shell that handoff is complete.

---

## Compact format rule

When writing `architecture.md` or `execution_plan.md`, use tables and bullet points only — no prose paragraphs. Aim for 35-40% fewer tokens than prose equivalents. Every status entry must fit in a table row or a two-line bullet.

---

## Step 1 — Determine session type

Check which session is active:
- **Oracle session**: `architecture.md` exists and contains design items with `Status:` fields, OR the current conversation resolves design checklist items.
- **Orchestrator session**: `execution_plan.md` exists and the current conversation manages task lifecycle, OR `.agentflow/state.json` exists.
- **Ambiguous**: default to oracle session type.

---

## Step 2 — Oracle session: flush to architecture.md

For each design item discussed this session:

1. Classify as `RESOLVED`, `UNRESOLVED`, or `DEFERRED`.
2. Read `architecture.md` if it exists. Update or append each item:

```
## <Item Name>
Status: RESOLVED | UNRESOLVED | DEFERRED
Decision: <one-line decision> (RESOLVED only)
Open: <bullet list of open questions> (UNRESOLVED only)
Reason: <why deferred> (DEFERRED only)
```

3. Write the updated `architecture.md` using compact format — tables and bullets only.

4. Run the handoff script:
```bash
bash agentflow/skills/providers/gemini/handoff/scripts/run_handoff.sh architecture.md
```

---

## Step 3 — Orchestrator session: flush to execution_plan.md

1. Read `execution_plan.md` if it exists.
2. Update the task status table with last known state for each task:

```
| Task ID | Description | Status  | PR |
|---------|-------------|---------|-----|
| T-001   | one-line    | MERGED  | #4  |
| T-002   | one-line    | PR_OPEN | #5  |
```

3. Write the updated `execution_plan.md` using compact format — tables and bullets only.

4. Run the handoff script:
```bash
bash agentflow/skills/providers/gemini/handoff/scripts/run_handoff.sh execution_plan.md
```

---

## State file paths

All state files live under `.agentflow/` in the project root:
- `.agentflow/state.json` — orchestrator task state
- `.agentflow/telemetry.jsonl` — token telemetry
- `.agentflow/tasks.archive.json` — completed task archive

Do NOT use `.claude/memory/` paths — that is the user's personal Claude memory, not AgentFlow project state.

---

## HANDOFF RECOMMENDED — proactive signal

This signal fires during normal oracle and orchestrate operation — it does NOT require handoff to be invoked explicitly.

**Oracle** — after each batch of checklist items is resolved, emit:
```
HANDOFF RECOMMENDED: <N> items resolved, context growing — good stopping point
```

**Orchestrator** — after each task reaches `PR_OPEN` or `MERGED` state, emit:
```
HANDOFF RECOMMENDED: <task_id> at <state> — good stopping point before next round
```

The PTY shell detects this signal and injects the handoff command automatically when the token threshold is crossed. In manual mode, the user sees it and decides when to trigger handoff.

---

## After HANDOFF_COMPLETE is printed

Do not take further action. In manual mode, tell the user:

```
State flushed. Start a new Gemini session and run the oracle or orchestrate skill to resume.
```
