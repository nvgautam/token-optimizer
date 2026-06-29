# AgentFlow — Execution Plan

Oracle creates; orchestrator extends lazily at milestone boundaries.

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
Goal: All provider skill + prompt files exist; manually testable.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-013 | Oracle prompts | T-001 | MERGED |
| T-014 | Worker prompts | T-001 | MERGED |
| T-015 | Reviewer + orchestrator prompts | T-001 | MERGED |
| T-025 | Handoff skill — Claude | T-001 | MERGED |
| T-025g | Handoff skill — Gemini/AGY | T-001 | MERGED |
| T-026 | Oracle skill — provider files | T-013 | MERGED |
| T-027 | Orchestrator skill — Claude | T-015 | MERGED |
| T-027g | Orchestrator skill — Gemini/AGY | T-015 | MERGED |
| T-004g | AGENTS.md — Gemini/AGY | T-001 | MERGED |

| Round | Tasks | Note |
|---|---|---|
| A | T-013, T-014, T-015, T-025 | Parallel — all unblocked |
| B | T-026, T-027 | After A |

Acceptance: `/oracle`, `/orchestrate`, `/handoff` invoke correctly; prompt files pass size + content assertions.

**Addendum:**

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-032 | Orchestrator — dual-window rate pacing | T-027 | MERGED |
| T-033 | Orchestrator — variance-aware scheduling | T-032 | MERGED |
| T-034 | Oracle — CV feedback loop | T-026, T-033 | MERGED |
| T-035 | Oracle — remove CV notification | T-034 | MERGED |

M2 + addendum complete.

---

## Milestone 3: Symbol Indexer
Status: COMPLETE
Architecture: architecture.md#symbol-indexer
Goal: .idx generated inline (pre-spawn); workers use targeted reads; Python parsers follow validation.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-031 | Inline .idx generation in orchestrate skill | T-027 | MERGED |
| T-028a | Symbol index — Python parser | T-001, T-031 | MERGED |
| T-028b | Symbol index — Markdown parser | T-001, T-028a | MERGED |
| T-029 | Symbol index — index manager + brownfield scanner | T-001, T-028b | MERGED |
| T-036 | Targeted reads in orchestrate skill | T-031 | MERGED |
| T-037 | Targeted architecture reads in oracle skill | T-031 | MERGED |
| T-038 | CLAUDE.md — universal .idx reading protocol | T-036 | MERGED |

Note: json/yaml parsers dropped — .idx format is Python + Markdown only.

| Round | Tasks | Note |
|---|---|---|
| A | T-031 | Inline skill; validates empirically |
| B | T-028a | Python parser |
| C | T-028b | Markdown parser |
| D | T-029 | Index manager + brownfield scanner |
| E | T-036 | Targeted reads in orchestrate |
| F | T-037 | Targeted reads in oracle re-spar |
| G | T-038 | CLAUDE.md universal protocol |

---

## Milestone 4: Config + PTY Shell
Status: IN_PROGRESS
Architecture: architecture.md#config-schema, architecture.md#pty-shell-design

| Task | Title | Status |
|---|---|---|
| T-039 | Orchestrate — ledger-anchored rate cap | MERGED |
| T-040 | Oracle — general .idx protocol | MERGED |
| T-041 | PreToolUse hook — Read enforcement | MERGED |
| T-042 | Orchestrate — 5hr cap tz fix + low-n guard | MERGED |
| T-043 | Defer Python CLI tasks to backlog | MERGED |
| T-044 | orchestrate.md — startup index refresh + targeted reads | MERGED |
| T-045 | Shadow cost measurement (read_logger + analyzer) | MERGED |
| T-046 | PostToolUse hook — auto-regenerate .idx on Write/Edit | MERGED |
| T-047 | Oracle generation — telegraphic style rule | MERGED |
| T-048 | Compress state docs (design_status.md, execution_plan.md, tasks.json) | MERGED |
| T-049 | Compress skill files (oracle.md, orchestrate.md, handoff.md) | MERGED |
| T-007 | Local tokenizer — tiktoken cl100k_base | MERGED |
| T-006 | PTY wrapper — stdlib pty, I/O interception | MERGED |
| T-008 | PTY session manager — handoff, countdown, idx injection | MERGED |
| T-009 | CLI cmd_shell — PTY I/O relay loop | MERGED |
| T-010 | PTY — per-turn output tracking + verbosity signal | MERGED |
| T-052 | PTY session manager — Read-event idx injection + proactive verbosity banners | MERGED |

| Round | Tasks | Note |
|---|---|---|
| A | T-007 | No deps — first spawn alone |
| B | T-006 | Depends on T-007 |
| C | T-008 | Depends on T-006 |
| D | T-009 | Depends on T-008 |
| E | T-010 | Depends on T-009 |
| F | T-052 | Depends on T-008 — extends session_manager.py |
| G | T-051, T-054, T-055 | T-051: CLI integration tests; T-054: read_check.py enforcement; T-055: _pending_banner turn guard |

---

## Milestone 5: Context Builder
Status: DEFERRED — Python CLI out of scope for v1

| Task | Title | Status |
|---|---|---|
| T-030 | Context builder (Python) | DEFERRED → backlog.json |

---

## Deferred
- AgentFlow user-facing CLI (subcommands for config management, T-002): backlog.json
- Headless automation layer: v2
- Headroom CacheAligner integration: v2 — KV cache prefix stabilization; evaluate after PTY validated
- Headroom ContentRouter integration: v2 — tool output compression; plug into PTY I/O interception layer
- Codex provider: v2
- Brownfield refactoring: v2
- Automated merge sequencer: v2
- Tier/licensing: TBD
- PTY binary naming: TBD
