# Session Isolation Proposal: Per-SID Volatile State Folder

**Task:** T-190  
**Status:** Proposal (spike)  
**Date:** 2026-07-11

---

## Problem Statement

The `.agentflow/` root directory currently mixes two categories of files:

1. **Per-SID files** — state scoped to a single PTY/Claude Code session (one file per concurrent session).
2. **Global files** — shared state that persists across all sessions.

This causes two issues:

- **Clutter:** 100+ `handoff_*.md` files and 6+ `session_state_<SID>.json` files accumulate at root with no cleanup mechanism.
- **Race condition:** `context_fill.json` has no SID in its path. Two concurrent sessions (`post_tool_use.py`) overwrite each other's fill token count, causing PTY threshold decisions to use stale/wrong values from a different session.

---

## Proposed Folder Structure

```
.agentflow/
├── sessions/
│   └── <SID>/                          ← one folder per active session
│       ├── session_state.json          ← was session_state_<SID>.json at root
│       ├── context_fill.json           ← was context_fill.json at root (GLOBAL → per-SID)
│       └── handoff_<date><suffix>.md   ← was handoff_*.md at root
├── context/                            ← task context bundles (task-scoped, global)
├── memory/                             ← global memory store
├── current_round.json                  ← global orchestrator round state
├── state.json                          ← global session-resume bookmark
├── tasks_in_flight.json / .lock        ← global task coordination
├── task_prs.json                       ← global PR tracking
├── tasks.archive.json                  ← global archive
├── telemetry.jsonl                     ← global append log
├── size_violations.jsonl               ← global append log
├── pty_audit.jsonl                     ← global audit log
├── verbosity_ab_arm.txt / _log.jsonl / _baseline.json / _log.jsonl
├── model_ab_arm.txt / _baseline.json   ← global A/B state
├── headroom_ab_log.jsonl               ← global A/B log
├── shadow_reads.jsonl                  ← global savings analytics
├── payload_inspect.jsonl               ← global debug log
├── reset_accumulator                   ← global state flag
├── proxy_log.jsonl                     ← global log
├── file_families.jsonl                 ← global index
└── session_state.json                  ← global fallback (no-SID sessions only)
```

---

## Classification Table

| File | Current Location | Classification | Reason |
|------|-----------------|----------------|---------|
| `session_state_<SID>.json` | `.agentflow/` root | **Per-SID** | Already keyed by SID; scoped to one session |
| `context_fill.json` | `.agentflow/` root | **Per-SID** (currently global — bug) | Fill tokens are per-session; global causes race condition |
| `handoff_<date><suffix>.md` | `.agentflow/` root | **Per-SID** | Emitted at session close; one or more per session |
| `current_round.json` | `.agentflow/` root | Global | Orchestrator round state shared across invocations |
| `state.json` | `.agentflow/` root | Global | Session-resume bookmark persists after PTY exits |
| `tasks_in_flight.json` / `.lock` | `.agentflow/` root | Global | Cross-session task coordination |
| `task_prs.json` | `.agentflow/` root | Global | PR tracking, survives sessions |
| `tasks.archive.json` | `.agentflow/` root | Global | Archive, append-only |
| `telemetry.jsonl` | `.agentflow/` root | Global | Project-wide append log |
| `size_violations.jsonl` | `.agentflow/` root | Global | Project-wide append log |
| `pty_audit.jsonl` | `.agentflow/` root | Global | Audit trail, all sessions |
| `verbosity_ab_*.txt/json/jsonl` | `.agentflow/` root | Global | A/B experiment state |
| `model_ab_*.txt/json` | `.agentflow/` root | Global | A/B experiment state |
| `headroom_ab_log.jsonl` | `.agentflow/` root | Global | A/B log |
| `shadow_reads.jsonl` | `.agentflow/` root | Global | Savings analytics |
| `payload_inspect.jsonl` | `.agentflow/` root | Global | Debug log |
| `reset_accumulator` | `.agentflow/` root | Global | State flag |
| `proxy_log.jsonl` | `.agentflow/` root | Global | Log |
| `file_families.jsonl` | `.agentflow/` root | Global | Index |
| `context/` | `.agentflow/` root | Global (task-scoped) | Task context bundles; not SID-scoped |
| `memory/` | `.agentflow/` root | Global | Memory store |
| `session_state.json` (no SID) | `.agentflow/` root | Global fallback | Fallback for sessions without `AGENTFLOW_SESSION_ID` |

---

## Migration Map

| Old Path | New Path | Notes |
|----------|----------|-------|
| `.agentflow/session_state_<SID>.json` | `.agentflow/sessions/<SID>/session_state.json` | Written by `user_prompt_submit.py`; read by `threshold_sync.py` |
| `.agentflow/context_fill.json` | `.agentflow/sessions/<SID>/context_fill.json` | Written by `post_tool_use.py` and `stop_context_capture.py`; read by `output_handler.py`, `handoff_handler.py`, `session_manager.py` |
| `.agentflow/handoff_<date><suffix>.md` | `.agentflow/sessions/<SID>/handoff_<date><suffix>.md` | Written by `/handoff` skill |
| `.agentflow/session_state.json` (no SID) | `.agentflow/session_state.json` (unchanged) | Fallback for no-SID sessions; keep in place |
| `.agentflow/context_fill.json` (no SID) | `.agentflow/context_fill.json` (unchanged as fallback) | Root copy kept as fallback for no-SID sessions only |

---

## Race Condition Analysis: `context_fill.json`

### Current Behavior

`post_tool_use.py` and `stop_context_capture.py` each write:
```
fill_path = agentflow_dir / "context_fill.json"
```

There is no SID in the path. Two concurrent sessions (session A with SID `abc`, session B with SID `xyz`) both write to the same file. The atomic `tempfile + os.replace` prevents partial writes, but does not prevent last-writer-wins overwrite.

**Scenario:**
1. Session A writes `{"fill_tokens": 50000, "ts": T1}` to `context_fill.json`.
2. Session B writes `{"fill_tokens": 12000, "ts": T2}` to the same path.
3. Session A's PTY reads the file and sees `fill_tokens=12000` — incorrectly below its threshold, suppressing a needed handoff.

### Fix

Move write targets to per-SID paths:
```
fill_path = agentflow_dir / "sessions" / sid / "context_fill.json"
```

Each session reads from its own folder. Sessions never share a fill file. The atomic write already in place remains sufficient.

**Read-side callers** (`output_handler.py`, `handoff_handler.py`, `session_manager.py`) must accept the SID to construct the per-SID path. The SID is available from `os.environ.get("AGENTFLOW_SESSION_ID")` in the PTY process.

### Staleness window

`output_handler.py` already checks mtime freshness (`FILL_STALE_SECONDS`). This guard remains correct post-migration; no change required.

---

## Backward-Compatibility Strategy

The only scenario that must keep working after migration is a session where `AGENTFLOW_SESSION_ID` is not set (legacy invocations, tests, manual hook calls).

**Rule:** All read and write helpers follow this fallback chain:

```python
if sid:
    path = agentflow_dir / "sessions" / sid / filename
else:
    path = agentflow_dir / filename          # legacy root path
```

This is implemented once in a shared helper (T-200) and called from all six sites that currently hardcode the root path. No existing session breaks because:

- `sync_session_type` in `threshold_sync.py` already has a multi-filename fallback chain; the per-SID folder is simply prepended as the highest-priority candidate.
- `context_fill.json` at root is kept as the no-SID fallback; it is never removed.
- `session_state.json` (no suffix) at root is kept as the no-SID fallback.

---

## Stale Session Cleanup

**Problem:** Without cleanup, `sessions/<SID>/` folders accumulate indefinitely (same problem as current `session_state_<SID>.json` files).

**Proposed TTL:** 24 hours from the folder's last mtime. Sessions complete in minutes to a few hours; 24h provides a comfortable safety margin.

**Trigger:** Best-effort cleanup runs once on PTY manager startup, before the PTY process is created. Errors are silently ignored — cleanup failure must never block a session from starting.

**Algorithm:**
```python
def cleanup_stale_sessions(agentflow_dir: Path, ttl_seconds: int = 86400) -> None:
    sessions_dir = agentflow_dir / "sessions"
    if not sessions_dir.exists():
        return
    cutoff = time.time() - ttl_seconds
    for sid_dir in sessions_dir.iterdir():
        if sid_dir.is_dir() and sid_dir.stat().st_mtime < cutoff:
            shutil.rmtree(sid_dir, ignore_errors=True)
```

Cleanup runs in the PTY process, not in hooks, to avoid racing with an in-flight write from the hook side.

---

## Discoverability Note: `handoff_*.md`

Moving handoff documents into `sessions/<SID>/` improves root cleanliness but reduces direct discoverability — the human currently `ls .agentflow/` to find the latest handoff. Mitigations:

1. **Symlink** latest handoff to `.agentflow/handoff_latest.md` (updated by the handoff skill on each write). Lightweight, no extra tooling.
2. **No change** — keep handoff docs at root; only migrate `session_state` and `context_fill`. Simpler; defers clutter problem.
3. **Index file** — handoff skill appends to `.agentflow/handoffs.index` (one line per entry with SID + path).

Option 1 is recommended. Option 2 is acceptable for an initial migration (handoff cleanup as a follow-on).

---

## Implementation Task Stubs

```json
[
  {
    "task_id": "T-200",
    "title": "Add session_paths.py — SID path helper utility",
    "owns": ["agentflow/shell/session_paths.py"],
    "reads": ["agentflow/shell/session_manager.py"],
    "depends_on": [],
    "estimated_lines": 40
  },
  {
    "task_id": "T-201",
    "title": "Migrate context_fill.json writes to per-SID path in hooks",
    "owns": [
      "agentflow/hooks/post_tool_use.py",
      "agentflow/hooks/stop_context_capture.py"
    ],
    "reads": ["agentflow/shell/session_paths.py"],
    "depends_on": ["T-200"],
    "estimated_lines": 25
  },
  {
    "task_id": "T-202",
    "title": "Migrate context_fill.json reads to per-SID path in PTY shell",
    "owns": [
      "agentflow/shell/output_handler.py",
      "agentflow/shell/handoff_handler.py",
      "agentflow/shell/session_manager.py"
    ],
    "reads": ["agentflow/shell/session_paths.py"],
    "depends_on": ["T-200"],
    "estimated_lines": 30
  },
  {
    "task_id": "T-203",
    "title": "Migrate session_state writes from root to sessions/<SID>/",
    "owns": ["agentflow/hooks/user_prompt_submit.py"],
    "reads": ["agentflow/shell/session_paths.py"],
    "depends_on": ["T-200"],
    "estimated_lines": 20
  },
  {
    "task_id": "T-204",
    "title": "Update threshold_sync.py to read session_state from sessions/<SID>/",
    "owns": ["agentflow/shell/threshold_sync.py"],
    "reads": ["agentflow/shell/session_paths.py"],
    "depends_on": ["T-200", "T-203"],
    "estimated_lines": 20
  },
  {
    "task_id": "T-205",
    "title": "Update handoff skill to write handoff_*.md into sessions/<SID>/",
    "owns": ["commands/claude/handoff.md"],
    "reads": [],
    "depends_on": ["T-200"],
    "estimated_lines": 15
  },
  {
    "task_id": "T-206",
    "title": "Symlink sessions/<SID>/handoff_*.md as .agentflow/handoff_latest.md",
    "owns": ["commands/claude/handoff.md"],
    "reads": [],
    "depends_on": ["T-205"],
    "estimated_lines": 10
  },
  {
    "task_id": "T-207",
    "title": "Add stale session folder cleanup on PTY startup (TTL 24h)",
    "owns": [
      "agentflow/shell/session_paths.py",
      "agentflow/shell/session_manager.py"
    ],
    "reads": [],
    "depends_on": ["T-200"],
    "estimated_lines": 35
  }
]
```
