# AgentFlow / Token Optimizer — Task Board

> **Protocol:** Tasks move left-to-right: TODO → IN_PROGRESS → DONE. One agent works one task at a time.  
> Notes cells: ≤ 1 sentence + a pointer to a linked file if more detail needed.  
> Reference: `VISION.md` (product vision), `AGENT_ORCHESTRATOR_PLAN.md` (PTY architecture).

---

## Phase 0 — Proof of Concept (DONE in OCI Assistant)

| ID | Description | Status | Notes |
|---|---|---|---|
| AF-P0 | Core agentflow.py: real/shadow tracking, JSONL reader, Gemini SQLite reader, `batch_decision`, `ctx-watch` stop hook, `classify_task`, `batch-check` CLI | DONE | Built and validated across 6 sessions in OCI project. Ledger data stays in OCI. |

---

## Phase 1 — Tooling Hardening (Validate before building Phase 3)

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| AF-001 | **Multi-project ledger.** Per-project `agentflow_ledger.json` (already the case). Add `report --all` flag that aggregates across all projects by scanning `~/.agentflow/projects.json` registry. Auto-register current project on first `handoff`. | TODO | — | Was C-010 in OCI task board. |
| AF-002 | **Auto-detect agent from CWD.** Update `handoff` to infer agent backend from worktree directory name (e.g. `oci-assistant-claude` → `claude`, `oci-assistant-gemini` → `gemini`). Prompt only if detection fails. | TODO | AF-001 ✅ | Was C-014 in OCI task board. |
| AF-003 | **Orchestrator scheduling integration.** Expose `classify_task()` + `batch_decision()` as a simple CLI check that a master/orchestrator agent can call between tasks to route: same session (batch) or fresh session. Accept task subject + optional file list from stdin or flags. | TODO | AF-001 ✅ | Was C-032 in OCI task board. |

---

## Phase 2 — Generic Token Optimizer Product

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| AF-004 | **Token scan + toggle.** `scripts/token_scan.py`: scan project files for size hotspots (flag files >500 lines) and re-read patterns in JSONL session log. `scripts/toggle_token_optimizer.py`: enable/disable via `.token-optimize.json` with plain-language UX messages. Acceptance: detects >500-line files and duplicate reads in a test fixture. | TODO | — | Was C-033 in OCI. C-033 artifacts were never committed — building fresh here. |
| AF-005 | **Redundant re-read prevention.** (1) Convention: document in `CLAUDE.md` that before any Read call, state what's already in context; only re-read if the file changed or the prior read was partial. (2) Extend `token_scan.py` to detect same file read >1× in a session's JSONL log. Toggle via `track_rereads` in `.token-optimize.json`. | TODO | AF-004 ✅ | Was C-034 in OCI. |
| AF-006 | **Split-file skill.** `.claude/commands/split-file.md` — slash command that takes a file path, proposes a split boundary, creates two files, updates all imports/references, and runs tests. First real application: test on a >500-line file in OCI bootstrap. | TODO | AF-004 ✅ | Companion to AF-004 file scanner. |

---

## Phase 3 — PTY Orchestrator (build only after Phase 1 validates shadow/real ≥ 3×)

> See `AGENT_ORCHESTRATOR_PLAN.md` for full architecture.

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| AF-007 | **PTY scaffolding.** Fork target CLI (claude/agy/codex) into a PTY. Relay stdin/stdout transparently. Tab-switching UI (blessed/textual). Config: `.orchestrator/config.yaml`. | TODO | Phase 1 validated | Python `ptyprocess` or Node `node-pty`. |
| AF-008 | **Context reader plugins.** Per-tool plugin interface. Claude: read JSONL from `~/.claude/projects/`. Gemini: read SQLite from `~/.gemini/antigravity-cli/conversations/`. Return (current_ctx, ctx_limit) tuple. | TODO | AF-007 ✅ | Reuse JSONL/SQLite readers already in agentflow.py. |
| AF-009 | **Task board watcher.** inotify/polling on `plan.md` (or `TASK_BOARD.md`). Detect status field changes: `done` → trigger compression + session cycle; `blocked` → surface question in notification bar. | TODO | AF-007 ✅ | Cross-platform: use `watchdog` Python lib. |
| AF-010 | **Session lifecycle manager.** On task DONE: call compressor → write `.orchestrator/context/<id>.ctx.md` → kill PTY → spawn fresh PTY with next task + context file injected as opening prompt. Emergency restart at 90% context mid-task. | TODO | AF-008 ✅, AF-009 ✅ | See AGENT_ORCHESTRATOR_PLAN.md §3 for lifecycle diagram. |
| AF-011 | **Context compressor.** One-shot Anthropic API call: input = transcript buffer (in-memory), output = ≤500-token structured Markdown summary written to `.orchestrator/context/<id>.ctx.md`. | TODO | AF-010 ✅ | Use claude-haiku-4-5 for cost efficiency. |
| AF-012 | **Gemini session boundary handling.** Verify that agy resets context cleanly on restart. Validate shadow tracking accuracy for Gemini sessions. Document any differences vs Claude session cycling. | TODO | AF-008 ✅ | Open question — needs empirical testing. |

---

## Validation Criteria

**Phase 1 → Phase 2 gate:** shadow/real token ratio ≥ 2× after 5+ sessions across 2+ projects.  
**Phase 2 → Phase 3 gate:** shadow/real ≥ 3× after 10+ sessions; token_scan.py detects real regressions in test fixture.  
**Phase 3 → Ship gate:** PTY wrapper tested on 3 real tasks without manual intervention; session cycling happens automatically at task boundary.
