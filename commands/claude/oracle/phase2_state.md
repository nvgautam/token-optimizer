# Phase 2 — State Management

### Auto-commit rule (mandatory — after every state write)
After any write to `tasks.json`, `execution_plan.md`, or `design_status.md`, immediately commit and push:
```bash
git add tasks.json execution_plan.md design_status.md
git commit -m "chore(oracle): <one-line summary of what changed>"
git push
```
Never leave state changes uncommitted. Risk: PTY restart or session end silently loses the work.

### Addendum rule (mandatory — every filed task)
After filing a task to `tasks.json` and the round table, **always** append a proper `## Addendum: T-NNN — Title` block to `execution_plan.md`. Format:
```
## Addendum: T-NNN — Title

**Goal:** [1–2 sentences: what it does, why, context]

**Files:**
- `path/to/file.py` (new/modify) — purpose

**Test scenarios:**
- [concrete acceptance criterion]

**OWNS:** [comma-separated file list]
**estimated_lines:** [N]
```
No addendum = orchestrator cannot execute or evaluate the task. Never substitute a prose paragraph or inline note.

### Incremental Flush

**After each decision resolves, immediately append `| Topic | RESOLVED | Decision summary |` to `design_status.md` — no batching (PTY may restart mid-phase).**

**Shared file locking (T-229):** Before writing `tasks.json`, `execution_plan.md`, or `state.json`, acquire the corresponding lockfile via Python:
```python
import fcntl, pathlib
lock_path = pathlib.Path('.agentflow/tasks.json.lock')  # or .md or state.json
lock_path.parent.mkdir(parents=True, exist_ok=True)
with open(lock_path, 'a+') as f:
    fcntl.flock(f, fcntl.LOCK_EX)  # blocks until lock acquired
    # write the file here
    fcntl.flock(f, fcntl.LOCK_UN)
```
Locks are advisory — all writers must cooperate.

### Batch HANDOFF signals

| Batch | Signal |
|---|---|
| Functional (name, stack, modules, interfaces) | `HANDOFF RECOMMENDED: functional checklist items resolved — good stopping point if context is growing` |
| NFR (scale, perf, security, compliance, test, deploy) | `HANDOFF RECOMMENDED: NFR checklist items resolved — good stopping point if context is growing` |
| Integrations (external, ownership, creds, failure) | `HANDOFF RECOMMENDED: integrations checklist items resolved — good stopping point if context is growing` |
| Security (trust, data flows, auth, secrets) | `HANDOFF RECOMMENDED: security checklist items resolved — good stopping point if context is growing` |
| Quality gates (size limits, ownership, stubs, injection) | `HANDOFF RECOMMENDED: quality gates checklist items resolved — good stopping point if context is growing` |
| Delivery priority (audience, milestone sequence, constraints) | `HANDOFF RECOMMENDED: delivery priorities resolved — good stopping point if context is growing` |

All 24 resolved → spar on delivery priority: who is the first audience (internal/external)? What ships in M1 vs M2? Any ordering constraints? Bake answers into milestone sequencing before generating.

Then say exactly:
```
I have enough to generate the architecture and task plan. Shall I proceed, or is there more to discuss?
```

Don't generate until user confirms.
