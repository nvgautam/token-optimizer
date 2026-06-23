# Agent Orchestrator — Architecture & Project Plan

> **Purpose:** Hand this document to Claude (or any AI coding agent) to implement the system.  
> **TL;DR:** A pseudo-terminal wrapper around Claude/Codex/Antigravity CLIs that solves token ballooning through structured task decomposition, succinct context handoff, and automatic session cycling.

---

## 1. Problem Statement

Long-running AI CLI sessions accumulate context ("token ballooning") that:

- Increases latency and cost per response.
- Eventually hits context-window limits and crashes the session.
- Forces users to manually summarize and restart — error-prone and tedious.

**This system solves it by:**

1. Decomposing work into discrete tasks managed in plain-text files.
2. Detecting task completion automatically.
3. Distilling the conversation to a succinct context snapshot.
4. Restarting the agent with only the snapshot + next task — not the full history.

---

## 2. Core Concepts

### 2.1 Roles

| Role | Description |
|---|---|
| **Orchestrator** | The wrapper process. Manages all PTY sessions, monitors completion, compresses context, cycles sessions. Never itself an LLM call. |
| **Master Agent** | An LLM session whose *only* job is to maintain `plan.md` — break goals into tasks, update task status, write worker task files. Always interactive — the user's primary window. |
| **Worker Agent** | An LLM session scoped to a single task file. Reads its task, does the work, writes a completion marker. Interactive when the user switches to its tab. |

### 2.2 File Conventions

```
project-root/
├── plan.md                  # Owned exclusively by Master Agent
├── .orchestrator/
│   ├── config.yaml          # Wrapper configuration
│   ├── context/
│   │   ├── master.ctx.md    # Latest succinct context for Master Agent
│   │   └── worker-<id>.ctx.md  # Latest context per worker slot
│   └── logs/
│       └── session-<ts>.log
└── tasks/
    ├── worker-1.task.md     # Written by Master Agent, read by Worker
    ├── worker-2.task.md
    └── ...
```

### 2.3 Task File Schema

Each `tasks/worker-<id>.task.md` follows this structure:

```markdown
# Task: <short title>
Status: pending | in_progress | done | failed | blocked
Worker: worker-1
Created: <ISO timestamp>
---

## Objective
<What the worker must accomplish — precise and bounded.>

## Inputs
- File: path/to/relevant/file
- Context: .orchestrator/context/worker-1.ctx.md

## Success Criteria
- [ ] Criterion A
- [ ] Criterion B

## Output
- Modified file: path/to/output
- Write completion signal to: tasks/worker-1.task.md (update Status → done)

## Blocked (if Status = blocked)
Question: <one-line question for the user>

## Notes
<Any constraints, style guides, references.>
```

### 2.4 plan.md Schema

```markdown
# Project Plan
Last updated: <ISO timestamp>
Master context: .orchestrator/context/master.ctx.md

## Goal
<High-level goal for the project.>

## Tasks
| ID | Title | Status | Worker | Updated |
|----|-------|--------|--------|---------|
| T1 | Scaffold repo | done | worker-1 | 2025-06-10 |
| T2 | Write auth module | in_progress | worker-2 | 2025-06-11 |
| T3 | Write tests | pending | - | - |

## Notes
<Master Agent's working notes — dependencies, decisions, risks.>
```

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                            │
│         (Node.js / Python process — no LLM calls)           │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   TUI Layer (blessed / textual)         │ │
│  │  Tab bar: [master] [worker-1] [worker-2]                │ │
│  │  Keyboard routing: Ctrl+] m/1/2 switches active PTY     │ │
│  │  Notification bar: "[worker-1 is blocked — Ctrl+] 1]"  │ │
│  └──────────────────────────┬──────────────────────────────┘ │
│                             │                                │
│  ┌──────────────────────────▼──────────────────────────────┐ │
│  │                   PTY Manager                           │ │
│  │  One node-pty instance per agent (master + N workers)  │ │
│  │  Each PTY:                                              │ │
│  │    - Passes stdin/stdout transparently                  │ │
│  │    - Tees output to its own in-memory transcript buffer │ │
│  │    - Buffer is a plain string, reset to "" on session   │ │
│  │      end (after context file has been written)         │ │
│  └──────────────────────────┬──────────────────────────────┘ │
│                             │                                │
│  ┌──────────────────────────▼──────────────────────────────┐ │
│  │              File Watcher (chokidar)                    │ │
│  │  Watches tasks/*.task.md for Status field changes       │ │
│  │  done → trigger compression + session cycle             │ │
│  │  failed → surface to user, save context                 │ │
│  │  blocked → surface question in notification bar         │ │
│  └──────────────────────────┬──────────────────────────────┘ │
│                             │                                │
│  ┌──────────────────────────▼──────────────────────────────┐ │
│  │              Session Lifecycle Manager                  │ │
│  │  1. Task assigned → spawn worker PTY with context       │ │
│  │  2. Status=done detected → call Compressor              │ │
│  │  3. Compressor writes .ctx.md (plain API call)          │ │
│  │  4. Reset transcript buffer to ""                       │ │
│  │  5. Kill PTY session → spawn next task                  │ │
│  └──────────────────────────┬──────────────────────────────┘ │
│                             │                                │
│  ┌──────────────────────────▼──────────────────────────────┐ │
│  │              Context Compressor                         │ │
│  │  Input:  transcript buffer (in-memory string)           │ │
│  │  Action: POST /v1/messages — one-shot, no PTY           │ │
│  │  Output: writes .orchestrator/context/<id>.ctx.md       │ │
│  │  Target: ≤500 tokens of structured Markdown summary     │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
        │ PTY            │ PTY              │ PTY
┌───────▼──────┐  ┌──────▼───────┐  ┌──────▼───────┐
│ Master Agent │  │ Worker Agent │  │ Worker Agent │
│ Always live  │  │   worker-1   │  │   worker-2   │
│ Manages      │  │ Executes one │  │ Executes one │
│ plan.md      │  │ task, then   │  │ task, then   │
│              │  │ session ends │  │ session ends │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 4. PTY Design — One Per Agent

Each agent (master + every worker) runs in its own dedicated PTY instance. The orchestrator acts as a terminal multiplexer:

### 4.1 Tab Switching

```
┌─────────────────────────────────────────────────────┐
│  [master] [worker-1*] [worker-2]        Ctrl+] to switch │
│  ─────────────────────────────────────────────────  │
│                                                     │
│  > Writing auth module...                           │
│  > Modified src/auth.ts                             │
│  > Added JWT validation                             │
│  > _                                                │
│                                                     │
│  ⚠ worker-2 is blocked — press Ctrl+] 2 to respond │
└─────────────────────────────────────────────────────┘

Keyboard shortcuts:
  Ctrl+] m   → switch to master agent
  Ctrl+] 1   → switch to worker-1
  Ctrl+] 2   → switch to worker-2
  Ctrl+] s   → show status of all agents
```

- The active tab's PTY receives all keyboard input and fills the screen.
- Inactive PTYs continue running in the background — their output is captured but not displayed.
- When the user switches to a tab, the last N lines of its output are replayed so context is not lost.

### 4.2 Transcript Buffer — What It Is and Is Not

Each PTY maintains its own transcript buffer. This is:

- **A plain in-memory string** (or array of lines) inside the orchestrator process.
- **Populated by** tee-ing the PTY's stdout stream — every character the agent outputs is appended.
- **Not a file** — it is never written to disk as a raw transcript.
- **Not the agent's context window** — the orchestrator has no access to the agent's internal state.
- **Reset to `""`** after the compressor has written the `.ctx.md` file and the PTY session is killed.
- **Capped** at a configurable size (default ~50K tokens by character count heuristic) using a ring buffer — oldest lines are dropped if the cap is hit.

### 4.3 Completion Detection (Per Worker PTY)

Three layers, checked in order:

**Layer 1 — File Watch (Primary)**
The file watcher detects `Status: done` in the task file. This is the canonical signal. Agents are instructed to update this field as their final action.

**Layer 2 — Output Sentinel (Secondary)**
The PTY output stream is scanned for:
```
[TASK_COMPLETE: worker-1]
```
This is emitted by the agent as plain text, prompted by its system prompt. The orchestrator intercepts it (dims or hides it from the user) and treats it as a completion signal.

**Layer 3 — Idle Timeout (Safety Net)**
If no output for N seconds (default 120s) and no completion signal, the orchestrator writes to the PTY's stdin:
```
Are you done with your task? If yes, update Status in your task file to "done"
and emit [TASK_COMPLETE: worker-1].
```
If still no signal after a second timeout, the task is marked `failed` and context is compressed and saved anyway.

### 4.4 Blocked Worker Handling

If a worker cannot proceed without input, it updates its task file:
```
Status: blocked
Question: Should I use JWT or session cookies for auth?
```

The file watcher detects `Status: blocked` and:
1. Shows a notification in the TUI: `⚠ worker-1 is blocked — press Ctrl+] 1 to respond`
2. The user switches to worker-1's tab and types the answer directly into that PTY
3. The worker continues; it updates Status back to `in_progress`

---

## 5. Context Compression — Step by Step

This happens automatically when a worker completes, between killing the old session and starting the next one.

```
Step 1 — Completion detected (file watch or sentinel)

Step 2 — Read transcript buffer
          The orchestrator reads its in-memory string for that PTY.
          This is the full stdout of the session since it started.

Step 3 — Kill the PTY session
          The worker agent process is terminated.
          Its context window is gone — that is intentional.

Step 4 — POST to /v1/messages (plain HTTP, no PTY)
          This is a brand new, isolated LLM call.
          It is NOT a new interactive session.
          Prompt:
            System: "You are a context compressor..."
            User:   "<transcript buffer contents>"
          The model returns a ≤500 token structured summary.

Step 5 — Write summary to disk
          .orchestrator/context/worker-1.ctx.md is written.

Step 6 — Reset transcript buffer
          The in-memory string for worker-1 is set to "".

Step 7 — Spawn next session (if another task is queued)
          New PTY is created for the next task.
          The agent's first message includes:
            - Contents of .orchestrator/context/worker-1.ctx.md
            - Contents of tasks/worker-2.task.md
          The new session starts with ~500 tokens of context,
          not the thousands from the previous session.
```

### 5.1 Why a Separate API Call for Compression

The compressor is a plain POST request, not an interactive session, for three reasons:

1. **Reliability** — if the agent session ended in a bad state (error, confused output, context limit hit), the orchestrator can still run the compressor against the buffered transcript. The dead session cannot respond.
2. **Output quality** — a cold, focused prompt ("summarize this transcript") produces a more neutral and compact summary than asking a fatigued, context-heavy session to summarize itself.
3. **No contamination** — the dying session's summarization exchange would itself need to be summarized. A separate call avoids this recursion.

Note: The total input tokens to the compressor are roughly equal to the transcript size either way. The saving is in the *next* session's startup cost — it receives ~500 tokens instead of the full history.

---

## 6. Agent System Prompts

### 6.1 Master Agent System Prompt

```
You are the Master Agent for this project. Your only job is to maintain plan.md.

Rules:
- Read plan.md at the start of every session.
- Break the high-level goal into discrete, bounded tasks.
- Write each task to tasks/worker-<N>.task.md using the defined schema.
- Update task statuses in plan.md when workers report completion.
- Never perform implementation work yourself. Delegate everything.
- When all tasks are done, write "Status: complete" in plan.md and emit [MASTER_COMPLETE].
- Your context from the previous session is in: .orchestrator/context/master.ctx.md
```

### 6.2 Worker Agent System Prompt

```
You are Worker Agent {id}. Your task is in: tasks/{id}.task.md

Rules:
- Read your task file first.
- Read your previous context from: .orchestrator/context/{id}.ctx.md (if it exists).
- Execute ONLY the objective in your task file. Nothing more.
- When done, update Status in your task file to "done".
- Emit exactly this line as your final output: [TASK_COMPLETE: {id}]
- If blocked waiting for input, set Status to "blocked" and add a Question field.
  Wait for the user to respond in this terminal before continuing.
- If you cannot complete the task, set Status to "failed" and emit:
  [TASK_FAILED: {id}] reason: <one line>
- Do not modify plan.md. Do not modify other workers' task files.
```

---

## 7. IDE Integration (VS Code / Cursor)

No MCP servers are required for the core system.

### 7.1 VS Code / Cursor Terminal

Run the orchestrator in the integrated terminal. Because it is a proper PTY wrapper, VS Code's terminal renders it identically to the underlying CLI — colors, cursor movement, and interactive prompts all pass through. The TUI tab bar renders using standard ANSI escape codes.

**Setup:** `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start Orchestrator",
      "type": "shell",
      "command": "orchestrator start --config .orchestrator/config.yaml",
      "presentation": { "panel": "dedicated", "reveal": "always" },
      "runOptions": { "runOn": "folderOpen" }
    }
  ]
}
```

### 7.2 MCP Server (Optional Enhancement)

If agents running inside the IDE's native AI tooling (Cursor agent mode, Claude Code) should participate as workers — without a PTY session — expose a lightweight MCP server:

Tools exposed:
- `get_my_task(worker_id)` — returns the task file contents
- `mark_task_done(worker_id)` — updates Status to done
- `mark_task_failed(worker_id, reason)` — updates Status to failed
- `mark_task_blocked(worker_id, question)` — updates Status to blocked

The file watcher detects all these changes identically. The PTY-based workers and MCP-based workers are fully interchangeable from the orchestrator's perspective.

### 7.3 Cursor Background Agent

Cursor's background agent can be pointed at a worker task file directly. The orchestrator writes the task file; Cursor picks it up; the file watcher detects completion. No MCP needed for this path.

---

## 8. Configuration

`.orchestrator/config.yaml`:

```yaml
cli:
  backend: claude           # claude | codex | antigravity | custom
  command: claude           # override if binary name differs
  args: []                  # extra args passed to the CLI

agents:
  master:
    context_file: .orchestrator/context/master.ctx.md
    plan_file: plan.md
  workers:
    max_concurrent: 2       # parallel worker PTY sessions
    task_dir: tasks/
    context_dir: .orchestrator/context/

completion_detection:
  file_watch: true
  sentinel_pattern: "\\[TASK_COMPLETE: {id}\\]"
  idle_timeout_seconds: 120

compression:
  enabled: true
  model: claude-sonnet-4-6  # model for the compressor API call
  max_output_tokens: 500
  transcript_buffer_chars: 200000   # ~50K tokens, ring buffer

tui:
  switch_key: "ctrl+]"      # prefix key for tab switching
  replay_lines: 40          # lines replayed when switching to a tab
  notification_bar: true

logging:
  dir: .orchestrator/logs/
  level: info               # debug | info | warn | error
```

---

## 9. Implementation Plan

### Phase 1 — Core PTY Infrastructure (Week 1)

| # | Task | Output |
|---|------|--------|
| 1.1 | Scaffold repo structure | `package.json`, directory layout, config loader |
| 1.2 | Implement single PTY wrapper | Spawns CLI, tees stdout to buffer, passes stdin/stdout |
| 1.3 | Implement transcript ring buffer | In-memory string with char cap, reset method |
| 1.4 | Implement file watcher | Watches task files, emits events on Status changes |
| 1.5 | Unit tests for PTY + watcher | Test suite passing |

### Phase 2 — Context Compression (Week 2)

| # | Task | Output |
|---|------|--------|
| 2.1 | Implement context compressor | POST /v1/messages, writes .ctx.md |
| 2.2 | Implement context injection on session start | Prepends .ctx.md to agent's first message |
| 2.3 | Implement session lifecycle manager | spawn → detect done → compress → reset buffer → kill |
| 2.4 | Integration test: full single-worker cycle | End-to-end compress + restart with context |

### Phase 3 — TUI Multiplexer (Week 3)

| # | Task | Output |
|---|------|--------|
| 3.1 | Implement TUI tab bar (blessed/textual) | Visual tab switcher, ANSI-rendered |
| 3.2 | Implement keyboard routing | Ctrl+] prefix switches active PTY |
| 3.3 | Implement tab replay buffer | Last N lines replayed on tab switch |
| 3.4 | Implement notification bar | Blocked/failed worker alerts |
| 3.5 | Integration test: multi-worker interaction | User switches tabs, responds to blocked worker |

### Phase 4 — Master Agent & Orchestration (Week 4)

| # | Task | Output |
|---|------|--------|
| 4.1 | Implement Master Agent session management | Dedicated PTY, drives plan.md |
| 4.2 | Implement task dispatch | Master writes task file → orchestrator spawns worker PTY |
| 4.3 | Implement multi-worker coordination | N concurrent PTYs, each with own buffer and lifecycle |
| 4.4 | Handle failure and blocked paths | Compress-on-fail, surface blocked question |
| 4.5 | Integration test: 5-task project end-to-end | Full orchestration cycle |

### Phase 5 — CLI UX, IDE & MCP (Week 5)

| # | Task | Output |
|---|------|--------|
| 5.1 | Implement CLI commands: `start`, `status`, `reset`, `logs` | User-facing CLI |
| 5.2 | Write `.vscode/tasks.json` template | VS Code / Cursor integration |
| 5.3 | Implement optional MCP server | `get_my_task`, `mark_done`, `mark_blocked` tools |
| 5.4 | Write `README.md` with quickstart | Documentation |
| 5.5 | Dogfood: use orchestrator to build orchestrator | Validation |

---

## 10. Technology Choices

| Concern | Recommendation | Rationale |
|---|---|---|
| Language | **TypeScript (Node.js)** | `node-pty` is the most mature PTY library; async event model fits well |
| PTY library | `node-pty` | Battle-tested; used by VS Code's own terminal |
| TUI framework | `blessed` | Handles ANSI rendering, keyboard input routing, box layouts |
| File watching | `chokidar` | Cross-platform, reliable |
| Config parsing | `js-yaml` | Simple, no dependencies |
| LLM calls (compressor) | `@anthropic-ai/sdk` or raw `fetch` | Direct API call, no session state |
| Testing | `vitest` | Fast, ESM-native |
| Python alternative | `ptyprocess` + `watchfiles` + `textual` | If team prefers Python |

---

## 11. Key Design Decisions & Rationale

**Q: Why one PTY per agent rather than one shared PTY?**
A: Multiple agents run concurrently. A shared PTY would interleave their output — unreadable and unroutable. Each agent needs its own process, its own stdin/stdout, and its own transcript buffer. The TUI layer sits above all PTYs and routes the user's keyboard to whichever tab is active.

**Q: What exactly is the transcript buffer?**
A: A plain in-memory string inside the orchestrator process, populated by tee-ing the PTY's stdout. It is not a file, not the agent's context window, and not shared between agents. It is reset to `""` after the context compressor has written the `.ctx.md` file.

**Q: Why kill the PTY session before running the compressor?**
A: The session's work is done. Keeping it alive wastes resources. The compressor only needs the transcript buffer, which is already in memory. The sequence is: detect done → read buffer → kill PTY → POST to compressor → write .ctx.md → reset buffer → spawn next.

**Q: Why file-based task communication?**
A: Files are readable by any agent CLI, any IDE, any human. They survive crashes. They are git-diffable. No infrastructure to deploy. The MCP server is a thin adapter over the same files for IDE-native agents.

**Q: Do we need MCP servers?**
A: No, for the core system. MCP is an optional adapter that lets IDE-native agents (Cursor, Claude Code) participate as workers without a PTY session. The file protocol works without it.

---

## 12. Open Questions for Implementor

1. **Worker concurrency:** Sequential (simpler, safer for shared files) or parallel (faster, requires file locking)?
   *Recommendation: Start sequential. Add `max_concurrent > 1` as an opt-in config flag with file locking.*

2. **Token counting:** Character heuristic (4 chars ≈ 1 token) or `tiktoken`?
   *Recommendation: Character heuristic for v1. Sufficient for a soft cap.*

3. **Compressor API key:** Reuse the same key as the underlying CLI backend, or require a separate one?
   *Recommendation: Read from `ANTHROPIC_API_KEY` env var, same as Claude CLI. Document that other backends need their own key.*

4. **Failed task retry:** Auto-retry once with failure reason appended to context, or always surface to user?
   *Recommendation: Surface to user for v1. Add auto-retry as config option.*

5. **Master Agent bootstrap:** Interactive `--goal` prompt on first run, or require `plan.md` to exist?
   *Recommendation: If no `plan.md`, prompt user interactively in the master PTY before starting.*

---

## 13. Acceptance Criteria

- [ ] `orchestrator start` launches a TUI with a master PTY and tab bar.
- [ ] The user sees identical output to running the underlying CLI directly.
- [ ] Multiple worker PTYs run concurrently; user can switch between them with `Ctrl+] N`.
- [ ] When a worker task completes, its session is compressed and a new session starts for the next task automatically.
- [ ] Blocked workers surface a notification; user responds by switching to that tab.
- [ ] Context summaries are ≤500 tokens and sufficient to continue work.
- [ ] A 10-task project uses ≤20% of the tokens a single continuous session would require.
- [ ] VS Code and Cursor integrated terminals render the TUI correctly.
- [ ] The optional MCP server allows IDE-native agents to act as workers.

---

*Document version 2.0 — updated with PTY multiplexer design, transcript buffer clarification, and step-by-step compression flow.*
