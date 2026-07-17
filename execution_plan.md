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
| T-068 | Per-task token estimator — regression model from task_token_log.jsonl | T-067 | MERGED (PR #103) |
| T-069 | Orchestrate — parallel worker scheduling using token estimator | T-068, T-065 | MERGED (PR #105) |

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
| T-102 | Verbosity A/B stopping criterion — report signals when sufficient data collected | T-101 | MERGED |
| T-103 | Haiku vs Sonnet subagent A/B — measure output token delta from model routing | T-101, T-102 | PENDING |

---

## Addendum: T-104 — Size Enforcement Closure (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-104 | cleanup_tasks.py — auto-file split tasks from size_violations.jsonl | — | MERGED |

Not demo-critical — code quality enforcement only, deferred to Round D.

## Addendum: T-105 — Arm Re-Read per Session Start (filed 2026-07-05)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-105 | session_manager — re-read arm file per session start, not just at init | — | MERGED |

Blocks T-102/T-103 data quality: long-lived shells never pick up new arm flips, producing untagged entries. Prepend to Round A.

| Round | Tasks | What ships |
|---|---|---|
| A | T-105, T-100 | Arm re-read fix (unblocks A/B data collection) + per-strategy % breakdown |
| B | T-102 | Verbosity A/B stopping criterion |
| C | T-103, T-099 | Model A/B + Gemini oracle skill (parallel) |
| D | T-098, T-063, T-104 | Model routing savings row + cross-provider claiming + size enforcement (parallel) |
| E | T-064, T-068 | Rate headroom + token estimator (parallel) |
| F | T-069 | Parallel worker scheduling |

Priority rationale (2026-07-04): investor demo + design-partner sequence. T-101 is critical path — arm tagging unblocks verbosity A/B, which gates T-103 (model A/B), which gates T-098 (model routing savings). 42-44% session-recycling headline is credible; verbosity methodology needs arm fix before pitch. T-105 added 2026-07-05: long-lived shell sessions don't re-read arm at session restart — fix must land before A/B data is valid.

---

## Addendum: T-106 — AgentFlow Session Identity (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-106 | PTY session identity — env var + session file for deterministic AgentFlow detection | T-105 | MERGED |

PTY generates UUID at launch → sets `AGENTFLOW_SESSION_ID=<uuid>` env var + writes `~/.agentflow/sessions/<uuid>.json` with `{arm, session_type, started_at}`. Hooks read env var and append `session_id` to verbosity_log.jsonl entries. Enables: (1) deterministic "is AgentFlow session?" check, (2) retrospective session→arm mapping, (3) clean join between session metadata and log entries. Prepend to Round B (after T-105 merges).

| Round | Tasks | What ships |
|---|---|---|
| A (MERGED) | T-105 | Arm re-read fix |
| B (MERGED) | T-106, T-102 | Session identity + verbosity A/B stopping criterion |
| C | T-107, T-108 | PTY auto-trigger fixes (sequential within round) |
| D | T-103, T-099, T-098, T-068 | Model A/B + Gemini oracle + routing savings + token estimator (parallel; T-103 needs T-102✓) |
| E | T-063, T-104 | Cross-provider claiming + size enforcement (parallel) |
| F | T-064, T-069 | Rate headroom + parallel scheduling (deps: T-063, T-068) |

---

## Addendum: T-115 — Capacity Calibration (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-115 | Capacity calibration — tasks-per-5hr-window as scheduling primitive | — | MERGED |

Replace unreliable raw-token 5hr cap with percentage-based capacity model: track 5hr window % consumed per task, EWMA of % per task, derive `tasks_remaining = floor(current_pct / ewma_pct_per_task)`. Orchestrate reads this before each spawn. Complements T-068 (token regression) — this tracks rate-limit headroom, not token count. Round D.

---

## Addendum: T-114 — Code Review Pass 2 Model Upgrade (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-114 | Code review Pass 2 — route to Sonnet unconditionally, not Haiku | — | MERGED |

Cross-tier review: Haiku-implemented → Sonnet reviewer; Sonnet-implemented → Haiku reviewer. Human gate backstops cases where Haiku misses subtle issues in Sonnet output. Update orchestrate.md Pass 2 spawn block to read implementing agent model and select reviewer accordingly. Round C.

---

## Addendum: T-113 — PTY Stale Index Guard (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-113 | PTY stale index guard — detect and rebuild .idx files when source file is newer | — | MERGED |

At session start, PTY walks `~/.agentflow/cache/<hash>/index/` and compares mtime of each `.idx` against its source file. Stale or missing `.idx` files are queued for rebuild via indexer CLI. Also: audit write_indexer hook registration to ensure no file writes are missed (e.g. files edited outside Claude Code). Prevents stale-idx bugs where oracle/worker reads ghost content from a prior file version. Round C (alongside T-107).

---

## Addendum: T-107 + T-108 — PTY Auto-Trigger Fixes (filed 2026-07-04)

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-107 | PTY auto-trigger bug: `_manual_handoff` never resets on `/clear` + add pty_audit.jsonl state machine logging | T-105 | MERGED |
| T-108 | `AGENTFLOW_ROUND_COMPLETE` never fires: investigate emission gap in orchestrate skill + fix | T-107 | MERGED |

**T-107:** Add `self._manual_handoff = False` to `/clear` detection block (session_manager.py:78–90). Add `pty_audit.jsonl` event log capturing: `_manual_handoff` set/reset, token threshold evaluations, `trigger_handoff` calls (auto vs manual), `_restart_session` calls, session_type transitions, `/clear` detections. Round A.

**T-108:** Two fixes: (1) Zero `AGENTFLOW_ROUND_COMPLETE` events in verbosity_log.jsonl — orchestrate skill never emits this signal; audit and add emission after PR filed + human gate passed. (2) Orchestrate startup missing Step 4b — add: read round table → identify first round with all PENDING tasks and satisfied deps → announce "Picking up Round X: T-xxx" → proceed without prompting. Depends on T-107. Round A.

---

## Milestone 8: IP Protection
Status: PENDING
Goal: Design partner-safe distribution — skills encrypted, PTY compiled, key server live.

| Task | Title | Depends on | Status |
|---|---|---|---|
| T-109 | Key server — auth + ephemeral key issuance + encrypted skill serving | — | MERGED |
| T-110 | Skill encryption pipeline — encrypt all skill .md files at rest, bundle with binary | T-109 | MERGED |
| T-111 | PTY — fetch + decrypt skills at session start; generate skill .idx ephemerally in memory, never on disk | T-110 | MERGED |
| T-112 | Nuitka compilation — compile PTY + hooks into binary; smoke-test distribution | T-111 | MERGED |

**Pre-condition (business, not engineering gate):** File provisional patent on targeted-read method (USPTO, ~$320) before onboarding any design partner.

**Design partner package:** compiled binary + NDA. No source, no plaintext skills, no .idx for skills on disk.

| Round | Tasks | What ships |
|---|---|---|
| D (master) | T-109 → T-110 → T-111 → T-112 (sequential within round) | Full IP protection stack |

---

## Master Round Table (updated 2026-07-10)

| Round | Tasks | What ships |
|---|---|---|
| A–C (MERGED) | T-105,T-106,T-102,T-107,T-108,T-113,T-114,T-115 | PTY fixes + measurement chain |
| D (MERGED) | T-116, T-117, T-109 | PTY handoff non-blocking + robustness + key server |
| D2 (MERGED) | T-118 ‖ T-110 (parallel), then T-111→T-112 (sequential) | PTY state machine refactor + IP protection stack |
| D3-prep | T-139 ‖ T-140 (MERGED) ‖ T-142 (parallel), then T-141 (MERGED) | Size splits — unblocks T-121 + T-122 from touching session_manager.py cleanly |
| D3 | T-121 (MERGED) ‖ T-122 ‖ T-125 ‖ T-120 (parallel) | PTY robustness (deadlines + ANSI reset + stdin gating + T-118 corrections) + regression tests + pty_signal + installer |
| D3-fix (P0) — MERGED | T-148 | PTY stdin \n→\r fix — commands submit instead of sitting idle; automated orchestrate loop unblocked |
| D3-restart | T-149 (MERGED) ‖ T-150 (MERGED) (parallel), then T-151 (MERGED), then T-152 (MERGED) | Restart-storm fixes — stale signal clear + accumulator reset + trigger simplification + hook guard |
| D3-156 — MERGED | T-156 | PostToolUse Agent hook — auto task_done signal backstop |
| D3-auto-1 — MERGED | T-155 (MERGED) | PTY session_type detection — oracle vs orchestrate threshold routing; must land before T-159 |
| D3-auto-2 — MERGED | T-161 (MERGED) | PostToolUse hook — auto-detect merged PRs, update tasks.json (flock), invoke cleanup_tasks.py; makes handoff chain deterministic |
| D3-auto-3 — MERGED | T-159 (MERGED) | PTY handoff_handler.py session_type branch — fires correct restart path on orchestrate threshold hit |
| D3-prep-cont-b | T-158 (MERGED) | Stale tasks_in_flight reconcile |
| D3-prep-cont-c — MERGED | T-139 (MERGED) ‖ T-142 (MERGED) ‖ T-145 (MERGED) | Size splits — unblocks D3b |
| D3-durability — MERGED | T-157 (MERGED) | CLAUDE.md post-merge checklist — prevents skill/config losses on branch diverge |
| D3-oracle — MERGED | T-153 (MERGED) ‖ T-154 (MERGED) | Oracle threshold config + incremental design_status flush |
| D3b (MERGED) | T-122 ‖ T-120 ‖ T-112 ‖ T-147 ‖ T-160a ‖ T-163 (parallel) | Regression tests + installer + Nuitka binary + cache breakpoint + verbosity boundary fix + auto-capture /usage |
| D3c — MERGED | T-184 ‖ T-185 (parallel) | Stop hook → transcript fill tokens → accurate PTY restart threshold + session state per-sid — unblocks auto-orchestrate loop + fixes session poisoning |
| D3d (P0) — MERGED | T-186 | Replace PTY /clear string match with UserPromptSubmit hook signal — eliminates false session resets |
| D3e (P0) — MERGED | T-187 (depends T-186) | PTY restart when tasks_in_flight drains empty + context ≥ 80K — closes auto-restart gap after PR merge cleanup |
| D3b-2 — MERGED (PR #102 2026-07-10) | T-160 (depends T-160a) ‖ T-164 (depends T-163) (parallel) | Verbosity A/B metrics + calibrate_capacity() wiring + ewma_cv |
| P0 — MERGED (PR #104 2026-07-10) | T-188 | cleanup_tasks.py PR merge detection + tasks_in_flight drain + conditional audit log — unblocks reliable PTY restart loop |
| Demo-1 — MERGED (PR #103 2026-07-10) | T-068 | Token estimator (regression model from task_token_log) — unblocks Demo-2 |
| Demo-2 — MERGED (PR #105 2026-07-10) | T-069 (T-064 deferred — blocked by T-063) | Parallel scheduling via task_estimator + disjoint owns check |
| P0-restart — MERGED (PR #106 2026-07-10) | T-189 | PTY restart storm hotfix — context_fill reset + 30s cooldown + session_type re-sync + 1.5s delayed inject |
| Demo-3 (MERGED PR #109 2026-07-11) | T-098 ‖ T-103 (parallel) | Combined savings report (USD + token-class) + Haiku vs Sonnet A/B — proves token reduction |
| P0-session-type — MERGED (PR #110 2026-07-11) | T-191 | Deterministic session_type via UserPromptSubmit hook — eliminates output-text heuristic misclassification |
| P0-pty-restart — MERGED (PR #111 2026-07-11) | T-194 | Fix init TASK_RUNNING oracle contamination — gate on orchestrator session_type |
| P0-pty-restart-2 — MERGED (PR #112 2026-07-11) | T-195 | Replace _delayed_inject with initialPrompt spawn mechanism |
| P0-context-fill — MERGED (PR #114 2026-07-11) | T-198 | PostToolUse hook writes context_fill.json mid-turn — fixes drain check reading stale fill from previous turn, unblocks reliable 80K restart |
| Spike — MERGED (PR #115 2026-07-12) | T-190 | Session isolation design — per-SID volatile state folder; yields 8 implementation tasks T-200–T-207 |
| split-1 — MERGED (PR #113 2026-07-11) | T-192 | Split test_report_builder.py (size violation) |
| split-2 — MERGED (PR #116, #117 2026-07-12) | T-197 ‖ T-187 (parallel) | Split report_builder.py + session_manager.py — size violations |
| t196-spawn-ctx — MERGED (PR #119 2026-07-12) | T-196 | Pre-resolve task context into orchestrate initialPrompt — eliminates worker startup re-derivation (depends T-195, already merged) |
| restart-deterministic — MERGED (PR #121 2026-07-14) | T-209 | Orchestrate drain restart — direct RESTARTING path, no output parsing |
| session-iso-1 — MERGED (PR #122 2026-07-14) | T-200 | Add _session_file() path helper (foundation for T-201–T-207) |
| gemini-quality | T-213 (MERGED) ‖ T-214 (MERGED) | Fix AGENTS.md dead paths + flatten Gemini model to gemini-2.5-flash — unblocks reliable Gemini orchestrate |
| session-iso-2 — MERGED (PR #128 2026-07-14) | T-201 ‖ T-203 (parallel) | Migrate context_fill + session_state writes to per-SID paths (depends T-200) |
| session-iso-4 — MERGED (PR #128 2026-07-14) | T-205 | Update handoff skill for per-SID handoff docs (depends T-200) |
| spike-restart-det — MERGED (PR #128 2026-07-14) | T-215 | Audit restart signal chain — catalogue every stdout/LLM-call dependency before session-iso-3 ships |
| session-iso-2c — MERGED (PR #129 2026-07-14) | T-216 | SID-scope task_complete.json — PTY path property + pty_signal writer + poll_session reader |
| session-iso-2d — MERGED (PR #130 2026-07-15) | T-218 | SID-scope current_round.json mtime guard via SID content validation (depends T-216 — shared session_manager.py) |
| session-iso-2e | T-217 — MERGED PR #131 2026-07-15 | SID-scope tasks_in_flight.json — all hook writers + drain reader + session_manager property (depends T-218 — shared handoff_handler.py) |
| session-iso-2f — MERGED PR #135 2026-07-15 | T-219 | Fix context_fill.json reset in _clear_signal_files (SID path) + staleness check in check_drain_restart (depends T-217 — shared handoff_handler.py) |
| session-iso-misc — MERGED PR #132,#133,#134 2026-07-15 | T-220 ‖ T-221 ‖ T-222 | Fix handoff.md doc drift + compress.py _is_mid_round() SID callsite + split test_post_tool_use_agent.py |
| session-iso-2g — MERGED (PR #136 2026-07-15) | T-223 | Hook-driven task_start via PreToolUse Agent + fix drain paths (gh pr view race, SID path, outside-CLI merge) |
| session-iso-3 — MERGED (PR #137/#138/#139 2026-07-15) | T-202 ‖ T-204 ‖ T-207 (parallel) | Migrate reads, threshold_sync, stale cleanup (depends session-iso-2f, T-200, T-201, T-203) |
| observability-1 — MERGED (PR #142/#143 2026-07-16) | T-225 ‖ T-226 (parallel) | Shell + hook exception handlers — replace silent except:pass with structured audit log / stderr JSON entries |
| observability-2 — MERGED (PR #144 2026-07-16) | T-227 (depends T-225) | session_type determination — remove root-level fallback when SID present, TDD all edge cases |
| A — MERGED (PR #147/#146 2026-07-16) | T-228 ‖ T-230 (parallel) | Atomic merge sync + orchestrator worktree lifecycle — closes two orthogonal orchestrate reliability gaps |
| B — MERGED (PR #149/#148 2026-07-16) | T-229 ‖ T-232 (parallel) | Flock on shared files + PostToolUse merge-detection hook — deterministic state sync on PR merge |
| C1 — MERGED (PR #150/#152 2026-07-16) | T-237 ‖ T-242 (parallel) | Session restart reliability: new-SID re-derive on restart + multi-PR drain fix (re.findall) + replace 30s poll log with drain_start/complete/timeout events |
| C2 — MERGED (PR #153 2026-07-16) | T-231 | SQLite migration: replace tasks.json with WAL-mode SQLite; atomic writes; eliminate oracle/hook write collisions; drop flock — TOP PRIORITY |
| C2b — MERGED (PR #154 2026-07-16) | T-247 | Fix drain bugs: session_type mismatch in post_tool_use.py (`"orchestrate"` → `"orchestrator"`, T-232 regression) + title-match regex in user_prompt_submit.py + post_tool_use_agent.py (`feat(T-N):` format fails). Must land before C3 — all parallel tasks depend on drain working correctly. |
| C3a — drain test — MERGED | T-244 (solo) | Remove EnterWorktree dependency from worker skill — verifies T-247 drain fix end-to-end; enough context to cross 80K restart threshold |
| C3b-pilot — MERGED | T-233 ‖ T-238 (parallel) | Verbosity rule (never narrate internal mechanics) + /debug skill — two independent tasks to validate parallel drain/restart |
| C3b-fix — MERGED (PR #158 2026-07-16) | T-251 (solo) | SQLite round table migration + write MERGED in check_drain_restart + clear active_round/active_tasks on drain — fixes PTY-kills-before-cleanup gap |
| C3b-hotfix — MERGED (PR #159 2026-07-16) | T-256 (solo) | Delete tasks_in_flight.json in _write_merged_and_clear after drain — fixes restart loop caused by stale [] tombstone |
| C3b-cleanup — MERGED (PR #160 2026-07-17) | T-253 (solo) | Remove file-based round/state cleanup dead code — depends T-251 verified |
| C3b-restart-test — MERGED (PR #161/#162 2026-07-17) | T-246 ‖ T-252 (parallel) | Restart validation run: test_post_tool_use_agent.py split + remove dead HANDOFF RECOMMENDED emit — verifies drain→restart chain end-to-end |
| C3b-tif-repro — MERGED (18fd947b1 2026-07-17) | T-257 (solo) | Failing test: Bash-written current_round.json does not populate tasks_in_flight.json — pins the regression before fix |
| C3b-tif-fix — MERGED (PR #163 2026-07-17) | T-258 (solo) | Self-healing fallback in sync_tasks_in_flight: read current_round.json from disk when tif absent after Bash call |
| C3b-splits — MERGED (PR #164/#165 2026-07-17) | T-262 ‖ T-263 (parallel) | Size-violation splits: handoff_handler.py (T-262) + post_tool_use.py / fill_utils.py (T-263) |
| C3b-restart-paths | T-264 ‖ T-265 (parallel) | Simplify restart paths: Path 1 never restarts (rename check_tokens→task_round_complete, always→IDLE, remove guard_tokens_threshold) + remove dead _handoff_in_progress setter (Path 3) |
| C3b-worker-guard — MERGED | T-261 (solo) | Hard guard: orchestrate must always dispatch a worker — never implement directly; runtime audit check + test |
| Round A — MERGED (PR #167/#168 2026-07-17) | T-269 ‖ T-264 (parallel) | Fix premature drain restart (clear current_round.json after merge) + simplify Path 1 restart — unblocks stable orchestrate startup |
| Round B — MERGED (PR #169/#170 2026-07-17) | T-265 ‖ T-267 (parallel) | Remove dead _handoff_in_progress setter (Path 3) + oracle.md opinionated-expert note |
| Round C-splits — MERGED (PR #171/#172 2026-07-17) | T-271 ‖ T-270 (parallel) | Size-violation splits: cleanup_tasks.py → cleanup_violations.py + user_prompt_submit.py → ups_task_sync.py |
| Round C-P0 (solo) — MERGED (PR #173 2026-07-17) | T-274 | Fix check_drain_restart: accept TIF=[] tombstone as equivalent to current_round.json — T-269 regression blocks all drain restarts |
| Round C-P1 (solo) | T-273 | Fix SID path bugs: pty_signal handoff_complete, shell/cleanup_tasks task_complete, user_prompt_submit delete, tools/cleanup_tasks TIF — all use flat paths instead of session_file()/SID-in-filename |
| Round C | T-162 ‖ T-210 ‖ T-243 ‖ T-250 ‖ T-266 ‖ T-268 (parallel) | oracle.md split + test cache fix + auto-mode default + debug.md KeyError + debug.md 5-phase rewrite + oracle duplicate-check |
| Round C | T-259 → T-260 ‖ T-234 ‖ T-236 (T-259 first, then parallel) | CLI spike → round-start CLI + context bundle temp file + conflict resolution |
| Round D | T-178 ‖ T-211 (parallel) | Hook audit log spike + Gemini lifecycle spike |
| Round E | T-167 ‖ T-168 (parallel) | Oracle Phase 3 plan-mode preview + product judgment layer |
| Round F | T-063 → T-064 → T-099 (sequential) | Multi-provider chain (enterprise) |

Priority rationale (2026-07-17): T-274 (P0) + T-273 (P1) prepend Round C — both block reliable orchestrate restart loop. Restart-path hardening (A/B) before skill rewrites — loop reliability prerequisite. CLI spike (T-259) gates T-260. Rounds D–E are spikes/oracle enhancements. Round F deferred until Claude-only loop is solid.

---

## Milestone M-DP: Demo & Design Partner Package
**Goal:** Deliver a working demo and distributable package to design partners.
**Focus:** Orchestrate loop must be hands-off + predictable. Gains measurable. Package installable on a clean machine.

### Deliverables
| # | Deliverable | Key tasks |
|---|---|---|
| 1 | Reliable orchestrate loop | Auto handoff + session restart working end-to-end (fixes shipped 2026-07-08), E2E regression test (T-165), capacity wiring (T-164) |
| 2 | Parallelization + savings measurement | Worker-token spike (T-166), verbosity A/B metrics (T-160), proxy SSE response parser (T-171) |
| 3 | Headroom gains measured | SSE parser (T-171), headroom A/B arm (T-172), proxy_log.jsonl covers input + output + cache |
| 4 | IP protection | Encryption/decryption (T-111 complete, T-120 installer pending) |
| 5 | Design partner package | Install script + README + binary bundle (T-173, depends T-120) |

### M-DP Round Table
| Round | Tasks | What ships |
|---|---|---|
| DP-1 — MERGED | T-165 ‖ T-160 (parallel) | Orchestrate loop E2E test + verbosity metrics |
| DP-2 — MERGED | T-171 ‖ T-166 (parallel) | SSE response parser + worker-token measurement |
| DP-2b — MERGED | T-177 (MERGED), T-176 (MERGED) | Deterministic session_type via hook + stall recovery — engine reliably restarts |
| DP-3 — MERGED | T-120 (MERGED PR #89), T-179 (MERGED PR #90) | PTY installer (+ cli.py split) + proxy/server.py split |
| DP-3c — MERGED | T-180 (MERGED PR #91) | PR URL registry — deterministic merge detection via gh pr view (fixes cleanup stall) |
| DP-3b — MERGED | T-172 (MERGED PR #92) | Headroom A/B arm |
| DP-3d — MERGED | T-181 (MERGED PR #93) | UserPromptSubmit cleanup hook + remove orchestrate handoff-inject (fixes spurious /handoff during cleanup) |
| DP-4 — MERGED | T-173 (MERGED PR #95) | Design partner package |
| DP-5 — MERGED (T-169 PR #96, T-170 PR #97) | T-169 ‖ T-170 (parallel, optional) | Orchestrate startup cost reduction (nice-to-have before demo) |
| DP-post | T-162, T-164, T-175, T-178 | oracle.md split + capacity wiring + session_manager split + hook audit log |

---

## Addendum: T-180 — PR URL registry + deterministic merge detection (filed 2026-07-09)
**Round:** DP-3c (before DP-3b)
**Problem:** `post_tool_use_agent.py` title-match heuristic fails for conventional-commit PR titles (e.g. `feat(T-120):` — `T-120:` not found as substring). Tasks remain in `tasks_in_flight.json` after merge; cleanup never fires.
**Fix:** Write `{task_id: pr_url}` to `.agentflow/task_prs.json` when `gh pr create` runs; use `gh pr view <url> --json state` for authoritative MERGED check. Title match kept as fallback for tasks with no registered URL.
**Owns:** `agentflow/hooks/post_tool_use_agent.py`, `tests/hooks/test_post_tool_use_agent_pr_registry.py`

---

## Addendum: T-116 — PTY Non-Blocking Handoff (filed 2026-07-04)

| Field | Value |
|---|---|
| Task | T-116 |
| Title | PTY trigger_handoff non-blocking — move handoff wait+countdown off main event loop |
| Files | agentflow/shell/session_manager.py, tests/shell/test_session_manager.py |
| Est. lines | 40 |
| Status | MERGED |

`trigger_handoff()` blocks the main select loop: up to 120s waiting for HANDOFF_COMPLETE + 5s countdown. Stdin is not forwarded during this window → shell unresponsive. Fix: daemon thread handles the wait + countdown + restart injection; main loop continues relaying I/O. Thread sets `_handoff_in_progress=True` before start, clears on completion. Stdlib threading only.

## Addendum: T-117 — PTY Handoff Robustness (filed 2026-07-05)

| Field | Value |
|---|---|
| Task | T-117 |
| Title | PTY handoff robustness — dead-PTY failure modes and repeated-output symptom |
| Files | agentflow/shell/session_manager.py, tests/shell/test_session_manager.py |
| Est. lines | 55 |
| Status | MERGED |

User-reported: after handoff fires, PTY "broke out of the shell" and the same number printed repeatedly. Five fixes: (1) investigate audit log for exact event sequence; (2) break inner read loop immediately if `_pty._exited` becomes True (currently busy-spins 120s on dead fd); (3) wrap `write_input("/clear\n")` and restart injection in try/except OSError (EIO on dead master_fd currently propagates unhandled through `_on_output` to cli.py's main loop); (4) forward chunks from inner read loop to stdout so user sees handoff progress; (5) on unexpected PTY exit during handoff, log `handoff_aborted` audit event and reset `_handoff_in_progress` without attempting `/clear` or countdown. Complements T-116 (blocking) — orthogonal fixes.

---

## Addendum: T-118 — PTY State Machine Refactor (filed 2026-07-05)

**Status:** MERGED

**Goal:** Replace flag-soup session_manager.py with explicit state machine; all signals file-based, no timers.

**States:** `IDLE → TASK_RUNNING → TASK_COMPLETE → HANDOFF_PENDING → RESTARTING → IDLE`; `DEAD_CHILD` recovery from any state.

**File signals:**
- `current_round.json` written by orchestrate → TASK_RUNNING
- `.agentflow/task_complete.json` written by cleanup_tasks.py → TASK_COMPLETE
- tokens ≥ 80K (PTY local measurement) → HANDOFF_PENDING
- `.agentflow/handoff_complete.json` written by agentflow.py handoff → RESTARTING
- PTY master fd EOF (select) → DEAD_CHILD

**Session restart:** `os.kill(SIGTERM)` → `os.waitpid` poll → `SIGKILL` if alive after 2s → fresh `subprocess.Popen`. No timers.

**Files:** `agentflow/shell/state_machine.py` (new, ~100L), `agentflow/shell/session_manager.py` (refactor, net reduction), `agentflow/shell/cleanup_tasks.py` (add signal write), `agentflow/handoff.py` (add signal write), `tests/shell/test_state_machine.py` (new), `tests/shell/test_session_manager.py` (update).

**Depends on:** T-116, T-117 (MERGED). Blocks T-111 (modifies session_manager.py). Runs parallel with T-110 (disjoint files).

## Addendum: T-120 — PTY installer: hook merge + binary-relative commands (filed 2026-07-05)

**Goal:** Safe hook registration in customer environments at install time; no customer config clobbered.

**Files:** `agentflow/ip/installer.py` (new, ~80L), `agentflow/cli.py` (add `install`/`uninstall`/`hooks` subcommands), `tests/ip/test_installer.py`.

**Protocol:** `agentflow install` reads `~/.claude/settings.json`, deep-merges agentflow hook entries (idempotent: command-string match), writes atomically via `os.replace`. `agentflow uninstall` removes only agentflow entries. Hook commands in installed config reference binary: `agentflow hooks <name>` — Nuitka binary dispatches internally. Dev `settings.json` (tracked in git) keeps `$CLAUDE_PROJECT_DIR` paths unchanged.

**Depends on:** T-112 (binary must exist before hook commands can reference it).

## Addendum: T-119 — UserPromptSubmit jailbreak hook (filed 2026-07-05, subtask of T-111)

**Goal:** Block known extraction/jailbreak prompts before they reach Claude, as defense-in-depth alongside T-111's meta-instruction preamble.

**Why hook, not stdin filter:** UserPromptSubmit fires on the complete submitted message — not raw keystrokes. Consistent with existing hook pattern (read_check.py, verbosity_reminder.py). Non-zero exit blocks the message from reaching Claude.

**Files:** `agentflow/hooks/jailbreak_check.py` (new, ~60L), `tests/hooks/test_jailbreak_check.py` (new). Register in `.claude/settings.json` under `hooks.UserPromptSubmit`.

**Protocol:** Fuzzy case-insensitive match. On match: exit non-zero + write `{ts, pattern_matched, raw_input}` to `.agentflow/sanitizer_blocked.jsonl`. On clean: exit 0. Stdlib only. Ships with T-111.

## Addendum: T-121 — PTY Robustness: Deadlines + ANSI Reset + Stdin Gating + T-118 Corrections (revised 2026-07-06g)

**Goal:** Guarantee agentflow never hangs and doesn't corrupt terminal state on session restart. Simplified from original spec — kqueue/inotify reactor removed; 50ms select() polling is sufficient.

**Per-state deadlines (transitional states only):** Each state transition records `entered_at = time.monotonic()`. The `select()` timeout branch checks elapsed time; on expiry: SIGKILL child → IDLE. Deadlines: `TASK_COMPLETE` 30 s, `HANDOFF_PENDING` 90 s, `RESTARTING` 30 s, `DEAD_CHILD` 10 s. **No deadline on `TASK_RUNNING`** — process liveness (`waitpid(child_pid, WNOHANG)`) is the correct signal; activity-based timers are unreliable (model inference + tool execution produce long silent periods).

**T-118 correction 1 — handoff_complete.json writer:** `agentflow/handoff.py` must write this file atomically; implementation scrapes `"HANDOFF_COMPLETE"` from PTY output instead. Fix: add atomic write to `agentflow/handoff.py`; remove output-scraping fallbacks from `session_manager.py`.

**T-118 correction 2 — test/production divergence:** `trigger_handoff()` routes through blocking `_run_handoff_loop` in pytest vs `poll()` in production — tests never exercise the production path. Fix: remove `_run_handoff_loop`; tests drive `poll()` directly.

**T-143 fold-in — ANSI state reset:** Complete `on_enter_restarting` stub in `state_machine.py`: emit `\x1b[0m` (SGR reset) to stdout so dirty terminal state from the dead session does not bleed into the new child.

**T-144 fold-in — stdin gating:** In `cli.py` stdin forwarding loop, skip `os.write(wrapper.master_fd, chunk)` when `session_manager._state_machine.state == States.RESTARTING`. No timer — state is the gate.

**Files:** `agentflow/shell/session_manager.py`, `agentflow/shell/state_machine.py`, `agentflow/handoff.py`, `agentflow/cli.py`, `tests/shell/test_session_manager.py`.

**Estimated lines:** ~80L total change.

**Depends on:** T-118 (MERGED). T-112 dependency removed. Slots top of Round D3.

## Addendum: T-139–T-142 — Size violation splits, deduplicated (filed 2026-07-06c)

**Root cause:** T-104's cleanup_tasks.py lacked deduplication — each PostToolUse write event appended a new split task, generating 16 duplicate entries (T-122–T-137). T-138 fixes the bug. These 4 tasks replace all 16.

| Task | File | Lines | Limit |
|---|---|---|---|
| T-139 | commands/claude/orchestrate.md | 239 | 150 |
| T-140 | agentflow/shell/session_manager.py | 564 | 250 |
| T-141 | tests/shell/test_session_manager.py | 390 | 350 |
| T-142 | agentflow/shadow/verbosity_ab.py | 331 | 250 |

T-141 depends on T-140 (test file references session_manager structure). T-139, T-140, T-142 are independent — run parallel. T-140 must land before T-122 and T-121 (both own session_manager.py).

---

## Addendum: T-122 — Session restart regression tests (restored 2026-07-06c)

**Status:** PENDING — tests were never written; task spec was clobbered by T-104 auto-numbering.

**Goal:** Three tests in tests/shell/test_session_manager.py: (1) test_on_enter_idle_reinjects_skill — assert skill command injected on restart; (2) test_restart_end_to_end_via_state_machine — drive full RESTARTING→IDLE path via poll(), assert tokenizer reset; (3) test_on_enter_restarting_oserror_safe — OSError on write_input must not propagate; restart_child still called. Stdlib + unittest.mock only. **Depends on T-140** (test file must be split before adding more tests).

## Addendum: T-125 — pty_signal.py (restored 2026-07-06c)

**Status:** MERGED

**Goal:** agentflow/shell/pty_signal.py with task_start / task_done / handoff_complete subcommands. Full spec preserved in tasks.json T-125.

## Addendum: T-143 + T-144 — CANCELLED (folded into T-121, 2026-07-06g)

Root cause traced to session recycling making restart invisible to user. Both fixes are stub completions of T-121's state machine — not independent tasks. Timer-based stdin gating (T-144 original design) replaced with state-based gating (no timer needed). See T-121 addendum for implementation details.

---

## Addendum: T-170 — Startup cache (MERGED PR #97, 2026-07-09)

Pre-compute round state on PTY startup to skip startup commands. See commit 924521ea3.

---

## Addendum: T-183 — Orchestrator HANDOFF RECOMMENDED bypass

**Status:** PENDING

**Goal:** In `output_handler.py`, detect the literal string `HANDOFF RECOMMENDED` in PTY output when `session_type == "orchestrator"` and call `trigger_handoff()` directly — bypassing the terminal-output token threshold. Guard: only fire when state is TASK_RUNNING or TASK_COMPLETE. Add audit log entry `handoff_recommended_detected`. Add test `test_orchestrator_handoff_recommended_triggers_handoff`.

**Files:** `agentflow/shell/output_handler.py` (~10 lines), `tests/shell/test_output_handler.py` (~20 lines)

---

## Addendum: T-184 — Context window fill via Stop hook transcript

**Status:** PENDING

**Goal:** Add a Stop hook (`agentflow/hooks/stop_context_capture.py`) that reads `transcript_path` from its payload, finds the last `assistant`-type entry, and extracts `message.usage`. Compute fill = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` (all three required — `input_tokens` alone is 1 when cache hits). Write `{"fill_tokens": <int>, "ts": <epoch>}` to `.agentflow/context_fill.json` atomically. In `output_handler.py` threshold check, read `context_fill.json` and use `fill_tokens / model_context_window >= 0.7` as primary guard when file is fresh (< 60s old), falling back to terminal output token count otherwise. Wire hook in `.claude/settings.json` Stop event. Add tests for fill computation and fallback logic. Independent — T-183 cancelled.

**Files:** `agentflow/hooks/stop_context_capture.py` (new), `agentflow/shell/output_handler.py`, `.claude/settings.json`, `tests/hooks/test_stop_context_capture.py` (new)

---

## Addendum: T-185 — Session state scoped per PTY session-id

**Status:** PENDING

**Goal:** Fix session poisoning. `user_prompt_submit.py` writes `session_state.json` to project `.agentflow/` — shared by all PTY shells. Fix: write to `.agentflow/session_state_<sid>.json` keyed by `AGENTFLOW_SESSION_ID`. In `session_manager.py` `_sync_session_type()`, read sid-keyed file first, fall back to unkeyed file for backward compat. Add isolation test: two sessions with different sids writing opposing types must each read their own value. Independent of T-183/T-184.

**Acceptance criteria (additional):** After fix, oracle auto-restart must inject `/oracle\r` into the correct PTY session only (no cross-session bleed). Verify with audit logs that a restarted oracle shell reads `session_type=oracle` from its own sid-keyed file, not a stale orchestrator value.

**Files:** `agentflow/hooks/user_prompt_submit.py`, `agentflow/shell/session_manager.py`, `tests/hooks/test_user_prompt_submit.py`, `tests/shell/test_session_manager.py`

---

## Addendum: T-194 — Fix init TASK_RUNNING oracle contamination (MERGED PR #111 2026-07-11)

**Goal:** `session_manager.py` `__init__` set `TASK_RUNNING` whenever `current_round.json` existed, regardless of session_type. Oracle sessions contaminated. Fix: move check after `_sync_session_type()` and gate on `self.session_type == "orchestrator"`.

**Files:** `agentflow/shell/session_manager.py`, `tests/shell/test_session_manager.py`

---

## Addendum: T-195 — Replace _delayed_inject with initialPrompt spawn (filed 2026-07-11)

**Status:** PENDING

**Goal:** `on_enter_idle`'s `_delayed_inject` (1.5s sleep thread writing `/orchestrate\r` to PTY stdin) is fragile. Replace: in `spawn_new_child` (`process_manager.py`), when `_just_restarted=True` and `session_type` is set, build spawn command as `[cmd, f"/{skill}"]` (e.g. `["claude", "/orchestrate"]`) so the CLI receives the prompt as a positional arg. Remove `_delayed_inject` thread from `on_enter_idle` entirely. Depends on T-194 (MERGED).

**Acceptance criteria:** No `threading.Thread` call in `on_enter_idle`. After restart, skill command appears as first user message. Unit test: mock `spawn_new_child`, assert command includes skill when `_just_restarted=True` and `session_type` set.

**Files:** `agentflow/shell/session_manager.py`, `agentflow/shell/process_manager.py`, `tests/shell/test_session_manager.py`

**estimated_lines:** 40

---

## Addendum: T-215 — Audit session-restart conditions for determinism (filed 2026-07-14)

**Status:** PENDING

**Goal:** Eliminate all LLM-output and PTY-stdout dependencies from the session-restart decision path.

**Scope:** Investigate only — no code changes. Requires oracle approval before any implementation.

**Files to audit:**
- `agentflow/shell/output_handler.py` — scans LLM stdout for `AGENTFLOW_TASK_COMPLETE:<id>` and `AGENTFLOW_TASK_START:<id>` regexes; drives turn counting + token accounting; confirm whether any restart decision is gated on these patterns
- `agentflow/shell/handoff_handler.py` — `poll_session`, `check_drain_restart`, `trigger_handoff`; audit what conditions feed `trigger_handoff` and whether any depend on LLM stdout or orchestrate calling `pty_signal.py task_done` explicitly
- `agentflow/shell/session_manager_handlers.py` — `handle_session_exit` gate (lines 150–153): checks `handoff_complete_path.exists()` AND `session_type == "orchestrator"`; confirm both are file-based, not stdout-derived
- `agentflow/shell/threshold_sync.py` — `session_type` detection; confirm it reads a file-based signal (not stdout heuristic) after T-191
- `agentflow/shell/pty_signal.py` — `task_done` / `handoff_complete` writers; audit whether orchestrate's failure to call these can block restart indefinitely
- `agentflow/hooks/post_tool_use.py` — audit which tool events hooks can intercept deterministically to cover gaps left by LLM omissions

**Specific failure to reproduce:** Session didn't restart after T-203/204/205 merge because orchestrate didn't emit task-done signal. Map the exact signal chain that failed and propose hook-based backstops for each gap.

**Output:** `.agentflow/spike_T215_restart_determinism.md` — catalogue every restart condition with: signal type (file / stdout / LLM-call), deterministic? (yes/no), proposed fix if no.

**estimated_lines:** 0

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
## Addendum: T-196 — Pre-resolve task context into orchestrate initialPrompt (filed 2026-07-11)

**Status:** MERGED (PR #119, 2026-07-12)

**Goal:** When orchestrate builds the `spawn_new_child` command (after T-195 lands), embed pre-resolved task context — active task ID, title, deps, estimated_lines — directly into the positional prompt arg. This eliminates startup re-derivation (execution_plan.md + tasks.json reads) from the worker's context. Depends on T-195.

**Acceptance criteria:** Worker session initialPrompt contains task ID, title, dep list, and estimated_lines. Orchestrate startup.md step 3b treats baked context as a fast-path hint: if present and task status in tasks.json matches, skip re-derivation; if absent or status mismatch, fall back to full re-derivation normally. Unit test: assert spawned command string contains task metadata; assert fallback triggers on stale context.

**Files:** `commands/claude/orchestrate.md`, `commands/claude/orchestrator/startup.md`, `agentflow/shell/process_manager.py`

**estimated_lines:** 30

---
## Addendum: T-208 — Fix PTY drain restart — tasks_in_flight.json as single source of truth (filed 2026-07-12)

**Status:** MERGED (PR #118, 2026-07-12)

**Goal:** Fix PTY drain restart being blocked in TASK_RUNNING state across sessions. Root cause: state machine starts in TASK_RUNNING when current_round.json exists but task_complete.json is absent (cleared by prior session). New session has no escape path since task_done signal was already consumed.

**Solution:** Three-part fix: (1) PostToolUse hook detects Write to current_round.json and atomically writes tasks_in_flight.json with task_ids — hook-driven, deterministic, no skill involvement; (2) pty_signal.py task_done writes [] tombstone instead of deleting file — absent=not initialized, []=drained, non-empty=tasks running; (3) check_drain_restart allows TASK_RUNNING state (alongside IDLE) and uses tasks_in_flight.json as sole truth.

**Files:** `agentflow/hooks/post_tool_use.py`, `agentflow/shell/pty_signal.py`, `agentflow/shell/handoff_handler.py`

---

## Addendum: T-213 — Fix AGENTS.md dead headless-layer paths (filed 2026-07-14)

**Task:** T-213
**Title:** Fix AGENTS.md — replace dead headless-layer paths with live commands/ structure
**Owns:** commands/gemini/AGENTS.md
**Estimated lines:** 60
**Depends:** none
**Status:** MERGED

## Addendum: T-214 — Flatten Gemini orchestrate model to gemini-2.5-flash (filed 2026-07-14)

**Task:** T-214
**Title:** Flatten Gemini orchestrate model selection to gemini-2.5-flash (single tier)
**Owns:** commands/gemini/skills/orchestrate/SKILL.md
**Estimated lines:** 60
**Depends:** none
**Status:** MERGED (PR #124, 2026-07-14)

## Addendum: T-216 — Scope task_complete.json to SID (filed 2026-07-14)

**Status:** PENDING

**Depends on:** T-215 (MERGED), T-200 (MERGED)

**Problem:** `.agentflow/task_complete.json` is flat. With concurrent orchestrator sessions, session A's task completing transitions session B out of TASK_RUNNING. (T-215 Flag 2)

**Fix:**
- `agentflow/shell/session_manager.py` — `_task_complete_path` property: return `task_complete_{sid}.json` when SID set, using `session_paths.session_file()`
- `agentflow/shell/pty_signal.py` — `task_done()`: accept SID argument (default from `AGENTFLOW_SESSION_ID` env); write SID-keyed path
- `agentflow/shell/handoff_handler.py` — `poll_session()` task_complete check: already reads via `manager._task_complete_path` (property change is sufficient)

**estimated_lines:** 25

---

## Addendum: T-218 — Scope current_round.json mtime guard to SID via content validation (filed 2026-07-14)

**Status:** MERGED (PR #130, 2026-07-15)

**Depends on:** T-216 (shared session_manager.py)

**Problem:** IDLE → TASK_RUNNING fires on any `current_round.json` mtime change (flat file). All concurrent sessions wake when any orchestrator writes a new round. (T-215 Flag 5)

**Fix:** Embed SID in `current_round.json` content (orchestrate skill writes this file; verify field exists). On mtime change, read file and validate `session_id` field matches `AGENTFLOW_SESSION_ID` before transitioning. Do NOT rename file — content validation is cheaper and avoids renaming session_manager path property.
- `agentflow/shell/handoff_handler.py` — `poll_session()` mtime guard: after mtime change detected, read JSON and check `session_id`; skip transition if mismatch
- `agentflow/shell/session_manager.py` — verify `_current_round_path` init is correct (no change expected)
- `agentflow/shell/process_manager.py` — `spawn_new_child()` TASK_CTX read: add assertion that SID field is present

**estimated_lines:** 20

---

## Addendum: T-217 — Scope tasks_in_flight.json to SID (MERGED PR #131 2026-07-15)

**Status:** MERGED

**Depends on:** T-218 (shared handoff_handler.py)

**Problem:** `tasks_in_flight.json` drain tombstone (`[]`) is flat. Session A's drain triggers `check_drain_restart` in session B even if B still has tasks running. (T-215 Flag 3)

**Fix:** Scope to SID-keyed path via `session_paths.session_file()`. Add `_tasks_in_flight_path` property to `session_manager.py`.
- `agentflow/shell/pty_signal.py` — `task_start()`, `task_done()`: write SID-keyed path (SID from env)
- `agentflow/hooks/post_tool_use.py` — `sync_tasks_in_flight()`: use SID-keyed path
- `agentflow/hooks/post_tool_use_agent.py` — tasks_in_flight updates: use SID-keyed path
- `agentflow/hooks/user_prompt_submit.py` — tasks_in_flight init: use SID-keyed path
- `agentflow/shell/handoff_handler.py` — `check_drain_restart()`: read via `manager._tasks_in_flight_path`

**Note:** `session_paths.session_file()` is available in hooks from T-200. pty_signal.py reads SID from `AGENTFLOW_SESSION_ID` env (already set by PTY at launch).

**estimated_lines:** 60

---

## Addendum: T-219 — Fix context_fill.json reset path + staleness check in check_drain_restart (filed 2026-07-14)

**Status:** PENDING

**Depends on:** T-217 (shared handoff_handler.py)

**Problem (write side):** `_clear_signal_files()` in `session_manager_handlers.py` resets context_fill using a hardcoded flat path (line 57). Both `post_tool_use.py` and `stop_context_capture.py` already write SID-keyed paths (fixed in T-201/T-203). The reset on restart clears the wrong file. (T-215 Flag 4 partial)

**Problem (staleness):** `check_drain_restart()` reads context_fill without checking `ts` freshness. `_read_fill_tokens()` checks `FILL_STALE_SECONDS = 60`; `check_drain_restart` omits this, allowing stale values to trigger spurious restarts. (T-215 Flag 4 sub-issue)

**Fix:**
- `agentflow/shell/session_manager_handlers.py` — `clear_signal_files()`: use `session_file(agentflow_dir, "context_fill.json", sid)` for reset write; read SID from `session_manager` or env
- `agentflow/shell/handoff_handler.py` — `check_drain_restart()`: after reading context_fill JSON, check `ts` field; skip if `time.time() - ts > 60`

**estimated_lines:** 20

---

## Addendum: T-220 — Fix handoff.md doc drift: PTY polls file, does not scan stdout for HANDOFF_COMPLETE (filed 2026-07-14)

**Status:** PENDING

**Problem:** `commands/claude/handoff.md` Step 8 states the PTY "scans stdout for `HANDOFF_COMPLETE`." The code polls `handoff_complete_{sid}.json` (file-based). The skill printing `HANDOFF_COMPLETE: ...` is for human-readable feedback only; it has no effect on PTY state. Identified in T-215 Section 1.4.

**Fix:** Remove or correct the stdout-scanning claim in Step 8. State that the PTY polls for `handoff_complete_{sid}.json`.

**estimated_lines:** 3

---

## Addendum: T-222 — Fix compress.py _is_mid_round() missed SID callsite (filed 2026-07-15)

**Status:** PENDING

**Depends on:** T-217 (merged)

**Problem:** `agentflow/proxy/compress.py:59` `_is_mid_round()` reads the flat `project_root / ".agentflow" / "tasks_in_flight.json"`. After T-217 ships, this file is absent when a SID is active (tasks_in_flight lives in `sessions/<SID>/`). So `_is_mid_round()` always returns False mid-round → compression runs when it should be suppressed.

**Fix:** Update `_is_mid_round()` to use `session_file()`:
```python
from agentflow.shell.session_paths import session_file
tif = session_file(project_root / ".agentflow", "tasks_in_flight.json", os.environ.get("AGENTFLOW_SESSION_ID", ""))
```

**Owns:** `agentflow/proxy/compress.py`
**estimated_lines:** 5

---

## Addendum: T-223 — Fix drain: extract PR number from gh pr merge, use gh pr view for URL+task_id+state (filed 2026-07-15)

**Status:** PENDING

**Root cause:** Three compounding bugs caused T-217 orchestrate session to fail to restart after PR #131 was merged:
1. PR URL never registered — worker creates PR inside Agent call; `_detect_pr_create` only fires for orchestrator direct Bash `gh pr create`, so task_prs.json never populated for T-217.
2. Title-match race — `_fetch_merged_pr_titles()` uses GitHub list API (eventual consistency); PR merged 1 second before hook fired, list API returned stale state → no title match.
3. SID path mismatch — hooks hardcode flat `agentflow_dir / "tasks_in_flight.json"` while `pty_signal.py` writes SID-scoped `sessions/<SID>/tasks_in_flight.json`; hooks read wrong file when agy is running.
4. Plus: `task_start` LLM-dependent (orchestrate.md line 77 — can be missed or mis-timed).
5. Plus: `_cleanup_merged_in_flight` in `user_prompt_submit.py` never calls `pty_signal.py task_done` — outside-Claude merges never write `task_complete.json`.

**Fix (6 changes):**
1. NEW `agentflow/hooks/pre_tool_use_agent.py` — PreToolUse Agent hook; extracts `^## Addendum: (T-\d+)` from prompt; calls `pty_signal.py task_start <task_id>`. Deterministic replacement for orchestrate.md line 77.
2. MODIFY `.claude/settings.json` — register `pre_tool_use_agent.py` under PreToolUse matcher for Agent tool.
3. MODIFY `agentflow/hooks/post_tool_use_agent.py` — fix SID path (`session_file(..., sid)`); at merge trigger, extract PR number from `gh pr merge N` command, call `gh pr view N --json title,state,url`, extract task_id via `re.search(r'\b(T-\d+)\b', title)`, drain on MERGED, register URL on OPEN (auto-merge scheduled). Remove `_detect_pr_create` dead code.
4. MODIFY `agentflow/hooks/user_prompt_submit.py` — fix SID path; add `pty_signal.py task_done <task_id>` call per completed task in `_cleanup_merged_in_flight`.
5. MODIFY `commands/claude/orchestrate.md` — remove `pty_signal.py task_start` from worker-spawn step; remove `pty_signal.py task_done` from post-worker step; keep stdout `AGENTFLOW_TASK_COMPLETE:<task_id>` signal.
6. Tests — new `tests/test_pre_tool_use_agent.py`; update `tests/test_post_tool_use_agent.py` and `tests/test_user_prompt_submit.py`.

**Two deterministic drain paths post-fix:**
- Primary: orchestrator runs `gh pr merge N` as Bash → PostToolUse → `gh pr view N` → MERGED → `task_done`
- Secondary: any user prompt → UserPromptSubmit → title-match (no race, user merged before typing) → `task_done`

**Owns:** `agentflow/hooks/pre_tool_use_agent.py` (new), `agentflow/hooks/post_tool_use_agent.py`, `agentflow/hooks/user_prompt_submit.py`, `commands/claude/orchestrate.md`, `.claude/settings.json`
**estimated_lines:** 120

---

## Addendum: T-224 — Fix session_state read/write mismatch + hook sys.path self-bootstrap (MERGED PR #140 2026-07-15)

**Status:** MERGED

**Problem 1 (read/write mismatch):** `user_prompt_submit.py` `_write_session_state_atomic()` (line 75) writes to `sessions/<SID>/session_state.json` via `session_file()`. But the read path (lines 230–239) checks `agentflow_dir / f"session_state_{SID}.json"` (old flat+keyed) then `agentflow_dir / "session_state.json"` (old flat) — never `sessions/<SID>/session_state.json`. Result: `[SESSION: unknown]` on every hook firing; PTY never detects orchestrator session type; `check_drain_restart` never runs.

**Problem 2 (sys.path fragility):** All hooks use absolute package imports (`from agentflow.shell.session_paths import session_file`) but are invoked as standalone scripts by Claude Code without PYTHONPATH set. This requires `pip install -e .` to be current — any new module added to the source tree silently breaks all hooks until reinstalled. Fix: add `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` before all project imports in every hook.

**Fix:**
- `agentflow/hooks/user_prompt_submit.py` — read path (lines 230–239): replace flat+keyed lookup with `session_file(agentflow_dir, "session_state.json", sid)` matching the write path.
- `agentflow/hooks/verbosity_reminder.py` — same read/write audit (write uses session_file correctly; verify no stale read path).
- All hook files (`post_tool_use.py`, `post_tool_use_agent.py`, `pre_tool_use_agent.py`, `user_prompt_submit.py`, `verbosity_reminder.py`, `idx_reminder.py`, `read_check.py`, `write_indexer.py`, `size_check.py`) — add `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` before first project import.

**Owns:** `agentflow/hooks/user_prompt_submit.py`, `agentflow/hooks/verbosity_reminder.py`, all other hook files for sys.path fix
**estimated_lines:** 35

## Addendum: T-228

**Title:** Atomic tasks.json sync on merge — close execution_plan/tasks.json split-brain gap

When a worker marks a task MERGED in execution_plan.md, it must atomically write `status=complete` to tasks.json in the same step. Currently execution_plan.md is updated by the worker but tasks.json update is expected from the orchestrator — if the session exits or restarts between those two writes, tasks.json is left stale (pending) while execution_plan.md shows MERGED. Fix: (1) update orchestrate.md post-merge step to write tasks.json immediately after confirming merge; (2) update worker/system.md post-merge checklist to include tasks.json write as a required atomic step alongside execution_plan.md; (3) confirm the startup reconciliation guard auto-repairs by writing `complete` when MERGED detected. Tests: assert worker post-merge checklist contains tasks.json write step.

**Owns:** `commands/claude/orchestrate.md`, `commands/claude/worker/system.md`
**estimated_lines:** 40

## Addendum: T-229

**Title:** Extend flock to tasks.json, state.json, execution_plan.md — close write-write and stale-read races

Three shared files have no write locking and are written concurrently by oracle, orchestrate, and hooks: (1) tasks.json — oracle files tasks, orchestrate marks complete, both do raw json.dump with no lock; (2) execution_plan.md — oracle updates round table, orchestrate reads/writes on startup; (3) state.json — orchestrate writes next_round/next_tasks, oracle can overwrite with stale value. Fix: extend the existing flock pattern (already on tasks_in_flight.json) to all three files using `.agentflow/<file>.lock` files. All writers — oracle edits, orchestrate skill steps, hook cleanup paths — must acquire the lock before writing. Tests: concurrent write test asserting no torn JSON and no lost updates.

**Owns:** `agentflow/hooks/user_prompt_submit.py`, `agentflow/shell/handoff_handler.py`, `agentflow/shell/session_manager.py`, `commands/claude/oracle.md`, `commands/claude/orchestrate.md`
**estimated_lines:** 60

## Addendum: T-230

**Title:** Orchestrator creates worktree before spawning worker + ban git checkout in project root

Root cause of oracle/orchestrate branch contamination: orchestrate session runs `git checkout <branch>` in the main project directory, leaving it on a feature branch when oracle sessions start. Fix: (1) update orchestrate.md — orchestrator must run `git worktree add .claude/worktrees/<name> -b <branch>` BEFORE spawning the worker, then pass the worktree path in the context bundle; (2) add explicit constraint to orchestrate.md: never run `git checkout` in the project root — use `git show <branch>:path` or `gh pr diff` for branch inspection; (3) worker receives a pre-created worktree path and calls EnterWorktree with that path rather than creating the branch itself. Keeps main project directory always on main, preventing stash contamination of parallel sessions.

**Owns:** `commands/claude/orchestrate.md`
**estimated_lines:** 30

## Addendum: T-232

**Title:** PostToolUse hook: detect PR merge event and atomically update tasks.json + execution_plan.md

When `session_type == "orchestrate"` and a Bash tool output contains `✓ Merged pull request`, parse the task_id from the PR title (format `fix(T-NNN):` / `feat(T-NNN):`), then atomically: (1) write `status: complete` to tasks.json with flock; (2) write `MERGED` marker to the corresponding Addendum section in execution_plan.md. Zero LLM calls, stdlib-only. Guard: only fires when `session_type == "orchestrate"` — oracle/other sessions skip entirely. Tests: mock Bash output with merged PR, assert both files updated atomically; assert oracle session_type skips the hook.

**Owns:** `agentflow/hooks/post_tool_use.py`
**estimated_lines:** 50

## Addendum: T-233

**Title:** Verbosity rule: never narrate internal mechanics in orchestrator/worker output

Add rule to `commands/claude/orchestrator/verbosity.md`: "Never narrate compliance with hooks or internal mechanics — idx reads, flock, sys.path bootstrap, hook reminders, skill file names, cache paths. Comply silently. Never surface agentflow implementation details in user-facing output." This prevents IP leakage in demos and eliminates token-wasting narration (e.g. "The hook requires me to use indexed reads...").

**Owns:** `commands/claude/orchestrator/verbosity.md`
**estimated_lines:** 15

## Addendum: T-234

**Title:** Context bundle delivery via temp file — remove context bundle from Agent prompt arg

Orchestrator writes context bundle to `.agentflow/ctx-<session-id>.json` before spawning a worker; passes only the file path in the Agent `prompt` arg. Worker reads and deletes the file on startup. UI shows a path reference, not bundle content; disk-based jailbreak vector eliminated once file is deleted. Guard: worker must handle missing file gracefully (fall back to error, not silent skip). Tests: assert Agent prompt arg contains only a path; assert file deleted after worker reads it.

**Owns:** `commands/claude/orchestrate.md`
**estimated_lines:** 40
