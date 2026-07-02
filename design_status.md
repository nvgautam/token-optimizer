# AgentFlow — Design Decisions

Oracle reads on startup. Handoff writes updates. Architecture.md = workers only.

| Item | Status | Decision |
|---|---|---|
| Primary artifact | RESOLVED | Skills-first: .md for Claude, SKILL.md + scripts for Gemini |
| PTY LLM usage | RESOLVED | Zero LLM calls in PTY shell — fully deterministic |
| Token counting | RESOLVED | Local tiktoken, ~95% accuracy, acceptable for threshold detection |
| Handoff threshold | RESOLVED | 40K floor OR 30% ceiling — whichever fires first |
| Semantic handoff trigger | RESOLVED | Round-boundary handoff: ROUND_COMPLETE signal primary; token threshold safety net. Handoff fires only if accumulated_tokens > floor (shell.handoff_token_floor_pct, default 0.30 of threshold) — T-066 |
| Velocity-based trigger | DEFERRED | Turn-delta tracking; trigger on accelerating growth (2nd derivative, 3-turn window) — v2 |
| Structured PTY signals | RESOLVED | AGENTFLOW_TASK_START:<id>, AGENTFLOW_TASK_COMPLETE:<id>, AGENTFLOW_ROUND_COMPLETE to stdout; current_round.json written at round start — T-065 |
| Per-task token tracking | RESOLVED | PTY brackets TASK_START/COMPLETE signals; accumulates token delta per task; writes task_token_log.jsonl — T-067 |
| Parallel worker scheduling | RESOLVED | Orchestrate spawns N workers per round; N = max(1, floor(remaining/estimated_per_task)); estimated from task_estimator.json (≥5 samples) or 2500 fallback; owns disjoint check enforced — T-068, T-069 |
| Local observation proxy | DEFERRED | v2 — stdlib HTTP proxy at ANTHROPIC_BASE_URL; logs exact API usage fields; foundation for Caveman/Headroom compression integration |
| Handoff state | RESOLVED | Living docs (design_status.md, execution_plan.md); no separate handoff files |
| Session resume | RESOLVED | Oracle: UNRESOLVED in design_status.md. Orchestrator: incomplete milestones in execution_plan.md |
| execution_plan.md owner | RESOLVED | Oracle: M1 full tasks + milestone stubs; orchestrator fills lazily at milestone completion |
| tasks.json owner | RESOLVED | Oracle: M1 full defs + stubs; orchestrator extends lazily at milestone boundaries |
| Staleness detection | RESOLVED | Document state, not timestamps |
| Symbol index location | RESOLVED | ~/.agentflow/cache/<hash>/index/ — never in project tree |
| Index update trigger | RESOLVED | write_file tool side-effect; worker unaware |
| Brownfield support | RESOLVED | Index generation v1; file refactoring v2 |
| Prompt injection | RESOLVED | Oracle asks user; generates tasks if applicable; AgentFlow sanitises oracle input |
| Human PR review | RESOLVED | HUMAN_APPROVED enforced gate before any merge |
| Idempotency | RESOLVED | Cross-cutting; all operations safe to run twice |
| PTY countdown | RESOLVED | 5s default; configurable by tier (Free: fixed; Pro: user; Enterprise: admin) |
| Providers v1 | RESOLVED | Claude Code + Gemini CLI |
| Tier/licensing | DEFERRED | Compiled binary + server-side components likely — design pending |
| Naming/branding | DEFERRED | PTY shell needs distinct product name |
| Codex provider | DEFERRED | v2 |
| Brownfield refactoring | DEFERRED | v2 — requires existing test suite, per-file human approval |
| OTel exporter | DEFERRED | v2 — JSONL schema already OTel-compatible |
| Merge sequencer | DEFERRED | v1 manual merge acceptable; automated sequencer v2 |
| PTY sequencing | RESOLVED | PTY built alongside skills in v1 — product IS skills + PTY shell. Headless layer v2. |
| v1 milestone order | RESOLVED | M1: skill files → M2: symbol indexer (inline) → M3: PTY shell → v2: headless |
| Headless automation layer | DEFERRED | Confirmed dead 2026-07-01 — oracle/orchestrator/worker/reviewer/tools API-mode subtree never wired into cli.py or any skill; marked deferred (v2) in architecture.md, not documented as live. Re-derive from scratch if ever revived — don't resume from the killed snapshot. |
| Symbol indexer | RESOLVED | Standalone CLI; PTY runs on session start; skills read .idx before full files (~65% per targeted read) |
| Context builder | RESOLVED | context_builder.py assembles minimal bundle; orchestrate writes context_bundle.md per task; workers read only that |
| Oracle state doc | RESOLVED | design_status.md — oracle reads on startup, handoff writes on flush. Replaces decisions log in architecture.md. |
| Compact state docs | RESOLVED | Handoff writes design_status.md + execution_plan.md as tables/bullets; no prose. Prompt instruction only. |
| Verbosity control | DEFERRED | v2 — motivation is output token cost (3-5x input rate), not context accumulation (ContentRouter handles that). Injection via ContentRouter system prompt modifier. Not a v1 necessity. |
| Section-only loading | RESOLVED | Task reads use anchors; skill prompts forbid full architecture.md load |
| Per-session thresholds | RESOLVED | oracle_threshold_tokens + orchestrator_threshold_tokens in config; session_manager reads per-type |
| Orchestrator persona | RESOLVED | Staff Eng Lead — executes, manages parallelism, escalates. No re-prioritization; oracle sets priority |
| Skill IP protection | DEFERRED | .md files readable — not IP-protected. PTY binary protects shell only. Prerequisite for commercial distribution. |
| Skill distribution mechanism | DEFERRED | Options: (1) embed+inject in binary; (2) server-side delivery at runtime. Blocked on tier/licensing. |
| Skill file location | RESOLVED | commands/claude/ (Claude) and commands/gemini/ (Gemini) at project root (git-tracked). Copy to ~/.claude/commands/ or .claude/commands/ from commands/claude/. No pip dist of skill content. |
| Gemini provider | RESOLVED | AGY skills (orchestrate, handoff, AGENTS.md) built and verified; Gemini serves as orchestrator |
| Orchestrator round-sizing | RESOLVED | max_tasks = max(1, remaining_tokens / pct_cost). Default pct_cost=2500. Encoded in orchestrate.md. |
| Token savings validation | RESOLVED | Stale skills caused missing savings 2026-06-26 (oracle 232L→126L; orchestrate 422L→140L). Re-spar ≤15% confirmed. |
| Architecture drift detection | DEFERRED | Low-cost sync check: every architecture.md line traceable to skill/code. Blocked on token savings validation. |
| .idx index format | RESOLVED | Plaintext name:start-end. Python: functions, classes, methods (ClassName.method). Markdown: H2/H3. <50 lines skipped. |
| Inline indexing approach | RESOLVED | Orchestrate generates .idx in pre-spawn (ast for .py, grep for .md). No standalone CLI for validation. |
| Concurrent orchestrator prevention | RESOLVED | Lock file .agentflow/orchestrator.lock with PID, provider, timestamp — prevents concurrent runs |
| Rate cap derivation | RESOLVED | Ledger-anchored: cap = total_window_tokens / (pct/100). Local time only (no tz). Gap: add unbilled current session. Weekly derived first. |
| Read hook enforcement | RESOLVED | PTY stream detection: strip ANSI, regex-match Read + file path, inject targeted [IDX] banner if .idx exists. Event-driven, no Claude Code hook dependency. T-052. |
| Hook IP protection | DEFERRED | PTY approach has no IP surface; hook binary approach moot. Revisit v2 only if distribution model requires it. |
| Telegraphic artifact style | RESOLVED | All artifacts: no articles, bullets over prose, ≤10 words per idea. generation.md enforces; existing compressed via T-048/T-049. ~20–30% token reduction. |
| PTY idx reminder injection | RESOLVED | Stdin injection disruptive — visible in user input field. Move to UserPromptSubmit hook: fires invisibly before each user turn, turn-conditioned (every 3 turns), recency preserved. ContentRouter wrong layer — system prompt has no recency advantage. |
| CacheAligner integration | RESOLVED | Superseded — T-071 confirmed `headroom wrap` runs CacheAligner as TransformPipeline stage 1 automatically; delivered by T-074's base wiring, not separate v2 work |
| ContentRouter integration | RESOLVED | Superseded — T-071 confirmed `headroom wrap` runs ContentRouter as TransformPipeline stage 2 automatically; delivered by T-074's base wiring, not separate v2 work |
| Mid-session /compact | DEFERRED | Not worth at current 30-60K handoff thresholds — sessions hand off before compaction helps. Revisit if thresholds raised significantly. |
| Verbosity compliance tracking | RESOLVED | Per-turn output token tracking in PTY (T-010) — writes verbosity_log.jsonl; shadow analyzer reports mean/p90 vs 150-token target. |
| Verbosity signal reliability | RESOLVED | Write-on-exit-only lost data across `/clear` cycles (no real process exit) — zero oracle-tagged entries despite completed oracle sessions confirmed. T-052/T-055 "proactive banner" never implemented despite MERGED (dead `_verbosity_last_inject`). Fix: incremental per-turn writes; new UserPromptSubmit hook `verbosity_reminder.py` (separate from idx_reminder.py, own counter, 1–2 turn cadence) — T-073 |
| Gemini idx injection mechanism | RESOLVED | Use PreInvocation hook in .agents/hooks.json. Fires before model invocation; runs script that maintains counter file and prints [IDX] reminder every 3rd turn to dynamically inject context. Invisible to user, preserves recency. |

## Oracle Direction — Sparred 2026-06-30

| Item | Status | Decision |
|---|---|---|
| Oracle 4-stage expansion | DEFERRED | Expand to: (1) market+product spec, (2) architecture, (3) engineering+token optimization, (4) QA acceptance criteria; blocked on first customer conversation — build with them, not before |
| Universal requirements taxonomy | DEFERRED | Replace per-market checklists with cross-cutting taxonomy (Security, Compliance, Observability, Reliability, Scale, Privacy) + silent market-segment overlays applied at spar time; shallow compliance depth agreed (flag what applies; no legal liability accepted) |
| Oracle IP protection — checklist content | RESOLVED | Taxonomy + overlays embed in PTY binary (Nuitka compile-time); server-side delivery for commercial tier; .md files on disk not acceptable for IP-sensitive content |
| Oracle brownfield mode | DEFERRED | Separate `/oracle --brownfield` skill; reads existing architecture + tech debt before sparring; different startup sequence from greenfield |
| QA acceptance criteria ownership | RESOLVED | Oracle writes acceptance criteria per milestone at generation time; test scaffolding + evaluation belong to worker/reviewer pipeline — not oracle |
| Delivery timeline propagation | DEFERRED | Oracle captures user-stated delivery timelines; propagates as ordering constraint into milestone sequencing; v2 design — needs milestone management integration |
| SRE persona | DEFERRED | Fold SRE concerns (observability, alerting, runbooks) into Stage 2 architecture checklist batch; not a separate oracle stage |
| Headroom/ContentRouter integration | RESOLVED | T-071 complete: fully composable (HTTP proxy vs PTY I/O — orthogonal layers); PTY invokes `headroom wrap claude`; workspace isolated to `.headroom/` per project; Intel macOS needs Homebrew onnxruntime workaround |
| Headroom SharedContext for M5 | DEFERRED | Workers operate on disjoint tasks by design — no cross-process context sharing needed in v1; task claiming already solved via file locks (T-063); revisit if same-file reads across providers become a measured problem |
| Demo report generator | RESOLVED | No build needed — `headroom.reporting.generator.generate_report()` produces HTML dashboard from `savings_events.jsonl` ledger; `agentflow report` subcommand wraps it; add as task after T-067 data populates ledger |
| Monetization positioning | RESOLVED | Cost + compliance, not orchestration features; target AI-first startups $5K–20K/month API spend; PTY measurement layer + compliance taxonomy = moat competitors lack |
| Customer conversation timing | RESOLVED | Start discovery conversations now (no code needed); live demo after M4 addendum (T-067) + report generator landed; build compliance taxonomy depth with first customer, not speculatively |

## Oracle Direction — Sparred 2026-07-01

| Item | Status | Decision |
|---|---|---|
| Savings-across-strategies task | RESOLVED | T-072 was earmarked (2026-07-01 handoff) but never written to tasks.json — gap closed; combines headroom's compression ledger + shadow analyzer's idx/read numbers into one demo report, no invented aggregate percentage |
| Headroom savings estimate | RESOLVED | Vendor's 60%+ context-reduction claim (headroom_eval.md) not assumed to transfer as-is — AgentFlow's own idx targeted-reads already strip much of the large tool-output payload Headroom targets hardest; real incremental number must be measured via T-072, not quoted from vendor docs |
| Headroom cross-provider scope | RESOLVED | T-074 wires Claude path (interception mechanism confirmed Claude-Code-specific in eval doc). Gemini path unverified — task must empirically confirm savings_events.jsonl gets entries from a headroom-wrapped Gemini session before claiming cross-provider savings; PTY's own benefits (token counting, idx/verbosity hooks) unaffected either way — confirmed orthogonal (network proxy vs terminal I/O) |
| Code-size threshold gap | RESOLVED | size_check.py (T-058) is Claude-Code-specific PostToolUse hook — never fires on pre-existing files (agentflow.py was 960+ lines at first commit) or Gemini CLI writes. T-075 splits agentflow.py; T-076 adds a periodic audit sweep + investigates a Gemini-side equivalent |
| Report modes | RESOLVED | T-072 expanded: two modes — aggregate (single deduped total) + by-strategy (each strategy separate); analyzer.py's targeted-reads/no-reread filters overlap (double-count bug), fixed via priority-order bucketing for aggregate mode only. Verbosity (T-073 log) and headroom (get_summary_stats, not just generate_report()) added as strategies feeding both modes. |
| Model tiering by task complexity | DEFERRED | Route each task to a cost-appropriate model (Haiku/Sonnet/Opus) instead of one fixed model for every worker spawn. Decision belongs to orchestrator at spawn time (reuse existing classify_task() mechanical/exploratory signal), not oracle at design time — oracle has no code context to judge complexity accurately. Blocked on an escalation path (retry on stronger model when a cheap-tier worker fails/gets rejected) that doesn't exist yet. Fits the cost+compliance moat (Monetization positioning, above) but is new scope beyond current M4 addendum — revisit at a future milestone (M6 Parallel Execution or later), not folded into in-flight tasks. |
| Report command unification | RESOLVED | Two undocumented competing report entrypoints found: `agentflow report` (report_builder.py, T-072, global aggregate/split, no per-session/agent view) vs `python agentflow.py report` (legacy_report.py, per-session table + `--agent claude/agy` filter, user-relied-on). Unified into one command surface: `agentflow report --mode aggregate\|split\|session`, `--mode session` reuses legacy_report.py logic as-is + `--agent` filter. Backing files stay separate; root `agentflow.py report` retired outright — no back-compat alias, no external users yet. Both underlying data sources (ledger vs shadow_reads/verbosity/headroom) are untouched by the CLI merge, so historical session data for before/after comparison is preserved automatically. T-078. |
| Headroom stale-Read protection | SUPERSEDED | Incident 2026-07-01: /orchestrate flagged garbled-looking Read/Grep results on design_status.md + rate_calibration_claude.json, correctly paused instead of acting. Original diagnosis (T-079) was wrong: claimed `cli.py`'s `headroom wrap claude` (no flags) "leaves the [exclude-tools] default intact." False — see "ContentRouter mode default" below. `ReadLifecycleConfig` staleness marker (`compress_stale=True`) is real but was not the mechanism observed. Skill-level rule (always fresh same-turn Read before any gate decision) still correct and kept. |
| ContentRouter mode default | RESOLVED | Root cause of the 2026-07-01 incident, traced in headroom's installed source (`.venv/.../headroom/proxy/modes.py`, `server.py:637`, `transforms/content_router.py:2935`): `headroom wrap` with no `HEADROOM_MODE` set resolves via `normalize_proxy_mode(mode, default="token")` to **token mode**, which sets `protect_recent_reads_fraction = 0.3` — overriding the library's own safe default (`0.0` = protect all `DEFAULT_EXCLUDE_TOOLS` outputs unconditionally). Under token mode, excluded-tool (Read/Grep/Write/Edit) results older than ~30% of the conversation fall through to SmartCrusher compression despite being "excluded" — exactly what happened to `design_status.md` and `.idx` reads. Fix: `cli.py` sets `HEADROOM_MODE=cache` explicitly alongside `HEADROOM_WORKSPACE_DIR` so the protective `0.0` default holds regardless of session length — T-080. Belt-and-suspenders: hook-injected `idx_reminder`/`verbosity_reminder` text isn't a tool_result block (can't rely on `exclude_tools`) — wrap in a custom XML tag, protected verbatim via `compress_tagged_content=False` (default) — T-080. Scope: applies to any AgentFlow-authored payload already minimized by strategies #4/#6/#8/#5 (symbol index, compact state docs, section-only loading, lazy decomposition) — further compression there is near-zero benefit and risks destroying structural fidelity (e.g. a crushed `.idx` lookup table loses its line ranges). |

## Oracle Direction — Sparred 2026-07-02

| Item | Status | Decision |
|---|---|---|
| combined_report.html anomalies | RESOLVED | User flagged idx=0, headroom compression=0, verbosity still unmeasured, no session-recycling bucket. Root-caused all four — see below. T-082/T-083 filed. |
| Headroom compression=0 | RESOLVED | Not a modeling bug — a wrong data source. `report_builder.py` falls back to `~/.headroom/headroom.db` (SQLite, `headroom.storage.create_storage`) when no project-local `.headroom/headroom.db` exists; that DB has 0 requests. Real telemetry for this project lives in `.headroom/proxy_savings.json` (JSON ledger — 1,027 requests, 9,035,421 lifetime tokens_saved measured 2026-07-02). `get_summary_stats()` is querying an empty/unrelated store. T-082. |
| idx=0 in strategy breakdown | RESOLVED | Not a bug — a mislabeled but structurally-correct zero. `get_bucketed_stats`' "targeted-reads" bucket only increments when `idx_exists AND offset is None` (i.e. a full read despite an available index — waste). `report_builder.py`'s `_is_blocked_attempt()` (T-081, anti-double-count) strips exactly those rows before they reach the analyzer, because `read_check.py` blocks them at exit 2 before the read executes — zero real cost, so correctly excluded from cost math. Net effect: the idx bucket can now only read 0, and 0 is the *correct* value once read_check.py enforces 100% compliance. Realized idx savings are already counted elsewhere, in `total_saved` via `file_reads_real`/`file_reads_baseline`. The zero is right; the section calls it a "savings" figure when it's a "waste" figure. T-083 relabels. |
| Verbosity still unmeasured (n=0) | RESOLVED | Not a bug. T-081 built the A/B baseline mechanism (`verbosity_ab.py`, `load_baseline`) but the comparison hasn't been run yet — `[UNMEASURED baseline=600tok, n=0]` is the designed fallback state until that A/B run executes. No task needed; run the T-081 A/B comparison when convenient. |
| Session-recycling (handoff) strategy missing from report | DEFERRED | Strategy #1 (Handoff/context cycling, architecture.md) was never modeled as a `get_bucketed_stats` bucket — pure scope gap, not a regression. Measuring it needs PTY handoff-event correlation (pre-handoff token count vs resumed-session compact-doc token count), a different data shape from the reads-log-driven buckets. New scope, not a quick fix — revisit as its own task if/when handoff-driven savings need to be demoed, don't fold into T-082/T-083. |
| Report metric semantics | RESOLVED | Going forward, `get_bucketed_stats` buckets (idx, no-reread, indexing-gap) are shadow *waste* metrics (lower is better, 0 = full compliance) — never sum them into achieved-savings totals. Only `file_reads_saved`, `verbosity_savings`, `compression_savings` are real realized savings. T-083 encodes this split in the report's presentation layer. |
