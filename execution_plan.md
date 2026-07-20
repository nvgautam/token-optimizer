# AgentFlow — Execution Plan

Oracle creates; orchestrator extends lazily at milestone boundaries.

---

## Milestone M-F: Friendlies Delivery — CURRENT FOCUS
**Goal:** Ship a polished, trustworthy package to friendly beta users with zero user involvement beyond PR approvals.
**Status:** IN PROGRESS
**Owner:** Orchestrator works this milestone until all rounds below are MERGED.

### Success criteria
1. Orchestrator restarts reliably after every round — user only approves PRs
2. Oracle has a clear handoff UX — no infinite sessions, no surprise restarts
3. Token-saving strategies are invisible to users — not surfaced in output or readable files
4. Context bundle and other IP delivered in-memory only — never displayed to user
5. All Python code compiled and obfuscated — not readable in the delivered package
6. API key controls access — key can be revoked from cloud at any time

M-F round rows live in the Master Round Table (M-F-1 through M-F-8). Orchestrator reads from there.

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

## Addendum: T-099 — Gemini Oracle Skill (filed 2026-07-04)

| Task | Title | Status |
|---|---|---|
| T-099 | Gemini Oracle Skill — create /oracle equivalent skill for Gemini | PENDING |

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

## Master Round Table (updated 2026-07-18)

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
| Round C-P1 (solo) — MERGED (PR #174 2026-07-18) | T-273 | Fix SID path bugs: pty_signal handoff_complete, shell/cleanup_tasks task_complete, user_prompt_submit delete, tools/cleanup_tasks TIF — all use flat paths instead of session_file()/SID-in-filename |
| Round C-P2 (solo) — MERGED (PR #175 2026-07-18) | T-275 | Integration test: full drain-restart file-state sequence — write_merged_and_clear → check_drain_restart → assert trigger_handoff; catches T-274-class regressions |
| Round C-P3 (solo) — MERGED (PR #177 2026-07-18) | T-276 | Signal-file audit log coverage — plug all silent write/delete/unlink gaps so logs give a complete picture at all times |
| Round C-P4 (solo) — MERGED (PR #178 2026-07-18) | T-277 | Fix _write_merged_and_clear current_round.json exception handling — split FileNotFoundError vs corrupt/mid-write; root cause of C-2 premature drain |
| Round C-1 — MERGED | T-266 | debug.md 5-phase forensic rewrite — largest task, triggers restart; folds T-250 (debug.md KeyError fix) |
| Round C-2 — MERGED (PR #179/#180 2026-07-18) | T-162 ‖ T-268 | oracle.md split + oracle duplicate-check (both touch oracle.md) |
| Round C-state — MERGED (PR #181 2026-07-18) | T-278 | Orchestrate resume: derive next round from execution_plan.md Master Round Table, not state.json — state.json is stale when tasks are prepended after last merge |
| Round C-state2 — MERGED (PR #182/#183 2026-07-18) | T-279 ‖ T-280 | Enforce Write tool for current_round.json + startup reconciliation (validate current_round.json task_ids against tasks.json on start, unlink if stale) |
| Round C-state3 — MERGED | T-281 | Round table [PENDING] tag format — migrate rows + update oracle/orchestrate to grep -m 1 '\[PENDING\]' for next round |
| Round C-splits2 — MERGED (PR #185/#186 2026-07-18) | T-272 ‖ T-282 | Size-violation splits: test_cleanup_violations.py (T-272) + test_orchestrate_skill.py (T-282) |
| Round C-pty — MERGED (PR #187/#188 2026-07-18) | T-283 ‖ T-284 (parallel) | PTY signal cleanup: sid in pty_signal _log (T-283) + remove vestigial task_done/ROUND_COMPLETE from orchestrate.md (T-284) |
| Round C-3a — MERGED (PR #188 2026-07-18) | T-210 | write_indexer test cache fix + prune CLI |
| Round C-3b — MERGED (PR #189 2026-07-18) | T-243 | Pass --auto to claude/claude2 PTY restart (not agy) after handoff |
| Round C-spawn-guard — MERGED (PR #190 2026-07-18) | T-285 (solo) | orchestrate.md: write current_round.json before Agent spawn — prevents premature drain on spawn failure |
| Round C-session-id — MERGED (PR #191 2026-07-18) | T-286 (solo) | Fix orchestrate.md: resolve $AGENTFLOW_SESSION_ID via Bash before Write tool call |
| Round C-permission-mode — MERGED (PR #192 2026-07-18) | T-287 (solo) | Fix PTY restart: --auto → --permission-mode auto in process_manager.py |
| Round C-cli-spike — MERGED (2026-07-18) | T-259 (solo) | CLI spike: agentflow round-start command foundation |
| Round C-restart-fix — MERGED (PR #195/#196 2026-07-19) | T-291 ‖ T-292 (parallel) | Fix mid-round restart bug + Fix session_type hooks substring → startswith |
| Round C — MERGED (PR #197 2026-07-19) | T-260 (solo) | round-start CLI announcement |
| M-F-2 — MERGED (PR #198 2026-07-19) | T-234 (solo) | Context bundle via temp file |
| Pre-M-F-1a — MERGED (PR #200 2026-07-19) | T-300 (solo) | Reviewer gate hardening — escalate happy-path-only → BLOCKER; mandatory /review before PR |
| Pre-M-F-1b — MERGED (PR #201 2026-07-19) | T-299 (solo) | tasks.db retirement + tasks.json schema enforcement + addendum lifecycle |
| Pre-M-F-1c — MERGED (PR #202 2026-07-19) | T-303 (solo) | Split post_tool_use_agent.py (271 lines) + size_check hook dedupe guard |
| M-F-1 [PENDING] | T-298 ‖ T-297 (MERGED PR #203) | CLI task_done/start impl + pty_signal migration + dead hook removal + hook integration tests |
| M-F-3 [PENDING] | T-296 (solo) | Verbosity hardening: oracle + orchestrate personas — no strategy leakage |
| M-F-4 — MERGED | T-236 (solo) | Post-merge conflict resolution (OWNS gate preserved) |
| M-F-6 [DEFERRED] | T-295 (solo) | IP spike: wire key server + encrypt context files — DEFERRED (customer-shipped binary; Nuitka Community obfuscation sufficient for now) |
| M-F-7 ‖ M-F-8 [PENDING] | T-301 ‖ T-302 (parallel) | Oracle handoff UX + customer distribution — disjoint OWNS (session_manager.py/oracle.md vs scripts/build_dist.sh) |
| Round D [PENDING] | T-178 ‖ T-211 (parallel) | Hook audit log spike + Gemini lifecycle spike |
| Round E [PENDING] | T-168 ‖ T-290 (parallel) | product judgment layer + debug terminal step |
| Round E-2 [PENDING] | T-167 (solo) | Oracle Phase 3 plan-mode preview |
| Round E-3 [PENDING] | T-288 (solo) | Oracle self-check: disjoint OWNS before writing execution_plan.md |
| Round E-4 [PENDING] | T-289 (solo) | Oracle troubleshoot detection → offer debug skill |
| Round F [PENDING] | T-063 (solo) | Multi-provider chain step 1 (enterprise) |
| Round F-2 [PENDING] | T-064 (solo) | Multi-provider chain step 2 |
| Round F-3 [PENDING] | T-099 (solo) | Multi-provider chain step 3 |

Priority rationale (2026-07-17): T-274 (P0) + T-273 (P1) prepend Round C — both block reliable orchestrate restart loop. Restart-path hardening (A/B) before skill rewrites — loop reliability prerequisite. CLI spike (T-259) gates T-260. Rounds D–E are spikes/oracle enhancements. Round F deferred until Claude-only loop is solid. T-276 (C-P3) prepends C-1 — audit log coverage is a prerequisite for diagnosing any further drain/restart bugs. T-277 (C-P4) prepends C-1 — this is the root fix for the C-2 premature-drain bug; was documented in T-276 spec but missed during implementation.

**T-277:** Fix `_write_merged_and_clear` exception handling for `current_round.json` unreadability — root cause of the Round C-2 premature drain bug. File: `agentflow/shell/drain_restart.py`, function `_write_merged_and_clear`, lines 13–18.

Current (broken): `except Exception: return` — single catch, always returns early, never unlinks TIF, completely silent.

Replace with two branches:
```python
except FileNotFoundError as e:
    manager._log_audit({"event": "drain_no_current_round", "error": str(e)})
    # fall through — file genuinely absent, safe to unlink TIF and proceed
except Exception as e:
    manager._log_audit({"event": "drain_no_current_round", "error": str(e)})
    return  # corrupt or mid-write race — preserve TIF, retry next 30s poll
```

**Why the split matters:** `current_round.json` has no write lock (`execution_plan.md.lock` exists; no `current_round.json.lock`). A concurrent skill write can produce partial/corrupt JSON → `json.JSONDecodeError`. Falling through on `JSONDecodeError` would permanently destroy both files and lose the MERGED annotation with no recovery. The retry path (return + preserved TIF) allows the next poll cycle to re-read a fully-written file. `FileNotFoundError` is different — file is genuinely gone, no retry will help, TIF must be cleaned up unconditionally.

**Acceptance criteria:** (1) Unit test: mock `current_round_path.read_text` to raise `FileNotFoundError` → assert `drain_no_current_round` logged, TIF unlinked, `current_round.json` unlink attempted. (2) Unit test: mock to raise `json.JSONDecodeError` → assert `drain_no_current_round` logged, TIF NOT unlinked (preserved for retry). (3) Integration: run the full drain sequence from T-275's test with `current_round.json` absent — confirm drain still completes without leaving stale TIF tombstone.

**T-276:** Signal-file audit log coverage — add log events for every unlogged write, unlink, and failure path across all PTY signal files so that `pty_audit.jsonl` provides a complete, unambiguous picture at all times. Eight specific gaps to close:

1. **`current_round.json` detected** — `handoff_handler.py:poll_session` line 128: add `_log_audit({"event": "current_round_detected", "round_id": ..., "mtime": ...})` on the success path (before `transition("current_round_written")`). Currently logs only error paths.

2. **`current_round.json` unlinked** — `drain_restart.py:_write_merged_and_clear` line 54: add `_log_audit({"event": "current_round_unlinked", "round_id": rid})` immediately after `manager._current_round_path.unlink(missing_ok=True)`. Currently only `tif_unlinked` is logged; the `current_round.json` removal is silent.

3. **`_write_merged_and_clear` early return** — `drain_restart.py` lines 17–18: split the single `except Exception: return` into two branches: `except FileNotFoundError as e: _log_audit({"event": "drain_no_current_round", "error": str(e)})` then **fall through** to the TIF unlink block (file is genuinely absent — safe to clean up and proceed); `except Exception as e: _log_audit({"event": "drain_no_current_round", "error": str(e)}); return` (corrupt or mid-write race — preserve TIF so the next 30s poll can retry once the file is fully written). `current_round.json` has no write lock, so `JSONDecodeError` from a concurrent skill write is a real failure mode; the retry path is the correct recovery. This distinction is the root fix for the C-2 premature-drain bug and makes the log event fire in both cases.

4. **`task_complete.json` unlinked on enter_idle** — `session_manager_handlers.py:clear_signal_files` line 58: add `_log_audit({"event": "signal_file_unlinked", "file": "task_complete.json"})` inside the `if path.exists()` block, after the successful `path.unlink()`. Currently only the error is logged.

5. **`handoff_complete.json` unlinked on enter_idle** — same `clear_signal_files` block (same `for` loop, same fix as gap 4, include the filename in the event so both files are distinguishable).

6. **`task_complete.json` unlinked by UPS hook** — `user_prompt_submit.py` line 72: add `_log_drain(agentflow_dir, {"event": "signal_file_unlinked", "file": name})` after successful `complete_file.unlink()`. Currently only the error path (`delete_signal_file_error`) is logged.

7. **`handoff_complete.json` unlinked by UPS hook** — same UPS block as gap 6 (same loop, same fix).

8. **`context_fill.json` reset to 0** — `session_manager_handlers.py:clear_signal_files` line 67: add `_log_audit({"event": "context_fill_reset", "sid": sid})` after the successful `cf.write_text(...)`. Currently only `context_fill_reset_error` is logged.

**Acceptance criteria:** After merge, grep `pty_audit.jsonl` and `hook_drain_debug.jsonl` for any orchestrate session and confirm: (a) `current_round_detected` appears when round starts, (b) `current_round_unlinked` appears when drain clears it, (c) if drain fires with no `current_round.json`, `drain_no_current_round` appears, (d) `signal_file_unlinked` appears for `task_complete.json` and `handoff_complete.json` on every `enter_idle`, (e) `context_fill_reset` appears on every `enter_idle`. Add unit tests asserting each event fires for its specific code path. No silent write, unlink, or failure path for any signal file.

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

## Addendum: T-143 + T-144 — CANCELLED (folded into T-121, 2026-07-06g)

Root cause traced to session recycling making restart invisible to user. Both fixes are stub completions of T-121's state machine — not independent tasks. Timer-based stdin gating (T-144 original design) replaced with state-based gating (no timer needed). See T-121 addendum for implementation details.

---

## Addendum: T-183 — Orchestrator HANDOFF RECOMMENDED bypass

**Status:** PENDING

**Goal:** In `output_handler.py`, detect the literal string `HANDOFF RECOMMENDED` in PTY output when `session_type == "orchestrator"` and call `trigger_handoff()` directly — bypassing the terminal-output token threshold. Guard: only fire when state is TASK_RUNNING or TASK_COMPLETE. Add audit log entry `handoff_recommended_detected`. Add test `test_orchestrator_handoff_recommended_triggers_handoff`.

**Files:** `agentflow/shell/output_handler.py` (~10 lines), `tests/shell/test_output_handler.py` (~20 lines)

---

## Addendum: T-194 — Fix init TASK_RUNNING oracle contamination (MERGED PR #111 2026-07-11)

**Goal:** `session_manager.py` `__init__` set `TASK_RUNNING` whenever `current_round.json` existed, regardless of session_type. Oracle sessions contaminated. Fix: move check after `_sync_session_type()` and gate on `self.session_type == "orchestrator"`.

**Files:** `agentflow/shell/session_manager.py`, `tests/shell/test_session_manager.py`

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
## Addendum: T-283

**Title:** Add sid to pty_signal.py _log calls — task_done, task_start, handoff_complete

pty_signal.py resolves session-scoped file paths using `sid = os.environ.get("AGENTFLOW_SESSION_ID", "")` but never includes `sid` in audit log entries written by `_log()`. Fix: pass `"sid": sid` into every `_log(...)` call in `task_done`, `task_start`, and `handoff_complete`. After merge, every pty_audit.jsonl entry from pty_signal has a `sid` field, enabling per-session log filtering without guessing.

**Owns:** `agentflow/shell/pty_signal.py`
**estimated_lines:** 15

## Addendum: T-284

**Title:** Remove vestigial task_done signal and AGENTFLOW_ROUND_COMPLETE prints from orchestrate.md

Two vestiges in `commands/claude/orchestrate.md` cause premature drain and dead stdout noise:
1. Line 39: `pty_signal.py task_done <task_id>` — called when worker Agent returns (PR opened), not when PR is merged. This tombstones TIF too early, triggering drain before the human review gate. The hook (`post_tool_use_agent.py`) already calls `task_done` correctly at PR merge.
2. Lines 40 and 69: `print AGENTFLOW_ROUND_COMPLETE` — the PTY shell has no handler for this signal; it is never read or acted upon.

Fix: remove the `pty_signal task_done` Bash call from the "After worker completes" bullet and remove both `AGENTFLOW_ROUND_COMPLETE` print instructions. `AGENTFLOW_TASK_COMPLETE` and `AGENTFLOW_TASK_START` prints must be retained — they are consumed by `output_handler.py` for EWMA token cost accounting.

**Owns:** `commands/claude/orchestrate.md`
**estimated_lines:** 10

## Addendum: T-298 — M-F-1b: Hook integration tests + dead hook removal

**Goal:** Write integration tests covering hook signal edge cases: missing SID env var, duplicate `task_done` calls, concurrent signal writes, corrupt `tasks_in_flight.json`. Remove hooks confirmed dead by prior rounds.

**Test scenarios (required — not just happy path):** missing SID → graceful no-op; duplicate task_done → idempotent; concurrent writers → last-write-wins with no corruption; corrupt JSON → safe reset.

**Files:** `tests/hooks/test_hook_integration.py`, `agentflow/hooks/` (dead hook removal)
**estimated_lines:** 120

## Addendum: T-299 — tasks.db retirement + tasks.json schema enforcement + addendum lifecycle

**Goal:** Retire `tasks.db` entirely (decision: flock+idx on tasks.json sufficient, SQLite adds no value). Enforce `tasks.json = {task_id, status}` only via CI schema test. Add addendum lifecycle: merge hook atomically moves `## Addendum: T-NNN` from execution_plan.md → `.agentflow/addendums_archive.md` on PR merge. Audit all 14 consumers to retire tasks.db reads.

**Test scenarios (required — not just happy path):**
- tasks.db file present after retirement → not read by any consumer (assert no imports/opens of tasks.db)
- tasks.json with extra fields (title, description) → test_tasks_json_schema.py fails (CI enforcement)
- Addendum move: merge hook ran twice on same task → idempotent (archive not duplicated)
- Round startup with 0 pending tasks → clean "nothing to do" exit, no crash

**Addendum lifecycle (new):**
- On PR merge: `post_tool_use.py` merge hook atomically (1) marks tasks.json complete, (2) writes MERGED to round table, **(3) moves `## Addendum: T-NNN` section from execution_plan.md to `.agentflow/addendums_archive.md`** — all three or none (rollback if any step fails)
- Migration: move all existing MERGED-task addendums out of execution_plan.md into archive as part of T-299
- `tests/test_addendum_lifecycle.py`: assert merge hook moves addendum; assert execution_plan.md contains no addendum for a completed task; assert archive contains it; assert idempotent (second run no-ops)

**Schema enforcement (new — added after root cause found in generation.md):**
- `tests/test_tasks_json_schema.py`: assert every entry in tasks.json has ONLY `task_id` + `status`; any extra field → test fails. Runs in CI. Prevents oracle from re-introducing description fields.
- `generation.md` updated: tasks.json schema is `{task_id, status}` only; all spec in execution_plan.md addendum.
- Migration already applied: descriptions stripped from 16 tasks; 6 missing addendums written to execution_plan.md.

**Consumer audit — all must be updated to read tasks.json (id+status only), retire tasks.db reads:**
- Hooks: `agentflow/hooks/post_tool_use.py`, `agentflow/hooks/post_tool_use_agent.py`, `agentflow/hooks/pre_tool_use_agent.py`, `agentflow/hooks/ups_task_sync.py`
- Shell: `agentflow/shell/cleanup_tasks.py`, `agentflow/shell/pty_signal.py`, `agentflow/shell/orchestrate_cache.py`, `agentflow/shell/session_manager.py`, `agentflow/shell/drain_restart.py`
- Skills: `commands/claude/orchestrate.md`, `commands/claude/orchestrator/startup.md`, `commands/claude/handoff.md`, `commands/claude/oracle.md`
- Migration tool: `agentflow/tools/migrate_tasks_sqlite.py`
- Tests: `tests/tools/test_migrate_tasks_sqlite.py`
- Gemini skill: `commands/gemini/skills/orchestrate/SKILL.md` — line "Write full task definitions to tasks.json" must change to "write {task_id, status} to tasks.json; write full definition as addendum to execution_plan.md"
- Gemini generation: `commands/gemini/oracle/generation.md` — tasks.json schema still includes `description` field; strip to {task_id, status} only, same fix as Claude's generation.md

**estimated_lines:** 250
**blocks:** T-297, T-298

## Addendum: T-300 — Reviewer gate: edge-case enforcement + mandatory review before PR

**Goal:** Escalate happy-path-only test coverage from WARNING → BLOCKER in `test_review.md`. Add mandatory `/review` invocation step in `orchestrate.md` before PR creation — reviewer output must show no BLOCKERs to proceed.

**Files:** `commands/claude/reviewer/test_review.md`, `commands/claude/orchestrate.md`
**estimated_lines:** 25

## Addendum: T-063 — Cross-provider atomic task claiming

**Title:** Cross-provider atomic task claiming — claimed_by field + claim protocol

**Goal:** Enable simultaneous Claude + Gemini orchestrators on the same tasks.json without task collision. Add `claimed_by` field to task schema (null = unclaimed, 'claude'/'gemini' = in use). Both providers check `status=pending AND claimed_by=null`, write `claimed_by='<provider>'` under file lock before spawning; clear on complete/failed. File lock held <100ms.

**Owns:** `commands/claude/orchestrate.md`, `commands/gemini/skills/orchestrate/SKILL.md`, `tests/prompts/test_orchestrate_skill.py`

## Addendum: T-064 — Cross-provider rate headroom check

**Title:** Cross-provider rate headroom check before task claiming

**Goal:** Before claiming a task, each provider checks its own `rate_calibration_<provider>.json` for remaining 5hr window headroom. If remaining < 10% of cap_5hr, skip claiming and log 'Rate headroom low — skipping claim (<provider>)'. Prevents a nearly-rate-limited provider from grabbing tasks it cannot complete.

**Owns:** `commands/claude/orchestrate.md`, `commands/gemini/skills/orchestrate/SKILL.md`
**Reads:** `~/.agentflow/rate_calibration_claude.json`, `~/.agentflow/rate_calibration_gemini.json`
**Depends on:** T-063, T-060

## Addendum: T-167 — Oracle Phase 3 plan-mode preview

**Title:** Oracle Phase 3 — generate artifacts in plan mode for user preview before file writes

**Goal:** Wrap oracle Phase 3 artifact generation in plan mode: show full content as reviewable preview before writing to disk. User approves at milestone/task-breakdown level — catches mis-sized tasks and wrong architectural decisions before they propagate to the orchestrator. Requires EnterPlanMode/ExitPlanMode gates around Phase 3 Write calls in oracle.md.

**Owns:** `commands/claude/oracle.md`
**estimated_lines:** 40

## Addendum: T-168 — Oracle product judgment layer

**Title:** Oracle product judgment layer — jobs-to-be-done, competitive displacement, pricing constraints, market-gated milestones

**Goal:** Extend oracle Phase 1 (market) and Phase 2 (design spar) with: (1) jobs-to-be-done forcing function; (2) competitive displacement probe; (3) pricing/packaging as architectural constraint; (4) milestone sequencing against market validation gates. Update `commands/claude/oracle/market.md` and `commands/claude/oracle/checklist.md`.

**Owns:** `commands/claude/oracle/market.md`, `commands/claude/oracle/checklist.md`
**estimated_lines:** 120

## Addendum: T-178 — Hook audit log + PTY threshold state snapshot

**Title:** Hook audit log + PTY threshold state snapshot — diagnose handoff stalls

**Goal:** PostToolUse hook appends to `.agentflow/hook_audit.jsonl` (task_id, action, tasks_json_write ok|failed, timestamp). `output_handler.py _log_audit` snapshots `_task_start_tokens` at every threshold evaluation. Enables replay of exactly what was in-memory when handoff gate checked.

**Milestone:** M-DP
**Owns:** `agentflow/hooks/post_tool_use.py`, `agentflow/shell/output_handler.py`

## Addendum: T-211 — Spike: agy/Gemini CLI session lifecycle

**Title:** Spike: agy/Gemini CLI session lifecycle — restart feasibility

**Goal:** Investigate agy session lifecycle: hook system, /clear command, token count per turn, skill injection, process model. Output: design_status.md entries (RESOLVED/UNRESOLVED) for each question + recommendation on whether agy restart parity is achievable in v1. Research only, no implementation.

**Owns:** `design_status.md`
**Model:** claude-sonnet-4-6
**estimated_lines:** 0

## Addendum: T-301 — Oracle handoff UX: proactive stopping-point prompt + PTY restart

**Goal:** When oracle session reaches 90K tokens, PTY injects a user-facing prompt: "For crisp decision making, taking forward the context into a new session is important. Session restart with context carried forward?" If user confirms: (1) oracle.md /handoff runs, (2) PTY restarts oracle session in `--auto` mode. No silent restart — user must consent.

**Files:**
- `agentflow/shell/session_manager.py` — add oracle session-type check + 90K threshold + prompt injection
- `commands/claude/oracle.md` — document the handoff trigger behaviour
- `commands/claude/handoff.md` — ensure /handoff works cleanly from oracle context

**Test scenarios:**
- Token count hits 90K in oracle session → prompt injected (not silent restart)
- User declines → session continues, no restart
- User confirms → /handoff runs, PTY restarts oracle in --auto, handoff file carries context
- Non-oracle session at 90K → unchanged behaviour (existing threshold applies)

**OWNS:** `agentflow/shell/session_manager.py`, `commands/claude/oracle.md`, `commands/claude/handoff.md`
**estimated_lines:** 60

## Addendum: T-302 — Customer distribution: standalone binary + strip .py + install archive

**Goal:** Package AgentFlow for friendly customers such that zero readable Python source is distributed. Builds on T-112 (Nuitka standalone compile). Adds: (1) post-build strip removes all .py/.pyc from dist/, (2) installs stub `.md` files into `~/.claude/commands/` — each stub instructs Claude to run `agentflow ip load-skill <skill>` and treat stdout as instructions (`load_skill.py` fetches key via T-109, decrypts `.enc` in memory, prints plaintext, exits — no disk write; design RESOLVED in design_status.md), (3) bundles binary + encrypted `.enc` skill files (T-110) + stub `.md` files + config templates into a versioned `.tar.gz`, (4) `install.sh` extracts archive, registers Claude Code hooks pointing at binary, writes stubs to `~/.claude/commands/`, smoke tests.

**Files:**
- `scripts/build_dist.sh` (new) — Nuitka standalone build + strip + bundle
- `scripts/install.sh` (new) — customer install: extract, register hooks, write stub .md files
- `scripts/stubs/` (new) — stub .md templates for oracle, orchestrate, handoff, debug, drift
- `Makefile` — add `dist` target calling build_dist.sh
- `tests/test_dist.sh` (new) — smoke test: install into temp dir, verify no .py files, run `agentflow --version`, verify stubs present

**Test scenarios:**
- `make dist` produces archive with zero .py/.pyc files
- install.sh on clean dir → hooks registered, stubs in ~/.claude/commands/, `agentflow --version` succeeds
- Stub .md content contains no skill logic — only `agentflow ip load-skill <name>` invocation
- `agentflow ip load-skill orchestrate` → decrypts + prints full skill content (T-109/T-110 path)
- Idempotent: running install.sh twice produces no duplicate hook entries or stub overwrites

**OWNS:** `scripts/build_dist.sh`, `scripts/install.sh`, `scripts/stubs/`, `Makefile`, `tests/test_dist.sh`
**estimated_lines:** 150

## Addendum: T-303 — Split post_tool_use_agent.py + size_check dedupe guard

**Goal:** (1) Split agentflow/hooks/post_tool_use_agent.py (271 lines, limit 250) — read file, identify distinct responsibilities, split by domain, verify each output ≤ 250 lines. (2) Add dedupe guard to size_check hook to prevent duplicate task auto-filing (root cause: 7 identical T-30x tasks filed in 8 min; guard should check tasks.json for existing task with same file path before filing).

**Owns:** ["agentflow/hooks/post_tool_use_agent.py", "agentflow/hooks/post_tool_use_pr.py", "agentflow/hooks/size_check.py", "tests/test_post_tool_use_agent.py", "tests/hooks/test_size_check.py"]
