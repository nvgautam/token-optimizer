# T-259 Spike: CLI-as-Interface for Orchestrate Round Announcements

**Date:** 2026-07-18  
**Status:** Design only — no implementation beyond prototype stub

---

## Problem

State mutations are scattered across three writers with no single audit point:

| Writer | Mechanism | Hook dependency |
|--------|-----------|----------------|
| orchestrate skill | Write tool → `current_round.json` | `tool_name == "Write"` + path match |
| `pty_signal.py task_start` | Bash call | detected via `tool_name == "Bash"` + pattern match |
| `cleanup_tasks.py` | Bash call | not hooked — fires post-merge |

The T-247 regression demonstrated the fragility: when the skill switches from `Write` to `Bash` (or vice versa), the hook silently stops detecting the mutation. The hook must track *tool names*, not *intent*. This is the root coupling.

---

## Proposed CLI Surface

```
agentflow round start --task-ids T-259 T-260 [--round-id C-cli-spike] [--sid <session-id>]
agentflow round status
agentflow task done <task-id> [--sid <session-id>]
agentflow task start <task-id> [--sid <session-id>]
```

### Argument Details

**`agentflow round start`**
- `--task-ids` (required, 1+): task IDs entering this round
- `--round-id` (optional): human label written to `current_round.json`; defaults to a timestamp slug if omitted
- `--sid` (optional): session ID; falls back to `$AGENTFLOW_SESSION_ID` env var

Effect: atomically writes `current_round.json` and adds all `--task-ids` to `tasks_in_flight.json`.

**`agentflow task done <id>`**
- Equivalent to current `pty_signal.py task_done`
- Removes task from `tasks_in_flight.json`; writes `task_complete.json` if list drains to empty
- `--sid`: same fallback as above

**`agentflow task start <id>`**
- Equivalent to current `pty_signal.py task_start` (add to in-flight without touching `current_round.json`)
- Included for completeness; `round start` is the preferred entry point

---

## State File Migration Plan

| File | Current writer | Migrates to CLI? | Priority |
|------|---------------|-----------------|---------|
| `current_round.json` | orchestrate skill (Write tool) | YES — `agentflow round start` | HIGH |
| `tasks_in_flight.json` | `pty_signal.py task_start/done` (Bash) | YES — `agentflow task start/done` | HIGH |
| `task_complete.json` | `pty_signal.py task_done` side-effect | YES — emitted by `agentflow task done` | MEDIUM |
| `handoff_complete.json` | `pty_signal.py handoff_complete` | KEEP in pty_signal for now | LOW |
| `context_fill.json` | post_tool_use hook (not skill-driven) | OUT OF SCOPE | — |
| `tasks.json` | `cleanup_tasks.py` | OUT OF SCOPE | — |

PTY shell reads (`session_manager.py`) stay file-based. The CLI writes files; the PTY polls files. No change to the PTY read path.

---

## How This Eliminates the `tool_name` Hook Dependency

Today: hook inspects `tool_name` to guess *what the skill is doing*.

```
post_tool_use → detect tool_name == "Write" + path == "current_round.json"
             → sync tasks_in_flight (side effect)
             → audit_orchestrator_direct_write (detect policy violations)
```

With CLI: the skill calls `agentflow round start` via Bash. The command *is* the intent. No inference needed.

The hook's `sync_tasks_in_flight` and `audit_orchestrator_direct_write` functions can be removed entirely. The single point of mutation is `cli_db.py` — one place to audit, log, and enforce invariants.

Hooks that remain: `detect_pr_merge` (unchanged — still needs tool output inspection). All state-mutation detection hooks become dead code.

---

## How This Enables SQLite Backend Swap

Today every writer directly constructs JSON paths with `_write_atomic`. Adding SQLite requires touching every writer.

With the CLI layer, the backend is fully encapsulated in `cli_db.py`:

```python
# Today
def _write_current_round(round_id, task_ids, sid):
    _write_atomic(path, {"round_id": round_id, "task_ids": task_ids})

# SQLite swap: change only this function
def _write_current_round(round_id, task_ids, sid):
    db.execute("INSERT OR REPLACE INTO rounds ...")
```

All callers (`round start`, `task done`) call the same internal writer. The file-based fallback for PTY reads can remain — the CLI writes files as a side effect of the DB write, keeping the PTY read path unchanged during the transition period.

This is a clean façade: CLI surface stays constant, backend is swapped below it.

---

## Migration Path

### What changes in the orchestrate skill (`commands/claude/orchestrate.md`)

Replace:
```
Write tool → .agentflow/current_round.json
Bash: python3 agentflow/shell/pty_signal.py task_start T-259
```

With:
```
Bash: agentflow round start --task-ids T-259 T-260 --round-id C-my-round
```

One command replaces two serial writes with an atomic operation.

### What changes in `pty_signal.py`

- `task_start` and `task_done` become thin wrappers that call `agentflow task start/done` (or are called by it — direction TBD in implementation).
- `handoff_complete` stays in `pty_signal.py` for now (LOW priority, not skill-driven).
- Long-term: `pty_signal.py` is deprecated as CLI coverage expands.

### What changes in hooks

- `sync_tasks_in_flight` in `post_tool_use.py`: remove (no longer needed)
- `audit_orchestrator_direct_write` in `post_tool_use.py`: remove (no longer needed)
- `detect_pr_merge`: unchanged

### Rollout order

1. Ship `cli_db.py` with `round start` + `task done` (T-259 spike → full implementation task)
2. Update orchestrate skill to use `agentflow round start`
3. Update pty_signal `task_start`/`task_done` to delegate to CLI (or vice versa)
4. Remove dead hook logic
5. SQLite backend (future milestone)

---

## Risk Assessment

### What gets simpler
- No more `tool_name` brittle detection — regression surface eliminated
- Atomic `round start` replaces two-step write sequence (eliminates partial-write window)
- Single audit log in `cli_db.py` covers all state mutations
- SQLite swap is a 1-file change instead of N-file change

### What could break
- **Skill prompt changes required:** orchestrate.md skill must be updated to call `agentflow round start` instead of using Write tool. If the skill is not updated in sync, both paths run in parallel during transition — need a migration window.
- **`agentflow` binary availability:** the CLI must be installed in the same env where the skill runs Bash. In dev this is always true; in CI or fresh installs, `pip install -e .` is needed.
- **pty_signal.py tests:** tests that directly call `task_start`/`task_done` functions will still pass; tests that check file state via hooks will need updating.
- **Handoff path:** `handoff_complete` is not migrated in this spike — the hook still needs to detect it. This is acceptable for now.

### What stays unchanged
- PTY shell read path (file-based polling, stdlib-only)
- PR merge detection hook
- `tasks.json` writer (`cleanup_tasks.py`)
- `context_fill.json` writer (hook-internal)
