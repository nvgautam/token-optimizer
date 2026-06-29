# AgentFlow — Design Decisions

Oracle reads on startup. Handoff writes updates. Architecture.md = workers only.

| Item | Status | Decision |
|---|---|---|
| Primary artifact | RESOLVED | Skills-first: .md for Claude, SKILL.md + scripts for Gemini |
| PTY LLM usage | RESOLVED | Zero LLM calls in PTY shell — fully deterministic |
| Token counting | RESOLVED | Local tiktoken, ~95% accuracy, acceptable for threshold detection |
| Handoff threshold | RESOLVED | 40K floor OR 30% ceiling — whichever fires first |
| Semantic handoff trigger | DEFERRED | TASK_COMPLETE signal primary; token threshold safety net — v2 |
| Velocity-based trigger | DEFERRED | Turn-delta tracking; trigger on accelerating growth (2nd derivative, 3-turn window) — v2 |
| Structured PTY signals | DEFERRED | TASK_COMPLETE:<id>, CHECKLIST_ITEM_RESOLVED:<id> to stdout — prerequisite for semantic trigger — v2 |
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
| Headless automation layer | DEFERRED | v2 — PTY approach validated in v1 first |
| Symbol indexer | RESOLVED | Standalone CLI; PTY runs on session start; skills read .idx before full files (~65% per targeted read) |
| Context builder | RESOLVED | context_builder.py assembles minimal bundle; orchestrate writes context_bundle.md per task; workers read only that |
| Oracle state doc | RESOLVED | design_status.md — oracle reads on startup, handoff writes on flush. Replaces decisions log in architecture.md. |
| Compact state docs | RESOLVED | Handoff writes design_status.md + execution_plan.md as tables/bullets; no prose. Prompt instruction only. |
| Verbosity control | RESOLVED | Skill prompts instruct concise responses; extends sessions ~25% before threshold fires |
| Section-only loading | RESOLVED | Task reads use anchors; skill prompts forbid full architecture.md load |
| Per-session thresholds | RESOLVED | oracle_threshold_tokens + orchestrator_threshold_tokens in config; session_manager reads per-type |
| Orchestrator persona | RESOLVED | Staff Eng Lead — executes, manages parallelism, escalates. No re-prioritization; oracle sets priority |
| Skill IP protection | DEFERRED | .md files readable — not IP-protected. PTY binary protects shell only. Prerequisite for commercial distribution. |
| Skill distribution mechanism | DEFERRED | Options: (1) embed+inject in binary; (2) server-side delivery at runtime. Blocked on tier/licensing. |
| Skill file location | RESOLVED | commands/ at project root (git-tracked). Copy to ~/.claude/commands/ or .claude/commands/. No pip dist of skill content. |
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
| PTY idx reminder injection | RESOLVED | Session manager counts turns; every 3 turns injects idx banner to stdin (~15 tokens). Recency effect recalibrates compliance lost to context growth. Part of T-008. |
| CacheAligner integration | DEFERRED | v2 — Headroom library; stabilizes prefixes for KV cache discount (~24% input token savings). Additive with all strategies. Evaluate after PTY validated. |
| ContentRouter integration | DEFERRED | v2 — Headroom library; compresses tool outputs before context ingestion (60-95% per output). Plugs into PTY I/O interception layer. |
| Mid-session /compact | DEFERRED | Not worth at current 30-60K handoff thresholds — sessions hand off before compaction helps. Revisit if thresholds raised significantly. |
| Verbosity compliance tracking | RESOLVED | Per-turn output token tracking in PTY (T-010) — writes verbosity_log.jsonl; shadow analyzer reports mean/p90 vs 150-token target. |
