# AgentFlow — Design Decisions

Oracle state: RESOLVED / UNRESOLVED / DEFERRED items. Oracle reads this file on startup (not architecture.md).
Handoff writes updates here. Architecture.md is the design reference — read by workers, not oracle.

| Item | Status | Decision |
|---|---|---|
| Primary artifact | RESOLVED | Skills-first: .md files for Claude, SKILL.md + scripts for Gemini |
| PTY LLM usage | RESOLVED | Zero LLM calls in PTY shell — fully deterministic |
| Token counting | RESOLVED | Local tiktoken, ~95% accuracy, acceptable for threshold detection |
| Handoff threshold | RESOLVED | Hybrid: absolute 40K floor OR 30% of window ceiling — whichever fires first |
| Semantic handoff trigger | DEFERRED | Task completion (TASK_COMPLETE signal) as primary trigger; token threshold as safety net — v2 |
| Velocity-based trigger | DEFERRED | Track turn-over-turn input delta; trigger on accelerating growth (second derivative positive over 3-turn window) — v2 |
| Structured PTY signals | DEFERRED | Skills emit TASK_COMPLETE:<id> and CHECKLIST_ITEM_RESOLVED:<id> to stdout for PTY consumption — prerequisite for semantic trigger — v2 |
| Handoff state | RESOLVED | Living documents (design_status.md, execution_plan.md) — no separate handoff files |
| Session resume | RESOLVED | Oracle: UNRESOLVED items in design_status.md. Orchestrator: incomplete milestones in execution_plan.md |
| execution_plan.md owner | RESOLVED | Oracle creates milestone structure + full tasks for Milestone 1; orchestrator lazily fills tasks for each subsequent milestone when prior milestone completes |
| tasks.json owner | RESOLVED | Oracle writes full task definitions for Milestone 1 only; stubs for future milestones; orchestrator extends lazily at milestone boundaries |
| Staleness detection | RESOLVED | Document state, not timestamps |
| Symbol index location | RESOLVED | ~/.agentflow/cache/<hash>/index/ — never in project tree |
| Index update trigger | RESOLVED | write_file tool side-effect; worker unaware |
| Brownfield support | RESOLVED | Index generation v1; file refactoring v2 |
| Prompt injection | RESOLVED | Oracle asks user; generates tasks if applicable; AgentFlow itself sanitises oracle input |
| Human PR review | RESOLVED | HUMAN_APPROVED enforced gate before any merge |
| Idempotency | RESOLVED | Cross-cutting constraint; all operations safe to run twice |
| PTY countdown | RESOLVED | 5s default; configurable by tier (Free: fixed; Pro: user; Enterprise: admin) |
| Providers v1 | RESOLVED | Claude Code + Gemini CLI |
| Tier/licensing | DEFERRED | To be designed; compiled binary + server-side components likely |
| Naming/branding | DEFERRED | PTY shell needs a distinct product name |
| Codex provider | DEFERRED | v2 |
| Brownfield refactoring | DEFERRED | v2 — requires existing test suite, per-file human approval |
| OTel exporter | DEFERRED | v2 — JSONL schema already OTel-compatible |
| Merge sequencer | DEFERRED | v1 manual merge acceptable; automated sequencer v2 |
| PTY sequencing | RESOLVED | PTY is built alongside skills in v1 — the product IS skills + PTY shell. Headless automation layer is v2. |
| v1 milestone order | RESOLVED | 1: skill files → 2: symbol indexer (via orchestrate skill inline) → 3: PTY shell → v2: headless automation layer |
| Headless automation layer | DEFERRED | v2 — see Module boundaries for full list. PTY approach validated in v1 first before building headless runners. |
| Symbol indexer | RESOLVED | v1 — standalone CLI tool; PTY shell runs on session start; skills instruct Claude to read .idx before full files. Highest-leverage read optimisation (~65% per targeted read). |
| Context builder | RESOLVED | v1 — context_builder.py assembles minimal bundle; orchestrate skill writes context_bundle.md per task to disk; workers read only that file on session start. |
| Oracle state doc | RESOLVED | design_status.md (this file) — oracle reads on startup, handoff writes on flush. Replaces decisions log embedded in architecture.md. |
| Compact state docs | RESOLVED | v1 — handoff skill writes design_status.md and execution_plan.md in dense structured format (tables/bullets, no prose). Prompt instruction only, no code. |
| Verbosity control | RESOLVED | v1 — all skill system prompts instruct Claude to keep responses concise. Extends sessions by ~25% before threshold fires. |
| Section-only loading | RESOLVED | v1 — task reads fields use anchors (already enforced); skill prompts explicitly forbid loading full architecture.md. |
| Per-session thresholds | RESOLVED | v1 — config adds oracle_threshold_tokens and orchestrator_threshold_tokens; session_manager reads per-type threshold on session detection. |
| Orchestrator persona | RESOLVED | Staff Engineering Lead — executes plan faithfully, manages parallelism and failure, escalates to human when authority exceeded. Does not re-prioritize. Oracle (Senior PE + PM + Designer) sets priority; orchestrator delivers it. |
| Skill IP protection | DEFERRED | `.md` skill files on disk are readable — not IP-protected. PTY binary protects shell mechanics only. Prerequisite for commercial distribution. |
| Skill distribution mechanism | DEFERRED | Two options: (1) embed+inject — PTY binary carries compiled skill content, unpacks to `~/.claude/commands/` on install/update; (2) server-side delivery — PTY fetches skills from server at runtime, never writes to disk (strongest IP protection, requires connectivity). Decision blocked on tier/licensing design. Determines both install flow and update mechanism. |
| Skill file location | RESOLVED | `commands/` directory at project root (git-tracked). Users copy to `~/.claude/commands/` (global) or `.claude/commands/` (project-scoped). No pip package distribution of skill content — IP protection mechanism deferred. |
| Gemini provider | RESOLVED | Built and verified equivalent agy skills (orchestrate, handoff, and AGENTS.md), enabling Gemini/AGY to serve as an orchestrator. |
| Orchestrator round-sizing | RESOLVED | Before each round: `max_tasks = max(1, (orchestrator_threshold_tokens - current_tokens) / tokens_per_task_estimate)`. Prevents context blowout mid-round. Config: `shell.tokens_per_task_estimate` default 2500. Encoded in commands/orchestrate.md skill logic. |
| Token savings validation | RESOLVED | Root cause of missing savings identified 2026-06-26: deployed skills were pre-T-026/T-027 stale versions (oracle 232L vs 126L; orchestrate 422L vs 140L). Synced. Empirically confirmed 2026-06-26: re-spar context ≤15% with new skills (vs 24% with stale). Hypothesis validated. |
| Architecture drift detection | DEFERRED | Explore low-cost deterministic sync check between architecture.md and implementation (skills + code). Hypothesis: every line in architecture.md should be traceable to a skill file or source file. Handoff owns the sync enforced path; this is for catching drift from direct edits. Prerequisite: validate token savings hypothesis first. |
| .idx index format | RESOLVED | Plaintext, one symbol per line: name:start-end. Python: top-level functions, classes, and class methods (ClassName.method:start-end). Markdown: H2/H3 headers (## Header:start-end). Files < 50 lines skipped. No JSON/YAML indexing. |
| Inline indexing approach | RESOLVED | Orchestrate skill generates .idx files during pre-spawn (ast for Python, grep for Markdown). No standalone CLI tool needed to validate token savings. Python CLI modules (T-028, T-029) deferred until inline approach empirically validated. |
| Concurrent orchestrator prevention | RESOLVED | Serial execution lock: PTY shell / orchestrator uses a lock file (`.agentflow/orchestrator.lock`) containing active PID, provider, and timestamp to prevent concurrent orchestrator runs on the same project repository. |
| Rate cap derivation | RESOLVED | Ledger-anchored: cap = total_billable_tokens_since_window_start / (current_pct / 100). More accurate than single-session delta (session_tokens / delta_pct) — full window base reduces variance. Ledger timestamps are local time (datetime.now(), no tz). 5hr window start = reset_time - 5h; weekly window start = reset_time - 7d. Unbilled current-session tokens (not yet flushed to ledger) are a known gap — correct by adding current-session delta explicitly. |
| Read hook enforcement | RESOLVED | Claude Code PreToolUse hook fires a script before every Read call. Script checks .idx existence + whether offset is absent; if targeted read is available, outputs a brief opaque instruction to Claude. Output must not reveal optimization strategy to terminal observers — generic phrasing only. v1: Python script at agentflow/hooks/read_check.py. v2: compiled Nuitka binary alongside PTY shell. Hook registered in .claude/settings.json (project-scoped). |
| Hook IP protection | DEFERRED | Hook source (read_check.py) reveals optimization strategy. v1 accepts this — file is in project repo but not distributed. v2: compile to binary (Nuitka); exclude source from distribution package. Hook output in terminal is opaque by design (generic phrasing). Full IP protection requires: compiled hook binary + compiled PTY binary + server-side skill delivery (see Skill IP protection). All three must ship together. |
