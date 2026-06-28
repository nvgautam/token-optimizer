# AgentFlow — Execution Plan

Created by oracle at sparring completion. Parallelism rounds are oracle-defined (based on the dependency graph). Orchestrator groups adjacent tasks within a round by shared `reads` overlap (≥ 2 shared files) for token efficiency, then spawns one agent per group.

When a milestone completes, the orchestrator decomposes the next milestone's stub into full tasks in `tasks.json` and adds its parallelism rounds here.

---

## Milestone 1: Foundation
Status: COMPLETE
Architecture: architecture.md#module-boundaries

| Round | Tasks | Status |
|---|---|---|
| 1 | T-001 | MERGED |

---

## Milestone 2: Skill Files
Status: COMPLETE
Architecture: architecture.md#oracle-design, architecture.md#orchestrator-design, architecture.md#handoff-flow
Goal: All provider skill files and prompt files exist and are testable via manual invocation.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-013 | Oracle prompts | T-001 | MERGED |
| T-014 | Worker prompts | T-001 | MERGED |
| T-015 | Reviewer + orchestrator prompts | T-001 | MERGED |
| T-025 | Handoff skill — Claude provider | T-001 | MERGED |
| T-025g | Handoff skill — Gemini/AGY provider | T-001 | MERGED |
| T-026 | Oracle skill — provider files | T-013 | MERGED |
| T-027 | Orchestrator skill — Claude provider | T-015 | MERGED |
| T-027g | Orchestrator skill — Gemini/AGY provider | T-015 | MERGED |
| T-004g | Developer rules — Gemini/AGY provider (AGENTS.md) | T-001 | MERGED |

| Round | Tasks | Note |
|---|---|---|
| A | T-013, T-014, T-015, T-025 | All unblocked — run in parallel |
| B | T-026, T-027 | After Round A — T-026 needs T-013; T-027 needs T-015 |

Acceptance: `/oracle`, `/orchestrate`, `/handoff` skills invoke correctly in a new Claude session; all prompt files pass size and content assertions.

**Addendum:**

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-032 | Orchestrator skill — dual-window rate pacing | T-027 | MERGED |
| T-033 | Orchestrator skill — variance-aware scheduling | T-032 | MERGED |
| T-034 | Oracle skill — CV feedback loop | T-026, T-033 | MERGED |
| T-035 | Oracle skill — remove CV notification (IP protection) | T-034 | MERGED |

M2 + addendum fully complete. Skills goal achieved.

---

## Milestone 3: Symbol Indexer
Status: COMPLETE
Architecture: architecture.md#symbol-indexer
Goal: Orchestrate skill generates .idx files inline (pre-spawn) for task reads lists; workers use targeted reads to validate token savings empirically. Python parser modules follow after validation.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-031 | Inline .idx generation in orchestrate skill | T-027 | MERGED |
| T-028a | Symbol index — Python parser | T-001, T-031 | MERGED |
| T-028b | Symbol index — Markdown parser | T-001, T-028a | MERGED |
| T-029 | Symbol index — index manager and brownfield scanner | T-001, T-028b | MERGED |
| T-036 | Targeted reads in orchestrate skill — consume .idx files | T-031 | MERGED |
| T-037 | Targeted architecture reads in oracle skill — re-spar path | T-031 | MERGED |
| T-038 | CLAUDE.md — universal .idx reading protocol | T-036 | MERGED |

Note: json_parser and yaml_parser dropped — design_status.md resolves .idx format as Python + Markdown only (no JSON/YAML indexing).

| Round | Tasks | Note |
|---|---|---|
| A | T-031 | MERGED — inline skill changes; validates approach empirically |
| B | T-028a | MERGED — Python parser + IndexEntry type + init scaffolding |
| C | T-028b | MERGED — Markdown parser |
| D | T-029 | Index manager + brownfield scanner — depends on T-028b |
| E | T-036 | MERGED — targeted reads in orchestrate skill; consumes .idx instead of full files |
| F | T-037 | MERGED — targeted reads in oracle re-spar path; consumes architecture.md.idx instead of full file |
| G | T-038 | CLAUDE.md universal .idx reading protocol — one rule for all sessions; absent .idx = file < 50L, read in full |

---

## Milestone 4: Config + PTY Shell
Status: PARTIAL — skill tasks complete; Python CLI tasks deferred to backlog.json
Architecture: architecture.md#config-schema, architecture.md#pty-shell-design

| Task | Title | Status |
|---|---|---|
| T-039 | Orchestrate skill — ledger-anchored rate cap | MERGED |
| T-040 | Oracle skill — general .idx protocol | MERGED |
| T-041 | PreToolUse hook — Read enforcement | MERGED |
| T-042 | Orchestrate skill — 5hr cap tz fix + low-n guard | MERGED |
| T-043 | Defer Python CLI tasks to backlog | MERGED |
| T-044 | orchestrate.md — startup index refresh + targeted reads rule | MERGED |
| T-045 | Shadow cost measurement (read_logger + analyzer) | MERGED |
| T-046 | PostToolUse hook — auto-regenerate .idx on Write/Edit | MERGED |
| T-047 | Oracle generation — telegraphic style rule | PENDING |
| T-048 | Compress state docs (design_status.md, execution_plan.md, tasks.json) | PENDING |
| T-049 | Compress skill files (oracle.md, orchestrate.md, handoff.md) | PENDING |
| T-002 | Config system (Python) | DEFERRED → backlog.json |
| T-006 | PTY wrapper (Python) | DEFERRED → backlog.json |
| T-007 | Local tokenizer (Python) | DEFERRED → backlog.json |
| T-008 | PTY session manager + countdown (Python) | DEFERRED → backlog.json |

---

## Milestone 5: Context Builder
Status: DEFERRED — Python CLI out of scope for v1; task moved to backlog.json

| Task | Title | Status |
|---|---|---|
| T-030 | Context builder (Python) | DEFERRED → backlog.json |

---

## Deferred
- AgentFlow Python CLI package (config, PTY shell, tokenizer, session manager, context builder): backlog.json
- Headless automation layer (agent_runner, write_file_tool, reviewer pipeline code): v2
- Codex provider: v2
- Brownfield file refactoring: v2
- Automated merge sequencer: v2
- Tier/licensing model: TBD
- PTY binary branding/naming: TBD
