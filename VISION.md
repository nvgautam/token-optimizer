# Multi-Agent Project Manager with Token Optimization

## Vision

An orchestrator that decomposes projects into tasks, assigns them to Claude and Gemini agents
in isolated worktrees, manages inter-task dependencies, and enforces session boundaries at task
completion — so each agent starts every task with a fresh context window.

The economic bet: **task completion = natural session reset**. Real token usage stays low
(each session only carries the tokens needed for one task). Shadow tokens (what a single
continuous session would have consumed) compound across all tasks. If shadow/real ≥ 3×
consistently, the approach is worth productizing.

---

## What Already Exists (OCI Assistant as Proof of Concept)

| Component | Where | Status |
|---|---|---|
| Worktree layout (main + claude/work + gemini/work) | `CLAUDE.md` | Live |
| Task board with dependency tracking | `TASK_BOARD.md` | Live |
| Agent assignment (Claude vs Gemini) | `GEMINI_TASKS.md` + `TASK_BOARD.md` | Live |
| Session handoff protocol | `SESSION_HANDOFF_PROTOCOL.md` | Live |
| Token ledger (real + shadow model) | `agentflow.py` + `agentflow_ledger.json` | Live |
| Per-session token capture (`/handoff`) | `agentflow.py handoff` | Live |
| Context warning stop hook (`ctx-watch`) | `agentflow.py ctx-watch` + `.claude/settings.json` | Live |
| Cumulative savings report | `agentflow.py report` | Live |

---

## Evaluation Phase (Do This First)

Run the OCI assistant project and this project side by side. At the end of each session, run:

```bash
python3 agentflow.py report
```

**Success criterion:** Shadow tokens ≥ 3× real tokens after 10+ sessions across both projects.

Track per-task:
- Real tokens consumed (from JSONL auto-read)
- Estimated shadow tokens (accumulated context without session cycling)
- Task size (small / medium / large) — to check if task granularity affects the ratio

If the ratio holds, the approach is validated. If it doesn't, investigate whether tasks are too
large (spanning multiple sessions) or too small (session overhead dominates).

---

## Product Vision (Phase 3 — only if Phase 1 validates)

**Not a new UI.** A PTY terminal that wraps existing CLI tools — `claude`, `agy`, `codex`,
etc. — so users experience each tool's native interface unchanged. The PTY sits transparently
between the user and the tool, monitoring context and managing session restarts automatically.

```
User
  │  (types as normal)
  ▼
PTY wrapper
  ├── forwards I/O to the underlying CLI (claude / agy / codex)
  ├── watches context usage (reads JSONL / SQLite / Codex equivalent)
  ├── watches TASK_BOARD.md for task completion events
  └── triggers session restart at the right moment (see below)
  ▼
Native CLI (unmodified)
```

The user never sees the PTY — they just see their familiar tool. The PTY adds one thing:
automatic session lifecycle management.

### When to restart: orchestrator vs worker agents

These are different:

**Orchestrator** — restart on context threshold (automatic, hard trigger).
The orchestrator's memory is `TASK_BOARD.md`. It is stateless by design. Restarting at 70%
context is cheap: the next session re-reads the task board, resolves the DAG, and continues.
No meaningful context loss.

**Worker agents (Claude/Gemini/Codex)** — restart at task completion only, NOT on threshold.
Mid-task restarts break in-flight reasoning and lose context that cannot be recovered from the
task board. The ctx-watch hook warns workers when context is high — that is a signal to wrap
up the current task, not to restart immediately. The PTY watches for `DONE` status on the
current task, then restarts the worker for the next assignment.

Exception: if a worker exceeds a hard ceiling (e.g. 90%) mid-task, the PTY triggers an
emergency handoff + checkpoint and restarts. This is a fallback, not normal operation.

**Summary:**

| Agent | Restart trigger | Restart type |
|---|---|---|
| Orchestrator | Context ≥ threshold | Hard, automatic |
| Worker | Task marked DONE | Soft, at boundary |
| Worker (emergency) | Context ≥ 90% mid-task | Hard, with checkpoint |

### What the PTY needs to implement

1. **PTY multiplexing** — fork the target CLI into a PTY, relay I/O transparently
2. **Context reader** — per-tool plugin that reads token usage (JSONL for Claude, SQLite for Gemini, TBD for Codex)
3. **Task board watcher** — inotify/polling on `TASK_BOARD.md` for status changes
4. **Session manager** — kills the current process, starts a new one, optionally injects a context summary prompt
5. **Handoff hook** — calls `agentflow.py handoff` before killing the session to capture token data

### Open design question

Should the PTY inject a session summary into the new process on restart? E.g.:
```
[Session restarted — previous task: G-097 (DONE). Next task: G-098. Context: see TASK_BOARD.md]
```
This costs tokens but reduces ramp-up time. Probably yes for workers, probably no for the
orchestrator (it re-reads the task board anyway).

---

## Architecture (Phase 2 — build after validation)

```
Orchestrator
  ├── reads TASK_BOARD.md (tasks + dependencies + agent assignment)
  ├── resolves which tasks are unblocked (all deps DONE)
  ├── assigns unblocked tasks to the appropriate agent worktree
  ├── monitors for task completion (DONE status written to TASK_BOARD.md)
  └── signals PTY to restart worker for next task
```

**TASK_BOARD.md is the shared state.** Both agents and the orchestrator read/write task status
here. No separate DB needed.

**One task per session is the target.** Tasks should be sized to complete in 1-2 sessions.
Tasks that regularly spill across 3+ sessions should be split.

**Dependency resolution is DAG-based.** Tasks have `depends_on: [TASK_ID, ...]`. The
orchestrator finds all tasks where every dep is DONE and the task is TODO/unassigned.

---

## Optimization Levers

Token savings come from multiple levers operating at different points in the session lifecycle. Session cycling is the primary lever and already tracked empirically. The others are complementary and stack on top.

### Savings estimates

| Lever | When it applies | Est. savings | Confidence | Effort |
|---|---|---|---|---|
| **Session cycling** | Per session boundary | 50–75% of total tokens | High — tracked via agentflow ledger (shadow/real ratio) | High (PTY + task discipline) |
| **File size / split recipe** | Per Read tool call | 10–20% of total tokens | Medium — depends on how often large files are read per session | Medium (one-time refactor per file) |
| **Redundant re-read prevention** | Per session | 5–15% of total tokens | Medium — highly variable by session pattern | Medium (convention + scan script) |
| **Always-loaded file hygiene** | Every session turn | 5–15% of total tokens | Medium — depends on cache hit rate and file sizes | Low (trim CLAUDE.md, MEMORY.md) |
| **Task board verbosity control** | Per task board read | 3–8% of total tokens | Medium — task board is re-read at every session start | Low (move notes to linked files) |
| **Prompt cache structuring** | Every session turn | 3–8% of total tokens | Low — requires cache hit rate data to validate | Low (reorder file sections) |
| **Tool output filtering** | Per Bash tool call | 5–10% on affected calls | Low — only applies where verbose commands are run | Low (discipline / linting rule) |
| **Session summary quality** | Per session boundary | 5–10% on recovery reads | Low — hard to measure without compression telemetry | Low (doc structure discipline) |

**Combined theoretical ceiling:** stacking all levers could reach 70–85% savings vs a naive single continuous session. Worked example: a 200k-token naive session → session cycling reduces it to ~66k → file splitting + hygiene + cache structuring bring it to ~43k. In practice, levers overlap and diminish — a realistic sustained target is **65–75%** with session cycling as the dominant contributor (~two-thirds of total savings).

### Confidence note

Session cycling savings are empirically tracked. All other estimates are theoretical — derived from token arithmetic on typical file sizes and read patterns in the OCI project. They should be treated as hypotheses to validate as the product matures, not commitments.

### Interaction effects

- **Session cycling + file splitting**: smaller files reduce the token cost of each session, which amplifies the cycling benefit — lower shadow tokens means a higher shadow/real ratio.
- **Always-loaded hygiene + cache structuring**: compound together — a lean, stably-ordered `CLAUDE.md` maximises both cache hit rate and the per-hit saving.
- **Task board verbosity + session cycling**: the task board is re-read at the start of every session (the orchestrator re-reads it to resolve the DAG). Verbosity here is a per-session-start tax, not a one-time cost — so it scales directly with session count.

### Toggle

All secondary levers (file scanning, verbosity checks, re-read tracking) are opt-in via `.token-optimize.json`. When turned off, Claude will tell you in plain language:

> "Token optimization checks are now off. Your sessions may gradually get slower and cost more as files grow, but you won't be interrupted with suggestions. You can re-enable this at any time."

When turned on:

> "Token optimization is now on. Claude will periodically flag files that have grown too large and suggest splitting them, and will warn when the same file is read more than once in a session. Think of it as preventing clutter before it builds up."

See C-033 in `TASK_BOARD.md` for the implementation plan.

---

## Open Questions

1. **Task granularity sweet spot** — how small does a task need to be to fit cleanly in one
   session? The OCI project will provide empirical data.
2. **Gemini session boundaries** — agy doesn't reset context as cleanly as Claude Code's
   `/clear`. Need to verify shadow tracking accuracy and whether the PTY can force a clean reset.
3. **Codex context monitoring** — no JSONL or SQLite equivalent known yet; needs investigation.
4. **Session summary injection** — cost vs benefit of injecting a handoff summary into the new
   session on restart. Probably opt-in per tool.
5. **Multi-project support** — the current ledger is per-project. PTY product needs a
   cross-project ledger with project tags.
