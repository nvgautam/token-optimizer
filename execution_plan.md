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
Status: IN_PROGRESS
Architecture: architecture.md#oracle-design, architecture.md#orchestrator-design, architecture.md#handoff-flow
Goal: All provider skill files and prompt files exist and are testable via manual invocation.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-013 | Oracle prompts | T-001 | MERGED |
| T-014 | Worker prompts | T-001 | MERGED |
| T-015 | Reviewer + orchestrator prompts | T-001 | MERGED |
| T-025 | Handoff skill — provider files | T-001 | MERGED |
| T-026 | Oracle skill — provider files | T-013 | MERGED |
| T-027 | Orchestrator skill — provider files | T-015 | PENDING |

| Round | Tasks | Note |
|---|---|---|
| A | T-013, T-014, T-015, T-025 | All unblocked — run in parallel |
| B | T-026, T-027 | After Round A — T-026 needs T-013; T-027 needs T-015 |

Acceptance: `/oracle`, `/orchestrate`, `/handoff` skills invoke correctly in a new Claude session; all prompt files pass size and content assertions.

---

## Milestone 3: Config + PTY Shell
Status: PENDING — tasks decomposed when Milestone 2 completes
Architecture: architecture.md#config-schema, architecture.md#pty-shell-design
Goal: PTY overlay shell wraps `claude`/`gemini`, counts tokens locally, injects `/handoff` at threshold, restarts session.

Known scope: T-002 (config), T-006 (PTY wrapper), T-007 (tokenizer), T-008 (session manager + countdown)

| Round | Tasks | Note |
|---|---|---|
| A | T-002, T-006, T-007 | All unblocked — run in parallel |
| B | T-008 | After Round A — depends on T-002, T-006, T-007 |

---

## Milestone 4: Symbol Indexer
Status: PENDING — tasks decomposed when Milestone 3 completes
Architecture: architecture.md#symbol-indexer
Goal: Standalone CLI tool indexes project files; targeted symbol lookups return line ranges instead of full files.

Known scope: T-028 (parsers), T-029 (index manager + brownfield scanner)

| Round | Tasks | Note |
|---|---|---|
| A | T-028 | Parsers first |
| B | T-029 | After Round A — depends on T-028 |

---

## Milestone 5: Context Builder
Status: PENDING — tasks decomposed when Milestone 4 completes
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
