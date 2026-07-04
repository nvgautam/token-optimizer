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
Status: COMPLETE
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
| T-051 | CLI integration tests — argparse round-trip, main() dispatch, __main__ smoke | MERGED |
| T-054 | Enforce IDX targeted reads — read_check.py exit 1 blocker | MERGED |
| T-055 | Verbosity banner — generation-turn guard (should_inject_banner) | MERGED |

**Addendum:**

| Task | Title | Status |
|---|---|---|
| T-050 | Add agentflow/__main__.py — `python -m agentflow` entrypoint | MERGED |
| T-053 | Bug fixes: verbosity banner timing + absolute-path IDX guard | MERGED |
| T-056 | read_check.py: skip block on empty idx + compress output message | MERGED |
| T-057 | Reorganise skill dirs: commands/claude/ + commands/gemini/ | MERGED |
| T-058g | Align Gemini orchestrate and handoff skills with Claude equivalents | MERGED |
| T-058 | PostToolUse hook: block Write/Edit when file exceeds line limit | MERGED |
| T-059 | Bake verbosity target into skill prompts as standing instruction | MERGED |
| T-060 | Provider-keyed rate calibration files: Claude vs Gemini | MERGED |
| T-061 | Explore Gemini CLI hook equivalents for .idx reminder injection | MERGED |
| T-062 | UserPromptSubmit hook — .idx reminder injection (replaces PTY stdin) | MERGED |
| T-065 || MERGED |
| T-066 | PTY session_manager — ROUND_COMPLETE detection + token-floor handoff | MERGED |
| T-067 | PTY session_manager — per-task token bracketing → task_token_log.jsonl | MERGED |
| T-070 | read_check.py — block large-range reads that bypass idx enforcement | MERGED |
| T-071 | Evaluate headroom-ai library — integration feasibility for PTY + M5 | MERGED |
| T-073 | Fix verbosity signal reliability — incremental writes + reminder hook | MERGED |
| T-074 | Wire headroom-ai into PTY shell — `headroom wrap <provider>` at session start | MERGED |
| T-075 | Split agentflow.py (989 lines) into modules — retroactive 250-line enforcement | MERGED |
| T-076 | Size-limit enforcement gap — Gemini writes + pre-existing violations uncovered | MERGED |
| T-072 | `agentflow report` subcommand — combined savings dashboard across strategies | MERGED |
| T-077 | Spike — can headroom's proxy auto-capture 5hr/weekly usage windows? | MERGED |
| T-078 | Unify `agentflow report` / `python agentflow.py report` into one command (--mode session) | MERGED |
| T-079 | Harden gate-file reads against Headroom staleness — skill rule + invocation audit | MERGED |
| T-080 | ContentRouter mode default fix — cli.py sets HEADROOM_MODE=cache; tag-protect hook-injected reminders | MERGED |
| T-081 | A/B test verbosity control — measure real hook-off/hook-on baseline, replace assumed 600-token constant | MERGED |
| T-082 | Fix headroom compression data source in report_builder.py — SQLite store empty, real data in proxy_savings.json | MERGED |
| T-083 | Split shadow-waste vs real-savings labeling in report output | MERGED |
| T-084 | Recover headroom compression savings lost to cache mode's strict prefix freeze | MERGED |
| T-085 | Calibrate handoff/session-recycling savings from real ledger data, add as report line item | MERGED |
| T-086 | Move headroom-wrap toggle from ambient env var into AgentFlow config; add startup active/inactive banner | MERGED |
| T-087 | Add steady-state (post-regression-fix) savings percentage alongside lifetime total in report_builder.py | MERGED |
| T-088 | Surface index-driven read savings as its own report line item | MERGED |
| T-089 | Relabel Percentage Saved / Steady-State stats + reconcile windowing across all savings sources | MERGED — PR #52 merged 2026-07-03 |
| T-090 | Combine all four savings strategies into one reconciled overall percentage | MERGED — PR #53 merged 2026-07-03 |
| T-091 | Include compression savings in combined pct_saved headline | MERGED — PR #54 merged 2026-07-03 |
| T-092 | Dashboard: per-strategy growth rate tracking + projected savings | MERGED — PR #57 merged 2026-07-03 |

| Round | Tasks | Note |
|---|---|---|
| A | T-007 | No deps — first spawn alone |
| B | T-006 | Depends on T-007 |
| C | T-008 | Depends on T-006 |
| D | T-009 | Depends on T-008 |
| E | T-010 | Depends on T-009 |
| F | T-052 | Depends on T-008 — extends session_manager.py |
| G | T-051, T-054, T-055 | T-051: CLI integration tests; T-054: read_check.py enforcement; T-055: _pending_banner turn guard |

**Addendum rounds (pending):**

| Round | Tasks | Note |
|---|---|---|
| A | T-067, T-063, T-061, T-071 | T-067: unblocked (T-065/T-066 merged); T-063: independent; T-061/T-071: research spikes |
| B | T-068, T-064 | T-068 depends on T-067; T-064 depends on T-063 |
| C | T-069 | Depends on T-068 + T-065 (merged) |
| D | T-073 | No deps — independent bug fix |
| E | T-074, T-075 | Both independent, disjoint owns — highest priority: savings mechanism + tech debt |
| F | T-072, T-076 | T-072 depends on T-074 (ledger); T-076 independent |
| G | T-077 | Depends on T-074 (headroom must be wired first) |
| H | T-078 | Depends on T-072 (report_builder.py must exist) |
| I | T-079 | Depends on T-074 (headroom must be wired first) — oracle re-spar 2026-07-01 |
| J | T-082 | Independent bug fix — oracle re-spar 2026-07-02, combined_report.html anomalies |
| K | T-083 | Depends on T-082 |
| L | T-084 | Independent — oracle re-spar 2026-07-02, headroom compression regression traced to T-080's cache mode |
| M | T-085 | Independent — oracle re-spar 2026-07-02, handoff savings measurement approach resolved |
| N | T-086 | Independent — oracle re-spar 2026-07-02, headroom-wrap silently skipped due to ambient env-var dependency |
| O | T-087 | Depends on T-084, T-086 (needs their merge timestamps as the steady-state window start) — oracle re-spar 2026-07-02, blended lifetime pct_saved understates current capability for demo use |
| P | T-088 | Independent — oracle re-spar 2026-07-02, index-driven savings computed but never surfaced as its own report row |
| Q | T-089 | Independent — oracle re-spar 2026-07-02, session-recycling investigation: stale "lifetime" label + two unrelated stats presented as comparable |
| R | T-090 | Depends on T-089 (needs consistent windowing) — oracle re-spar 2026-07-02, no single number represents total savings across all four strategies |
| S | T-091 | Depends on T-090 — oracle re-spar 2026-07-03, pct_saved excluded compression_savings despite coherent shadow model |

---

## Milestone 5: Multi-Provider Coordination
Status: PENDING
Goal: Simultaneous Claude + Gemini orchestrators on the same project; each rate-aware; no task collision.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-063 | Cross-provider atomic task claiming — claimed_by + file lock | T-060 | PENDING |
| T-064 | Rate headroom check before claiming — skip if <10% window remaining | T-063, T-060 | PENDING |

| Round | Tasks | Note |
|---|---|---|
| A | T-063 | First — establishes claim protocol |
| B | T-064 | Depends on T-063 |

Acceptance: two simultaneous /orchestrate sessions (one Claude, one Gemini) on same tasks.json complete without duplicate task execution; rate-limited provider yields to the other.

---

## Milestone 6: Parallel Execution
Status: PENDING
Goal: Orchestrate spawns N workers in parallel per round, bounded by per-task token estimates; data collected from PTY task bracketing.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-068 | Per-task token estimator — regression model from task_token_log.jsonl | T-067 | PENDING |
| T-069 | Orchestrate — parallel worker scheduling using token estimator | T-068, T-065 | PENDING |

| Round | Tasks | Note |
|---|---|---|
| A | T-068 | Estimator first — needed by orchestrate skill |
| B | T-069 | Parallel scheduling; depends on estimator + signals |

Acceptance: orchestrate spawns multiple workers in one round without blowing session budget; owns fields verified disjoint; token estimator improves on 2500 constant after N≥5 samples.

---

## Milestone 7: Context Builder
Status: DEFERRED — Python CLI out of scope for v1

| Task | Title | Status |
|---|---|---|
| T-030 | Context builder (Python) | DEFERRED → backlog.json |

---

## Addendum: T-093 — Thin Owned Proxy (MERGED PR #55 2026-07-03)

| Task | Title | Status |
|---|---|---|
| T-093 | Replace headroom wrap with thin owned proxy | MERGED |

---

## Addendum: T-097 — Session-Recycling Savings (MERGED PR #60 2026-07-03)

| Task | Title | Status |
|---|---|---|
| T-097 | Session-recycling savings: windowed headline % + shadow-relative lifetime callout | MERGED bf59e5f |

---

## Addendum: T-094/T-095/T-096 — Savings Infrastructure (filed 2026-07-03)

| Task | Title | Status |
|---|---|---|
| T-092 addendum | Session recycling in sparklines/projections + per-strategy % breakdown | pending |
| T-094 | Automated verbosity A/B — PTY coin-flip + flag file + oracle tagging fix | MERGED 8ba2382 |
| T-095 | Post-compaction re-onboarding cost in shadow model | MERGED ac44480 |
| T-096 | Code-size savings as 5th dashboard strategy (git bootstrap + prospective family tracking) | MERGED 5fdfc18 |

---

## Addendum: T-098 — Model Routing Savings (filed 2026-07-04)

| Task | Title | Status |
|---|---|---|
| T-098 | Model Routing Savings — track USD and token-class savings in combined report | PENDING |

---

## Addendum: T-099 — Gemini Oracle Skill (filed 2026-07-04)

| Task | Title | Status |
|---|---|---|
| T-099 | Gemini Oracle Skill — create /oracle equivalent skill for Gemini | PENDING |

---

## Addendum: T-100/T-101/T-102/T-103 — Measurement Chain (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-100 | Per-strategy % of total_saved column in combined report | — | MERGED |
| T-101 | Tag verbosity_log.jsonl entries with arm at write time | — | MERGED |
| T-102 | Verbosity A/B stopping criterion — report signals when sufficient data collected | T-101 | PENDING |
| T-103 | Haiku vs Sonnet subagent A/B — measure output token delta from model routing | T-101, T-102 | PENDING |

---

## Addendum: T-104 — Size Enforcement Closure (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-104 | cleanup_tasks.py — auto-file split tasks from size_violations.jsonl | — | PENDING |

Not demo-critical — code quality enforcement only, deferred to Round D.

| Round | Tasks | What ships |
|---|---|---|
| A | T-100 | Per-strategy % breakdown (T-101 already merged — T-102 now unblocked) |
| B | T-102 | Verbosity A/B stopping criterion |
| C | T-103, T-099 | Model A/B + Gemini oracle skill (parallel) |
| D | T-098, T-063, T-104 | Model routing savings row + cross-provider claiming + size enforcement (parallel) |
| E | T-064, T-068 | Rate headroom + token estimator (parallel) |
| F | T-069 | Parallel worker scheduling |

Priority rationale (2026-07-04): investor demo + design-partner sequence. T-101 is critical path — arm tagging unblocks verbosity A/B, which gates T-103 (model A/B), which gates T-098 (model routing savings). 42-44% session-recycling headline is credible; verbosity methodology needs arm fix before pitch.

---

## Deferred
- AgentFlow user-facing CLI (subcommands for config management, T-002): backlog.json
- Headless automation layer: confirmed dead 2026-07-01 — oracle/orchestrator/worker/reviewer/tools API-mode subtree (includes M7/T-030's context builder) never wired into cli.py or any skill; see architecture.md "Deferred (v2)" section for the full file list. Not v1 scope; do not resume from this snapshot if ever revived.
- Local API observation proxy: v2 — stdlib HTTP proxy; ANTHROPIC_BASE_URL swap; logs exact usage fields from API responses; foundation for Caveman/Headroom integration
- Headroom CacheAligner integration: v2 — KV cache prefix stabilization; evaluate after PTY validated
- Headroom ContentRouter / Caveman integration: v2 — tool output compression; plug into PTY I/O interception layer (same ANTHROPIC_BASE_URL intercept as observation proxy)
- Codex provider: v2
- Brownfield refactoring: v2
- Automated merge sequencer: v2
- Tier/licensing: TBD
- PTY binary naming: TBD
