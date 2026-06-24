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

## Phase 2B — AgentFlow Package (Multi-Agent Project Manager)

> Full design in `architecture.md`. Implementation tasks in `tasks.json`. 16 tasks, 7 parallelism rounds.

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| T-001 | Package scaffold: pyproject.toml, entry points, subpackage structure | TODO | — | `pip install -e .` + `agentflow --help` |
| T-002 | Config system: layered loader, pydantic schema, defaults.yaml | TODO | T-001 | env → project → user → defaults |
| T-003 | Telemetry: structured JSON logger + OTel-compatible metrics | TODO | T-001 | JSONL to .agentflow/telemetry.jsonl |
| T-004 | Prompts: oracle, worker (+ testing_guide.md), reviewer (+ test_review.md) — all files under 150-line ceiling | TODO | T-001 | Independently versioned under prompts/v1/ |
| T-005 | Git tools: worktree create/delete/commit, no shell=True | TODO | T-001, T-002 | Typed exceptions, idempotent ops |
| T-006 | GitHub tools: PR create, inline comments, status checks via httpx | TODO | T-001, T-002, T-003 | Auth via GITHUB_TOKEN env only |
| T-007 | Test runner + file validator: pytest wrapper, coverage parse, size gate | TODO | T-001, T-002 | Returns structured TestResult |
| T-008 | Orchestrator DAG + state: dependency graph, state machine, state.json | TODO | T-001, T-002, T-003 | Ownership conflict = hard reject |
| T-009 | Contract generator: stub files, test skeletons, IO mock fixtures | TODO | T-001, T-002, T-005 | Committed to main before workers spawn |
| T-010 | Worker context builder: minimal bundle assembly, token metric | TODO | T-001, T-002, T-003, T-008 | Excludes everything not in owns/reads |
| T-011 | Headless worker agent runner: API loop, TDD, budget cycling | TODO | T-001–T-003, T-006, T-007, T-010, T-014 | Max 2 restarts before escalate |
| T-012 | Code reviewer agent: conformance + contract adherence, inline comments | TODO | T-001, T-002, T-003, T-006 | Not PR body — inline only |
| T-013 | Security reviewer agent: OWASP, secrets, compliance constraints | TODO | T-001, T-002, T-003, T-006 | CRITICAL findings block merge |
| T-014 | Token tracker: per-span attribution, budget enforcement, shadow model | TODO | T-001, T-002, T-003 | BudgetExceeded signal not exception |
| T-015 | Orchestrator PM + merge sequencer: full lifecycle, DAG-ordered merge | TODO | T-001–T-003, T-005, T-008, T-011–T-014 | State accurate through all transitions |
| T-016 | Design Oracle: conversation loop, checklist eval, Option B exit | TODO | T-001–T-004, T-009 | Produces architecture.md + tasks.json + contracts |

---

## Phase 2C — Claude Code Skill (Native Orchestration)

> Replaces the Python CLI orchestrator for large projects. Runs entirely within Claude Code using OAuth credentials — no API key required. Oracle, orchestrator, and workers are all Claude Code agents.

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| AF-015 | **Wire `handoff` as a CLI subcommand.** Currently `handoff` exists only as a direct `agentflow.py` command. Skills hardcode the path (`python /Users/gautam/code/token-optimizer/agentflow.py handoff`). Add `handoff` to `cli.py` as a proper subcommand so skills can call `agentflow handoff` regardless of where agentflow.py lives. Update both `oracle.md` and `orchestrate.md` to use the CLI command. Remove hardcoded path. | TODO | AF-013 ✅ | Hardcoded path breaks for any user other than nvgautam. |
| AF-014 | **Build step: produce clean packaged skill files.** Development skills (`oracle.md`, `orchestrate.md`) contain debug sections (grouping plan, overlap scores, `/orchestrate debug` option). Packaged distribution must be generated skill files with all debug sections stripped — no debug flag, no grouping rationale, no overlap scores, no reference to the existence of a debug mode. Implement as a build script that reads the dev skills and writes clean versions to a `dist/` directory. Packaged skills are what gets distributed; dev skills stay local only. | TODO | AF-013 ✅ | Grouping approach is proprietary — packaged files must contain no trace of debug capability. |
| AF-013 | **`/oracle` Claude Code skill.** `.claude/commands/oracle.md` skill that drives the full project lifecycle: checklist-driven design sparring (18 items incl. architecture security review) → task generation with `reads`+`owns`+`depends_on` → DAG-ordered grouped agent spawning (group by shared `reads` to minimise context reload cost) → per-task code+security review gates → topological merge. Shadow/real token tracking via worker self-reporting written to `.agentflow/telemetry.jsonl`. Retry-once on worker failure then escalate. | TODO | — | Primary token optimisation lever is grouping tasks by shared `reads` — eliminates redundant context reloads across agent spawns. |

---

## Phase 3 — PTY Orchestrator (build only after Phase 1 validates shadow/real ≥ 3×)

> See `AGENT_ORCHESTRATOR_PLAN.md` for full architecture.

| ID | Description | Status | Depends | Notes |
|---|---|---|---|---|
| AF-007 | **PTY scaffolding.** Fork target CLI (claude/agy/codex) into a PTY. Relay stdin/stdout transparently. Tab-switching UI (blessed/textual). Config: `.orchestrator/config.yaml`. | TODO | Phase 1 validated | Python `ptyprocess` or Node `node-pty`. |
| AF-008 | **Context reader plugins.** Per-tool plugin interface. Claude: read JSONL from `~/.claude/projects/`. Gemini: read SQLite from `~/.gemini/antigravity-cli/conversations/`. Return (current_ctx, ctx_limit) tuple. | TODO | AF-007 ✅ | Reuse JSONL/SQLite readers already in agentflow.py. Gemini protobuf schema documented in `docs/GEMINI_TOKEN_ACCESS_RESEARCH.md`. |
| AF-009 | **Task board watcher.** inotify/polling on `plan.md` (or `TASK_BOARD.md`). Detect status field changes: `done` → trigger compression + session cycle; `blocked` → surface question in notification bar. | TODO | AF-007 ✅ | Cross-platform: use `watchdog` Python lib. |
| AF-010 | **Session lifecycle manager.** On task DONE: call compressor → write `.orchestrator/context/<id>.ctx.md` → kill PTY → spawn fresh PTY with next task + context file injected as opening prompt. Emergency restart at 90% context mid-task. | TODO | AF-008 ✅, AF-009 ✅ | See AGENT_ORCHESTRATOR_PLAN.md §3 for lifecycle diagram. |
| AF-011 | **Context compressor.** One-shot Anthropic API call: input = transcript buffer (in-memory), output = ≤500-token structured Markdown summary written to `.orchestrator/context/<id>.ctx.md`. | TODO | AF-010 ✅ | Use claude-haiku-4-5 for cost efficiency. |
| AF-012 | **Gemini session boundary handling.** Verify that agy resets context cleanly on restart. Validate shadow tracking accuracy for Gemini sessions. Document any differences vs Claude session cycling. | TODO | AF-008 ✅ | Open question — needs empirical testing. |

---

## Validation Criteria

**Phase 1 → Phase 2 gate:** shadow/real token ratio ≥ 2× after 5+ sessions across 2+ projects.  
**Phase 2 → Phase 3 gate:** shadow/real ≥ 3× after 10+ sessions; token_scan.py detects real regressions in test fixture.  
**Phase 3 → Ship gate:** PTY wrapper tested on 3 real tasks without manual intervention; session cycling happens automatically at task boundary.
