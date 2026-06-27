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
Status: IN_PROGRESS
Architecture: architecture.md#config-schema, architecture.md#pty-shell-design
Goal: PTY overlay shell wraps `claude`/`gemini`, counts tokens locally, injects `/handoff` at threshold, restarts session.

Known scope: T-002 (config), T-006 (PTY wrapper), T-007 (tokenizer), T-008 (session manager + countdown), T-039 (ledger-anchored cap derivation), T-040 (oracle .idx protocol)

| Round | Tasks | Note |
|---|---|---|
| A | T-002, T-006, T-007, T-039, T-040 | All unblocked — run in parallel |
| B | T-008 | After Round A — depends on T-002, T-006, T-007 |

| Task | Title | Status |
|---|---|---|
| T-039 | Orchestrate skill — ledger-anchored rate cap | MERGED |
| T-040 | Oracle skill — general .idx protocol | MERGED |

---

## Milestone 5: Context Builder
Status: DEFERRED — not required for skills goal; needed for headless runner (v2) only

Architecture: architecture.md#context-bundle
Goal: `context_builder.py` assembles minimal per-task bundle using symbol index; orchestrate skill writes `context_bundle.md` to each worktree.

Known scope: T-030 (context builder)

| Round | Tasks | Note |
|---|---|---|
| A | T-030 | Depends on T-002, T-029 |

---

## Deferred
- Headless automation layer (agent_runner, write_file_tool, reviewer pipeline code): v2
- Codex provider: v2
- Brownfield file refactoring: v2
- Automated merge sequencer: v2
- Tier/licensing model: TBD
- PTY binary branding/naming: TBD
