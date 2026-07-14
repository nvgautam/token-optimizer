# Spike T-215: Audit — Session Restart Conditions for Determinism

**Date:** 2026-07-14  
**Author:** agent (claude-sonnet-4-6)  
**Scope:** PTY shell restart chain; prerequisite for session-iso-3 (T-202, T-204, T-207)

---

## 1. Stdout Patterns Parsed by the PTY Shell

The PTY shell does NOT scan stdout for freeform LLM text to make restart decisions. All restart triggers are file-based (polled). Two stdout patterns are parsed solely for token accounting; one file presence is detected as a side channel for session reset.

### 1.1 Token accounting markers (output_handler.py, lines 87 and 91)

| Pattern | Regex | Source | Lines | Effect |
|---|---|---|---|---|
| Task start sentinel | `AGENTFLOW_TASK_START:([A-Za-z0-9_-]+)` | `agentflow/shell/output_handler.py` | 87–89 | Records token accumulator at task start for delta calculation only |
| Task complete sentinel | `AGENTFLOW_TASK_COMPLETE:([A-Za-z0-9_-]+)` | `agentflow/shell/output_handler.py` | 91–115 | Increments `_turn_count`; records token delta; triggers `_run_stale_index_guard` |

Neither pattern triggers restart. They affect token accounting and turn metrics only.

### 1.2 Preprocessing patterns (output_handler.py, lines 11–17)

| Pattern | Regex | Effect |
|---|---|---|
| ANSI strip | `\x1b\[[0-9;]*[mGKHFABCDhJlsu]` | Applied to all output before marker matching |
| Read path detection | Three-variant regex for `.py`, `.md`, `.json`, `.toml`, `.yaml`, `.txt` paths | Tracks `_last_idx_injected` for index injection; not restart-related |

### 1.3 Side-channel file detection (output_handler.py, lines 58–74)

`clear_signal` file (`.agentflow/clear_signal`) is checked on every output chunk. Written by `user_prompt_submit.py` when the user types exactly `/clear`. Effect: resets `session_type` to None, `_turn_count` to 0, and tokenizer state. Does not trigger restart.

### 1.4 Documentation drift: HANDOFF_COMPLETE stdout signal

`commands/claude/handoff.md` Step 8 states the PTY "scans stdout for `HANDOFF_COMPLETE`." The actual code does not scan stdout for this text. The PTY polls for `handoff_complete_{sid}.json` (file-based). The skill printing `HANDOFF_COMPLETE: ...` is for human-readable feedback only; it has no effect on PTY state transitions.

---

## 2. File Paths Read During the Restart Chain

### 2.1 Per-SID paths (session-isolated when AGENTFLOW_SESSION_ID is set)

| File | Pattern | Who writes | Who reads | Notes |
|---|---|---|---|---|
| `handoff_complete_{sid}.json` | `.agentflow/handoff_complete_{sid}.json` | PTY (orchestrator path, `handoff_handler.py` lines 28–34); oracle: skill should write but see Flag 1 | `handoff_handler.py` `poll_session()` line 114; `session_manager_handlers.py` `handle_session_exit()` line 151 | Falls back to `handoff_complete.json` when no SID |
| `session_state_{sid}.json` | `.agentflow/session_state_{sid}.json` | `user_prompt_submit.py` `_write_session_state_atomic()` line 76 | `threshold_sync.py` `sync_session_type()` lines 19–39 | Falls back to `session_state.json` then `session_type` |
| `{sid}.json` (home dir) | `~/.agentflow/sessions/{sid}.json` | `session_audit.py` `update_session_file()` | Nothing in restart chain; observability only | Written on session_type change |

### 2.2 Flat paths (no SID scoping — shared across concurrent sessions)

| File | Who writes | Who reads | Restart role |
|---|---|---|---|
| `task_complete.json` | `pty_signal.py` `task_done()` lines 99–100 | `handoff_handler.py` `poll_session()` line 142 | TASK_RUNNING → TASK_COMPLETE trigger |
| `tasks_in_flight.json` | `post_tool_use.py` `sync_tasks_in_flight()`; `pty_signal.py` `task_start/done()`; `user_prompt_submit.py`, `post_tool_use_agent.py` | `handoff_handler.py` `check_drain_restart()` line 197 | Drain-restart gate: empty `[]` tombstone allows restart |
| `current_round.json` | Orchestrator skill (Write tool) | `session_manager.py` init + mtime tracking; `process_manager.py` `spawn_new_child()` line 84 | IDLE → TASK_RUNNING on mtime change; TASK_CTX injection on restart |
| `context_fill.json` | `post_tool_use.py` after every tool call; `stop_context_capture.py` at session stop | `handoff_handler.py` `check_drain_restart()` lines 213–216; `output_handler.py` `_read_fill_tokens()` lines 26–35 | Drain-restart threshold: fill_tokens >= 80K |
| `session_state.json` | `user_prompt_submit.py` when no SID | `threshold_sync.py` `sync_session_type()` | Fallback session type when SID-keyed file absent |
| `handoff_complete.json` | `pty_signal.py` `handoff_complete()` line 108; legacy | `handoff_handler.py` `poll_session()` (fallback when no SID) | Fallback handoff completion signal |
| `handoff_disabled` | Manual/test | `session_manager.py` `_auto_handoff_disabled()` line 85 | Kill switch: prevents any auto-handoff |
| `debug_restart_trigger` | Manual/test | `debug_trigger.py` `check_debug_restart_trigger()` | Fires `trigger_handoff("debug")` on any session polling this file |
| `task_prs.json` | `post_tool_use_agent.py` `_register_pr_url()` | `post_tool_use_agent.py`, `user_prompt_submit.py` | PR merge detection for task completion; indirect restart path |
| `agentflow_ledger.json` | Ledger script | `session_manager_handlers.py` `handle_enter_handoff_pending()` lines 72–80 | Capacity calibration on entering HANDOFF_PENDING; not a restart gate |
| `pty_audit.jsonl` | `session_audit.py` `log_audit()` | Nothing in restart chain | Append-only observability |

---

## 3. Non-Determinism Flags

### Flag 1 (CRITICAL): `pty_signal.py handoff_complete` writes flat path; PTY polls SID-keyed path

- **Location:** `agentflow/shell/pty_signal.py` lines 104–109; `agentflow/shell/session_manager.py` lines 98–103
- **Problem:** `pty_signal.py handoff_complete()` unconditionally writes to `.agentflow/handoff_complete.json` (flat). When `AGENTFLOW_SESSION_ID` is set, `session_manager._handoff_complete_path` returns `.agentflow/handoff_complete_{sid}.json`. If the oracle `/handoff` skill calls `pty_signal.py handoff_complete`, the file lands at the wrong path and the PTY never sees it. The HANDOFF_PENDING state times out after 90 seconds (`_DEADLINES[HANDOFF_PENDING] = 90.0`), SIGKILLs the child, and forces IDLE.
- **Current mitigation:** Oracle auto-restart is marked DEFERRED (`session_manager_handlers.py` line 149). Oracle sessions do not restart — the 90s deadline is the expected terminal state for oracle handoffs. Flag becomes critical if oracle restart is ever implemented.
- **Pre-fix needed for session-iso-3:** No (deferred); yes if oracle restart is activated.

### Flag 2 (HIGH): `task_complete.json` is flat — shared across concurrent orchestrator sessions

- **Location:** `agentflow/shell/pty_signal.py` lines 81 and 99; `agentflow/shell/handoff_handler.py` line 142
- **Problem:** Task completion is signalled by presence of `.agentflow/task_complete.json` (flat). With two concurrent orchestrator PTY sessions (enabled by session-iso-3), session A's task completing flips session B's state machine TASK_RUNNING → TASK_COMPLETE, potentially triggering an unwanted restart in session B.
- **Pre-fix needed for session-iso-3:** YES. File must be SID-scoped (`task_complete_{sid}.json` or `sessions/<sid>/task_complete.json`). `pty_signal.py task_done()` must accept and use a SID argument.

### Flag 3 (HIGH): `tasks_in_flight.json` is flat — drain-restart is a shared signal

- **Location:** `agentflow/shell/handoff_handler.py` lines 197–209; `agentflow/hooks/post_tool_use.py` lines 73–75; `agentflow/shell/pty_signal.py` lines 44–74
- **Problem:** All concurrent sessions share `tasks_in_flight.json`. When session A's tasks drain (`[]` tombstone), `check_drain_restart` may fire in session B even if session B still has tasks running — because the tombstone was written for session A's round, not B's.
- **Pre-fix needed for session-iso-3:** YES. `tasks_in_flight.json` must be SID-scoped. All writers and readers must be updated consistently.

### Flag 4 (HIGH): `context_fill.json` is flat — fill token value shared across sessions

- **Location:** `agentflow/shell/handoff_handler.py` lines 213–216; `agentflow/hooks/post_tool_use.py` line 103; `agentflow/hooks/stop_context_capture.py` line 63
- **Problem:** Both the PostToolUse hook and the Stop hook write fill token counts to `context_fill.json` (flat). Concurrent sessions overwrite each other's value. The `check_drain_restart` guard reads whichever session last wrote the file — which may be another session's context fill, not the current session's.
- **Additional sub-issue:** `check_drain_restart()` does not validate the `ts` freshness field when reading `context_fill.json`. `output_handler.py _read_fill_tokens()` does check freshness (lines 31–33: `< FILL_STALE_SECONDS = 60`), but `check_drain_restart()` omits this check entirely. A stale value from a previous session can suppress or spuriously trigger a drain restart.
- **Pre-fix needed for session-iso-3:** YES for SID-scoping. Staleness check is an independent bug that should be fixed in both single- and multi-session modes.

### Flag 5 (HIGH): `current_round.json` mtime is flat — IDLE→TASK_RUNNING fires in all sessions on any write

- **Location:** `agentflow/shell/handoff_handler.py` lines 129–135; `agentflow/shell/session_manager.py` lines 151–153
- **Problem:** The IDLE → TASK_RUNNING transition fires when `current_round.json` mtime changes. This file is flat (no SID). If session A's orchestrator writes `current_round.json` to dispatch a new round, session B (also in IDLE) will also transition to TASK_RUNNING, believing it has work to do.
- **Pre-fix needed for session-iso-3:** YES. `current_round.json` must be SID-scoped or the mtime guard must compare against the SID embedded in the file content.

### Flag 6 (MEDIUM): `session_state.json` flat fallback — session type contamination

- **Location:** `agentflow/shell/threshold_sync.py` lines 19–39; `agentflow/hooks/user_prompt_submit.py` lines 76–78
- **Problem:** `sync_session_type()` falls back from `session_state_{sid}.json` to `session_state.json`. If the SID-keyed file hasn't been written yet (first turn, hook hasn't fired), the PTY reads the flat file which was last written by any session. A new orchestrator session could briefly adopt `"oracle"` as its session type if a concurrent oracle session wrote the flat file last, applying the wrong token threshold.
- **Current scope:** Low probability in practice because `user_prompt_submit.py` writes `session_state_{sid}.json` before the first turn completes. Becomes a real race in session-iso-3 parallel sessions.
- **Pre-fix needed for session-iso-3:** ADVISORY. Add a session-type guard: if the SID-keyed file is absent and the flat file belongs to a different session_type, treat session_type as unknown rather than inheriting.

### Flag 7 (LOW): LLM text can match AGENTFLOW_TASK_START/COMPLETE patterns

- **Location:** `agentflow/shell/output_handler.py` lines 87–95
- **Problem:** These regexes match against raw LLM stdout. If the LLM explains the AgentFlow system or quotes source code containing these sentinel strings, it would falsely increment `_turn_count` and record spurious token deltas for a non-existent task.
- **Impact:** Corrupts turn and per-task token metrics. Does not trigger restart (no restart path depends on these markers).
- **Pre-fix needed for session-iso-3:** No, but bounded by adding a prefix guard (e.g., `^AGENTFLOW_TASK_`) if the LLM is asked to document these patterns.

### Flag 8 (LOW): `debug_restart_trigger` is flat — affects a random concurrent session

- **Location:** `agentflow/shell/debug_trigger.py` lines 9–17
- **Problem:** `.agentflow/debug_restart_trigger` is flat. Writing it during testing will trigger `trigger_handoff("debug")` in whichever session polls `on_idle_tick` first. In multi-session scenarios this is non-deterministic.
- **Pre-fix needed for session-iso-3:** Low priority. Use SID suffix in the file name or remove the mechanism from production hooks.

---

## 4. Restart Chain Summary (Orchestrator Path)

```
PostToolUse hook (post_tool_use_agent.py)
  → detects merged PR
  → pty_signal.py task_done(task_id)
      → writes task_complete.json [FLAT]
      → writes tasks_in_flight.json (tombstone []) [FLAT]

PTY poll_session() [handoff_handler.py:108]
  state == TASK_RUNNING
    → task_complete.json exists [FLAT]
    → transition("task_complete_written") → TASK_COMPLETE

  state == TASK_COMPLETE
    → transition("check_tokens", tokens=_last_accumulated_tokens)
    → StateMachine.guard_tokens_threshold()
        → if tokens >= 80000: → HANDOFF_PENDING
        → else: → IDLE

  state == HANDOFF_PENDING
    → on_enter_handoff_pending()
        → clears stale handoff_complete [SID-keyed]
        → session_type == "orchestrator":
            writes handoff_complete_{sid}.json directly [SID-keyed]  ← no LLM call
        → session_type == "oracle":
            writes /handoff\r to PTY stdin  ← LLM dependency
    → poll_session() sees handoff_complete_{sid}.json [SID-keyed]
    → transition("handoff_complete_written") → RESTARTING

  state == RESTARTING
    → on_enter_restarting()
        → _clear_signal_files()
            → unlinks task_complete.json [FLAT]
            → unlinks handoff_complete_{sid}.json [SID-keyed]
            → writes context_fill.json {"fill_tokens": 0} [FLAT]
        → restart_child()
            → SIGTERM old child → wait 2s → SIGKILL if needed
            → _clear_signal_files() again
            → spawn_new_child()
                → reads current_round.json for TASK_CTX [FLAT]
                → appends /orchestrate to command
                → pty.fork() → os.execvp()
        → resets _last_accumulated_tokens, tokenizer
        → transition("restart_done") → IDLE

Alternative drain path (check_drain_restart, handoff_handler.py:161):
  on_idle_tick() → check_drain_restart()
    → session_type == "orchestrator"
    → state in (IDLE, TASK_RUNNING)
    → not handoff_in_progress, not handoff_disabled
    → current_round.json exists [FLAT]
    → tasks_in_flight.json is [] tombstone [FLAT]
    → context_fill.json fill_tokens >= 80000 [FLAT, no staleness check]
    → transition("restart_session") → RESTARTING (bypasses HANDOFF_PENDING)
```

---

## 5. LLM Dependencies in the Restart Chain

| Session type | LLM call in restart path? | Details |
|---|---|---|
| orchestrator | NO | HANDOFF_PENDING writes `handoff_complete_{sid}.json` directly; no `/handoff` skill invoked |
| oracle | YES (currently blocked by DEFERRED gate) | PTY sends `/handoff\r` to stdin; waits up to 90s for `handoff_complete.json`; times out and kills child |

For orchestrator sessions (the only sessions that restart), the restart chain is fully deterministic and LLM-free. All transitions are driven by file presence and mtime polling.

---

## 6. Recommendation: Safety Assessment for session-iso-3

**Verdict: NOT safe to ship session-iso-3 (T-202/T-204/T-207) as-is for concurrent orchestrator sessions.**

Four flat files must be SID-scoped before concurrent orchestrator sessions are safe:

| Priority | File | Fix |
|---|---|---|
| P0 | `task_complete.json` | Scope to `task_complete_{sid}.json`; update `pty_signal.py task_done()` and `session_manager._task_complete_path` |
| P0 | `tasks_in_flight.json` | Scope to `tasks_in_flight_{sid}.json`; update all writers (post_tool_use.py, post_tool_use_agent.py, user_prompt_submit.py, pty_signal.py) and reader (handoff_handler.py check_drain_restart) |
| P0 | `current_round.json` | Scope mtime guard to SID; or embed SID in file content and validate on read |
| P1 | `context_fill.json` | Scope to `context_fill_{sid}.json`; update PostToolUse and Stop hooks; add staleness check in `check_drain_restart` |
| P1 | Staleness check in `check_drain_restart` | Read `ts` field and skip if > 60s old (matching `_read_fill_tokens` behavior) |

`session_paths.py` (`agentflow/shell/session_paths.py`) already provides the `session_file(agentflow_dir, filename, sid)` utility and is imported by session-iso-3 worktree hooks. The work is wiring it into the production hooks and PTY session_manager path properties.

**Single-session production usage is safe.** No concurrent PTY sessions means flat files are uncontested. All restart conditions are deterministic for a single session: file polling is the only trigger mechanism, no LLM text parsing drives restarts, and the orchestrator path bypasses the oracle `/handoff` LLM call entirely.
