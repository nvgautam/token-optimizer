# AgentFlow — Architecture

Provider-agnostic multi-agent project management delivered as skills + PTY overlay shell. Given a project description, the oracle spars with the user to produce a living architecture document, the orchestrator decomposes it into milestones and tasks, headless workers implement each task in an isolated worktree, and the PTY shell manages context lifecycle transparently across all sessions.

---

## Guiding principles

- **Skills-first**: the primary artifacts are skill files (`.md` for Claude, `SKILL.md` + scripts for Gemini). Python modules are the runtime backing those skills.
- **Token-first**: context is cycled at task boundaries; workers receive minimal context bundles; symbol index enables targeted file reads instead of full-file reads.
- **Living documents**: `architecture.md`, `execution_plan.md`, and `tasks.json` are continuously updated state — not written once and forgotten.
- **Prove before automating**: token savings are delivered by the skills + state documents. PTY shell automates the handoff trigger and protects IP — built last, after savings are empirically validated with manual handoffs.
- **Idempotency**: every operation is safe to run twice. Starting oracle or orchestrator on an existing project resumes from current state.
- **IP by obscurity of mechanism**: symbol index files live outside the project tree; the PTY shell ships as a compiled binary. Skill content distribution mechanism is UNRESOLVED — `.md` files on disk are not IP-protected.

---

## System overview

```
User types: claude / gemini                   ← existing AI CLI, unchanged
         ↑
  ┌──────┴──────────────────────────────────┐
  │         PTY Overlay Shell               │  ← wraps the AI CLI process
  │  local tokenizer · threshold watch      │    zero LLM calls
  │  session type detection · countdown     │    stdlib only
  │  /handoff inject · /clear inject        │
  │  skill restart coordination             │
  └──────┬──────────────────────────────────┘
         │  injects /oracle or /orchestrate
         ↓
  ┌──────────────────┐    ┌──────────────────────────────────────────┐
  │  Oracle skill    │    │  Orchestrator skill                       │
  │  (Claude/Gemini) │    │  (Claude/Gemini)                         │
  │                  │    │                                           │
  │  multi-persona   │    │  reads architecture.md                    │
  │  market-aware    │    │  reads tasks.json, writes execution_plan.md │
  │  checklist       │    │  spawns headless workers                  │
  │                  │    │  manages reviewer pipeline                │
  │  writes:         │    │  gates on HUMAN_APPROVED                  │
  │  architecture.md │    │  merges in DAG order                      │
  │  CLAUDE.md       │    └──────────────┬───────────────────────────┘
  └──────────────────┘                   │  per task
                              ┌──────────▼──────────────┐
                              │  Headless Worker Agent   │
                              │  reads context bundle    │
                              │  write_file → .idx hook  │
                              │  TDD: red→green→PR       │
                              └──────────┬──────────────┘
                                         │  PR opened
                              ┌──────────▼──────────────┐
                              │  Reviewer Pipeline       │
                              │  code reviewer           │
                              │  security reviewer       │
                              └──────────┬──────────────┘
                                         │  Human approves
                                    Merge (DAG order)
```

---

## Module boundaries

```
commands/                           # Claude Code skill files (git-tracked; copy to .claude/commands/)
  oracle.md                       # Claude oracle skill — lazy-loads oracle/ sub-files per phase
  orchestrate.md                  # Claude orchestrate skill
  handoff.md                      # Claude handoff skill
  oracle/
    market.md                     # market segment branching (loaded in Phase 1 only)
    checklist.md                  # NFR question bank (loaded in Phase 2 only)
    generation.md                 # artifact format spec (loaded in Phase 3 only)
  worker/
    system.md                     # worker persona + no-re-read rule (embedded in spawn prompts)
    context_bundle.md             # bundle format interpretation guide
    testing_guide.md              # TDD rules for workers
  reviewer/
    code_review.md                # code review checks (embedded in review prompts)
    security_review.md            # security review checks
    test_review.md                # test quality checks
  orchestrator/
    planning.md                   # milestone decomposition format guide
agentflow/
  cli.py                          # entry points, arg dispatch
  shell/
    pty_wrapper.py                # PTY process lifecycle, I/O interception
    tokenizer.py                  # local token counting per provider (tiktoken)
    session_manager.py            # threshold watch, session type, restart coordination
    countdown.py                  # configurable countdown with SIGINT handler
  oracle/
    checklist.py                  # market-aware NFR checklist, confidence scoring
    artifact_generator.py         # writes architecture.md + CLAUDE.md
    prompts/v1/
      system.md                   # multi-persona: Senior PE + PM + Designer
      market.md                   # market segment branching (consumer/SMB/enterprise)
      checklist.md                # NFR question bank, 23+ items
      generation.md               # artifact output format spec
  orchestrator/
    execution_plan.py             # architecture.md → milestones → execution_plan.md
    task_decomposer.py            # milestone → tasks.json entries (lazy, per milestone)
    state_machine.py              # task state transitions with timestamps
    environment.py                # tech-stack aware env setup (python/node/go/ruby)
    project_manager.py            # PM loop: spawns workers, handles results, reviewer trigger
    merge_sequencer.py            # post-HUMAN_APPROVED ordered merge, worktree cleanup
    prompts/v1/
      system.md                   # orchestrator persona: Staff Engineering Lead
      planning.md                 # milestone decomposition format
  worker/
    context_builder.py            # assembles minimal context bundle with index lookups
    agent_runner.py               # headless API agent, TDD loop, budget restart
    write_file_tool.py            # write_file + automatic .idx regeneration side-effect
    prompts/v1/
      system.md                   # implementer persona, no-re-read rule
      context_bundle.md           # bundle format and interpretation
      testing_guide.md            # TDD: red→green, behaviour not implementation
  reviewer/
    code_reviewer.py              # contract adherence, architecture conformance
    security_reviewer.py          # OWASP Top 10, secrets, compliance constraints
    prompts/v1/
      code_review.md
      security_review.md
      test_review.md
  indexer/
    index_manager.py              # cache path: ~/.agentflow/cache/<hash>/index/<mirrored-path>.idx
    brownfield_scanner.py         # scan existing project files on first load, build initial index
    parsers/
      python_parser.py            # ast-based: functions, classes, signatures, line ranges
      markdown_parser.py          # H2/H3 headers, line ranges
      json_parser.py              # top-level keys + line ranges (files > 30 lines only)
      yaml_parser.py              # top-level and second-level keys (files > 30 lines only)
  tools/
    git.py                        # worktree create/delete, commit, branch
    github.py                     # PR create, inline comments, status checks (httpx)
    test_runner.py                # run tests in worktree, parse coverage
    file_validator.py             # enforce file size limits, fail with rework message
  telemetry/
    logger.py                     # structured JSON logger, trace IDs, JSONL output
    token_tracker.py              # per-span attribution, shadow model, budget enforcement
    ledger.py                     # .agentflow/ledger.json r/w, project_total, session_total
  config/
    loader.py                     # layered resolution: env → project → user → defaults
    schema.py                     # Pydantic v2 models for all config fields
    defaults.yaml                 # shipped defaults
pyproject.toml
```

---

## Provider support

| Provider | Skill format | Handoff command | Tokenizer |
|---|---|---|---|
| Claude Code | `.md` in `commands/` (git-tracked source → copy to `~/.claude/commands/` or `.claude/commands/`) | `/handoff` | `tiktoken` cl100k_base |
| Gemini CLI | `SKILL.md` + scripts | `/handoff` | `tiktoken` cl100k_base (approx) | — deferred |
| Codex | — | — | — v2 |

Token counting uses `tiktoken` for all providers. ~95% accuracy is sufficient for a 40% threshold trigger.

Skill file location: `commands/` is the canonical source in the repo. IP distribution mechanism is UNRESOLVED — `.md` files are human-readable. PTY binary protects shell mechanics; skill content protection deferred to commercial distribution design.

---

## State documents

### architecture.md (oracle's living state)

Each design item carries an explicit status:

```markdown
## Authentication
Status: RESOLVED
Decision: JWT tokens, 24h expiry, refresh via httpOnly cookie

## Rate limiting
Status: UNRESOLVED
Open: per-user vs per-IP? burst allowance?

## Audit logging
Status: DEFERRED
Reason: v2 scope — agreed 2026-06-25
```

Oracle startup logic:
1. Read `architecture.md`
2. Any `UNRESOLVED` items (not `DEFERRED`)? → resume sparring from those items
3. All items `RESOLVED` or `DEFERRED`? → oracle is complete, prompt user to run orchestrator
4. File absent? → fresh project, start from scratch

The `/handoff` skill flushes current resolution state to `architecture.md` before `/clear`. No separate handoff file — the document IS the session state.

### execution_plan.md (oracle-created, orchestrator-extended)

Created by the oracle at sparring completion. Contains full milestone structure with task assignments for Milestone 1 and stubs for subsequent milestones.

```markdown
## Milestone 1: Foundation
Status: COMPLETE
Architecture: architecture.md#module-boundaries
Tasks: T-001 (MERGED)

## Milestone 2: Skill Files
Status: IN_PROGRESS
Architecture: architecture.md#oracle-design, architecture.md#orchestrator-design
Tasks: T-013 (PENDING), T-014 (PENDING), T-015 (PENDING),
       T-025 (PENDING), T-026 (PENDING), T-027 (PENDING)

## Milestone 3: Config + PTY Shell
Status: PENDING — tasks decomposed when Milestone 2 completes
Architecture: architecture.md#pty-shell-design, architecture.md#config-schema

## Milestone 4: Symbol Indexer
Status: PENDING — tasks decomposed when Milestone 3 completes
Architecture: architecture.md#symbol-indexer

## Milestone 5: Context Builder
Status: PENDING — tasks decomposed when Milestone 4 completes
Architecture: architecture.md#context-bundle

## Deferred
- Codex provider: v2
- Brownfield file refactoring: v2
- Headless automation layer: v2
- Tier/licensing: TBD
```

Orchestrator startup:
1. Read `execution_plan.md` (oracle-created) — any milestones not `COMPLETE`? → resume from first incomplete milestone
2. If current milestone's tasks are stub-only → decompose now using the milestone's architecture anchor, write full tasks to `tasks.json`
3. Read `tasks.json` — pick up in-flight tasks, spawn pending ones
4. All milestones `COMPLETE`? → project done

---

## Oracle design

### Multi-persona checklist

The oracle embodies three roles simultaneously: Senior Principal Engineer, Senior Principal Product Manager, Senior Principal Designer. Questions are not asked in isolation — the market segment answer gates which subsequent questions are relevant.

**Market segment question (asked first):**
> "Who is your primary user — consumer (B2C), small/medium business (SMB), or enterprise? Describe them in one sentence."

Market segment drives:
| Segment | Compliance defaults | Auth defaults | Deployment defaults | Scale defaults |
|---|---|---|---|---|
| Consumer | GDPR if EU, COPPA if minors | OAuth social login | Cloud, mobile-first | Viral growth, elastic |
| SMB | GDPR if EU | Email + password, MFA optional | Cloud SaaS | Tens of thousands users |
| Enterprise | SOC2 + possible HIPAA/PCI | SSO/SAML required | Cloud or on-prem option | Hundreds of thousands, SLA |

The oracle then covers: functional requirements, UX flows, module boundaries, integrations, security model, compliance, test strategy, deployment, and prompt injection/output validation:

> "Does your application receive untrusted text that reaches an LLM prompt, or produce LLM output that reaches users or downstream systems? If yes, which entry points?"

If yes → generates concrete tasks in `tasks.json` for runtime input sanitisation (prompt injection guard) and output validation (PII/sensitive data leakage check). These are acceptance-criteria tasks, not checkbox notes.

### Oracle outputs
- `architecture.md` — living design document with RESOLVED/UNRESOLVED/DEFERRED items
- `CLAUDE.md` — project guide for every future Claude Code session
- `execution_plan.md` — milestone structure with full task definitions for Milestone 1; stubs for subsequent milestones
- `tasks.json` — full task definitions for Milestone 1 only; slim stubs (`{task_id, status}`) for later milestones

The oracle has full design context and is the right place to define milestone ordering and Milestone 1 scope. Future milestone tasks are intentionally left as stubs — the orchestrator fills them lazily when the prior milestone completes, against architecture that may have evolved.

---

## PTY shell design

Pure deterministic systems code. Zero LLM calls. stdlib-only (pty, subprocess, signal, time, re, pathlib, hashlib).

### Token counting

```
I/O intercepted from PTY stdout/stdin
  → tokenizer.count(text, provider)   # tiktoken cl100k_base
  → accumulated_tokens += count
  → if accumulated_tokens > threshold: trigger_handoff()
```

Trigger fires when either condition is met (whichever comes first):
- `accumulated_tokens > threshold_tokens` (default: 40,000 — empirical sweet spot before compounding accelerates)
- `accumulated_tokens > window_size * threshold_pct` (default: 30% — safety ceiling for large-window models)

Both values are user-configurable in `~/.agentflow/config.yaml`.

### Session type detection

PTY watches stdin for the first skill invocation after session start:
- Sees `/oracle` → `session_type = "oracle"`
- Sees `/orchestrate` → `session_type = "orchestrator"`
- No skill seen → `session_type = None` → handoff triggered but no auto-restart

### Handoff flow

```
PTY: accumulated_tokens > threshold
  → write "/handoff\n" to PTY stdin         (AI CLI sees it as user input)
  → scan PTY stdout for "HANDOFF_COMPLETE"  (printed by handoff skill)
  → write "/clear\n" to PTY stdin           (works on Claude Code and Gemini CLI)
  → start 5s countdown (configurable, Ctrl+C cancels)
  → write "/oracle\n" or "/orchestrate\n"   (same command that started the session)

New session:
  → skill reads living state document
  → resumes from UNRESOLVED items (oracle) or incomplete milestones (orchestrator)
  → user sees no gap
```

**Manual `/handoff`** (user-initiated before threshold): PTY detects that `/handoff` came from stdin (not injected by itself) → suppresses auto-restart → user retains full control.

**Pre-PTY operation (v1 manual mode)**: Until the PTY shell is built, the handoff skill itself signals the user when a handoff is recommended — printing `HANDOFF RECOMMENDED: <reason>` at natural stopping points (task complete, checklist batch resolved, context growing heavy). The user triggers `/handoff` manually. PTY automates this in the final v1 milestone.

### Countdown config (tier-based)
- Default: 5 seconds
- Free tier: fixed, not configurable
- Pro tier: `~/.agentflow/config.yaml` → `shell.restart_delay_seconds`
- Enterprise: admin policy overrides user config; `0` valid for CI/automation

---

## Symbol indexer

### Cache location

```
project file:  /myproject/agentflow/tools/git.py
index file:    ~/.agentflow/cache/<sha256-of-project-root>/index/agentflow/tools/git.py.idx
```

Index files are never in the project tree, never committed, never visible to users. Cache miss → regenerate on demand (deterministic from file contents).

### File types indexed

| Extension | Indexed by | Condition |
|---|---|---|
| `.py` | function/class names, signatures, line ranges | always |
| `.md` | H2/H3 section headers, line ranges | always |
| `.json` | top-level keys + line ranges | file > 30 lines |
| `.yaml` | top-level + second-level keys, line numbers | file > 30 lines |
| `.sh` | skipped | — |

Parsers: `ast` (Python), regex (Markdown, YAML), `json.loads` (JSON). No external deps.

### write_file hook

Workers call `write_file(path, contents)`. The tool:
1. Writes the file to disk
2. Calls `index_manager.update(path, contents)` silently
3. Returns success

Workers are unaware indexing exists. The `.idx` update is a side effect, always in sync at commit time.

### Ownership rule

A task that owns `agentflow/tools/git.py` implicitly owns its index file. No other task may write either. The validator enforces this pair as a unit.

### Brownfield scan

On first load of an existing project, `brownfield_scanner.py` walks the project tree, indexes all files meeting the size threshold, and populates the cache. No refactoring — index only. Workers on existing files then get targeted reads immediately.

---

## Context bundle (per worker, token-optimised)

```
task brief          (description + acceptance criteria)
owned file list     (what to create/modify)
read-only file contents  (dependencies — already included, do not re-read via tool)
contract stubs      (function signatures to implement against)
architecture section (architecture.md#<anchor> — relevant section only, not full doc)
test_strategy.md    (always included read-only)
security constraints
test scenarios
config snapshot     (model, coverage threshold, file size limits)
```

No-re-read rule (in worker system.md): "Do not use the Read tool on any file listed in your Dependencies section — its contents are already in this context. Re-reading wastes tokens."

Bundle size warning: if bundle exceeds 50k tokens, `context_builder` emits a telemetry warning. Indicates reads list may be too broad.

---

## Token savings model

Nine strategies, applied at different layers. Savings are modelled estimates — pending empirical validation via manual skill testing.

### 1. Handoff (context cycling)

**Mechanism:** LLM input cost compounds — each turn costs all prior context plus new tokens. At the threshold (40K tokens or 30% of window), `/handoff` flushes state to living documents, `/clear` resets context, resumed session starts from a compact state doc (~2–5K tokens) instead of full history.

**Model:** A 60-turn session with 500 new tokens/turn accumulates ~900K input tokens total (triangular sum). With one handoff at turn 40, the first session costs ~410K, the resumed session costs ~140K → **~40% reduction** in total input tokens. Savings increase with session length — the longer past the threshold, the steeper the compounding avoided.

**v1 status:** Manually testable today with `/handoff` skill. PTY automates the trigger.

---

### 2. No-re-read rule

**Mechanism:** Worker prompts include all dependency file contents upfront. The no-re-read rule ("Do not use the Read tool on any file in your Dependencies section") prevents workers from issuing redundant Read calls that would pull the same content into context a second time.

**Model:** If a worker has 5 dependency files averaging 300 tokens each, one re-read per file = 1.5K tokens wasted per worker session. Across 10 workers = 15K tokens. Small per-session, but eliminates a class of waste with zero implementation cost.

**v1 status:** Built into worker prompt (`testing_guide.md`, `system.md`). Testable once headless workers exist (v2). Rule is in the prompt files today.

---

### 3. Context bundle

**Mechanism:** Workers receive a pre-assembled minimal bundle instead of reading files ad-hoc during their session. Bundle contains only what the task needs: task brief, owned file list, relevant architecture section (anchor only, not full doc), dependency contents, test scenarios, security constraints.

**Model:** A worker reading files ad-hoc accumulates those reads in context for the entire session. A bundle fixes the cost at session start. Estimated savings: 20–30% vs ad-hoc reading, because the bundle omits everything outside task scope and prevents context growth from exploratory reads.

**v1 status:** v1. `context_builder.py` assembles the bundle programmatically. In v1 with skills (no headless runner), the orchestrate skill writes a `context_bundle.md` per task to disk; workers read only that file on session start.

---

### 4. Symbol index

**Mechanism:** Instead of reading entire files, workers request specific symbols (function, class, section header) via the index. The index returns only the relevant lines rather than the full file.

**Model:** If a worker needs 3 functions from a 250-line file, full-file read = 250 lines ≈ 1.25K tokens. Index lookup = ~30 lines × 3 = 90 lines ≈ 450 tokens. **~65% reduction per targeted read.** Multiplied across all reads in a worker session, this is the highest-leverage strategy at scale.

**v1 status:** v1. `indexer/` module ships in v1 as a standalone CLI tool. PTY shell runs it on session start. Skill prompts instruct Claude to read `.idx` files before full files — targeted reads without a headless runner.

---

### 5. Lazy decomposition

**Mechanism:** `tasks.json` only contains the current milestone's full task definitions plus slim stubs (`{task_id, status}`) for completed tasks. Future-milestone tasks are not written until the prior milestone merges. This keeps `tasks.json` small so it doesn't bloat the orchestrator's context on every load.

**Model:** A 50-task project across 5 milestones: eager decomposition loads all 50 task definitions (~15K tokens) every orchestrator turn. Lazy decomposition loads ~10 task definitions + 40 stubs (~3–4K tokens). **~75% reduction** in tasks.json context cost.

**v1 status:** Design principle today (already encoded in orchestrator startup logic). Validated with current tasks.json (completed tasks are slim stubs).

---

### 6. Compact state documents

**Mechanism:** State documents (`architecture.md`, `execution_plan.md`) are written in dense structured format — tables, bullets, no prose paragraphs. Every token in these docs gets re-read many times across sessions, so compactness has a multiplier effect. The `/handoff` skill enforces this format when flushing state.

**Model:** architecture.md at ~600 lines ≈ 4,500 tokens. Compact format targets 35–40% reduction → ~2,700 tokens. Savings per load: ~1,600 tokens. Over a 20-session project with 3 loads/session: **~96K tokens saved** across the project lifetime.

**v1 status:** v1. Enforced via handoff skill format spec. No code required — prompt instruction only.

---

### 7. Output verbosity control

**Mechanism:** Skill system prompts instruct Claude to keep responses concise. Fewer output tokens means slower context growth between handoffs — the threshold fires later, so each session does more work before a restart is needed.

**Model:** Average response drops from ~600 to ~250 tokens: 350 tokens saved per turn. In a 40-turn session: 14K direct output savings plus ~7K avoided carry-forward (compounding). Net: **~20% slower context growth**, extending sessions by ~25% before threshold fires.

**v1 status:** v1. One-line addition to each skill's system prompt. No code required.

---

### 8. Section-only loading

**Mechanism:** Skills and tasks only load the relevant anchor section of `architecture.md` (e.g. `architecture.md#pty-shell-design`), never the full document. Already partially enforced via `reads` anchors in tasks.json — made explicit and mandatory.

**Model:** Full doc load ≈ 4,500 tokens. Section load ≈ 400–600 tokens. Savings: ~4,000 tokens per load. With 10 worker sessions each loading it once: **~40K tokens saved**. Savings scale as architecture.md grows.

**v1 status:** v1. Enforced in task `reads` fields (already use anchors) and in skill system prompts. No code required.

---

### 10. Orchestrator round-sizing heuristic

**Mechanism:** Before scheduling each round, the orchestrator estimates how many tasks fit in its remaining token budget. Each task added to a round contributes ~2,500 tokens of orchestrator context (PR description + review output + status update). Exceeding the threshold mid-round forces a handoff that interrupts task tracking.

**Model:** `max_tasks_in_round = max(1, (orchestrator_threshold_tokens - current_estimated_tokens) / tokens_per_task_estimate)`. Current tokens estimated from accumulated `TOKENS:` reports of completed agents this session. If the round has more tasks than `max_tasks_in_round`, excess tasks deferred to a sub-round after the next state save.

**v1 status:** v1. Encoded in `commands/orchestrate.md` skill logic. Config adds `shell.tokens_per_task_estimate` (default 2500). No code required.

---

### 9. Per-session-type thresholds

**Mechanism:** Oracle and orchestrator sessions have different token burn rates. Oracle is conversational (~200–300 tokens/turn) and can run longer. Orchestrator is file-heavy (~1,000–2,000 tokens/turn) and should trigger handoff sooner. Separate `threshold_tokens` per session type prevents premature handoffs in oracle and late handoffs in orchestrator.

**Model:** Better threshold calibration yields ~10–15% improvement in session efficiency — fewer wasted restarts in oracle, fewer expensive compounding turns in orchestrator.

**v1 status:** v1. Config schema addition (`shell.oracle_threshold_tokens`, `shell.orchestrator_threshold_tokens`). Session manager reads per-type threshold on session type detection.

---

### Summary

| Strategy | Layer | Est. savings | v1 or v2 | Testable now? |
|---|---|---|---|---|
| Handoff | Session lifecycle | ~40% input tokens | v1 | Yes — manual `/handoff` |
| No-re-read rule | Worker prompt | ~1–15K tokens/session | v1 (prompt) / v2 (worker) | Partially |
| Context bundle | Worker context | ~20–30% per worker | v1 | Once context_builder built |
| Symbol index | File reads | ~65% per targeted read | v1 | Once indexer built |
| Lazy decomposition | Orchestrator context | ~75% of tasks.json cost | v1 | Yes — current tasks.json |
| Compact state docs | State documents | ~96K tokens/project | v1 | Yes — update handoff skill |
| Verbosity control | All sessions | ~20% slower growth | v1 | Yes — update skill prompts |
| Section-only loading | Architecture reads | ~40K tokens/project | v1 | Yes — enforce in tasks.json |
| Per-session thresholds | PTY shell | ~10–15% efficiency | v1 | Once session_manager built |
| Orchestrator round-sizing | Orchestrator skill | Prevents wasted handoff mid-round | v1 | Yes — in commands/orchestrate.md |

All savings figures are modelled, not measured. **Combined effect: with all strategies active, estimated 2× more work per session vs baseline** (same threshold gets through ~80 turns instead of ~40). Manual testing priority: handoff + verbosity + compact docs first (zero implementation cost, testable today).

---

## Task state machine

```
PENDING → SPAWNED → IMPLEMENTING → PR_OPEN → REVIEW_IN_PROGRESS
                                                    │
                              ┌─────────────────────┤
                              │                     │
                         REWORK_NEEDED         REVIEW_PASSED
                              │                     │
                      (worker reruns with    HUMAN_APPROVED  ← enforced gate
                       reviewer comments          │
                       as rework context)       MERGED
```

Failure policy: retry once on crash → rework on review failure → escalate to human after second rework failure. No third attempt.

CRITICAL security findings block `HUMAN_APPROVED` transition. Reviewer findings reference file and line; they never echo secret values.

---

## Security model

### AgentFlow itself
- No secrets in source or config files — env vars only (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
- Telemetry records token counts only — no prompt content, no API keys
- Ledger records token counts only
- Worker file writes sandboxed to `owns` list — write attempts outside the list raise `SandboxViolationError`
- `shell=True` banned in all subprocess calls — list args only, branch names validated before use
- PR diff content treated as untrusted user data in reviewer prompts — never as instructions
- Input sanitisation at oracle ingestion: pattern-match for instruction-override attempts in user descriptions
- `tasks.json` validated against Pydantic schema on load — tampered files rejected before any worker spawns

### Projects built with AgentFlow
The oracle asks: "Does your application receive untrusted input that reaches an LLM prompt, or produce LLM output that reaches users or downstream systems?"

If yes, the oracle probes: which entry points, what sensitivity level, what output risk (PII leakage, instruction following, hallucination propagation). This produces concrete tasks for:
- Runtime input sanitisation layer (prompt injection guard at identified entry points)
- Output validation layer (PII/sensitive data scan before output reaches user or downstream system)

---

## External integrations

| Service | Owner module | Credentials | Failure strategy | Compliance impact |
|---|---|---|---|---|
| GitHub REST API | tools/github.py | `GITHUB_TOKEN` env var | retry 3× with backoff, then surface error | None |
| Anthropic API | worker/agent_runner.py | `ANTHROPIC_API_KEY` env var | budget exhaustion → compress + restart (max 2); escalate on 3rd | None |
| Gemini API | worker/agent_runner.py | `GEMINI_API_KEY` env var | same as Anthropic | None |

---

## Config schema

```yaml
models:
  oracle: claude-opus-4-8
  worker: claude-sonnet-4-6
  reviewer_code: claude-sonnet-4-6
  reviewer_security: claude-opus-4-8

shell:
  threshold_tokens: 40000         # fallback when session type is unknown
  oracle_threshold_tokens: 60000  # oracle is conversational — slower burn, can run longer
  orchestrator_threshold_tokens: 30000  # orchestrator is file-heavy — faster burn, trigger earlier
  threshold_pct: 0.30             # percentage ceiling — safety net for large-window models (e.g. 1M Gemini)
  tokens_per_task_estimate: 2500  # used by orchestrator round-sizing heuristic
  restart_delay_seconds: 5        # countdown before auto-restart
  providers:
    claude:
      handoff_command: "/handoff"
      clear_command: "/clear"
    gemini:
      handoff_command: "/handoff"
      clear_command: "/clear"

testing:
  coverage_threshold: 85
  require_integration_tests: true
  mock_io: true

token_budget:
  per_worker: 50000
  reviewer: 20000

file_limits:
  implementation: 250
  tests: 350
  prompts: 150
  stubs: 100
  index_min_lines: 30             # files below this are not indexed

parallelism:
  max_concurrent_workers: 4
```

Resolution order: env vars → `.agentflow/config.yaml` (project) → `~/.agentflow/config.yaml` (user) → `defaults.yaml` (package).

---

## Telemetry schema

```json
{
  "trace_id": "<uuid>",
  "span": "<component.action>",
  "task_id": "<id or null>",
  "model": "<model-id>",
  "tokens_in": 0,
  "tokens_out": 0,
  "duration_ms": 0,
  "status": "<ok|error|rework|escalate>",
  "metadata": {}
}
```

Emitted as JSONL to `.agentflow/telemetry.jsonl`. No prompt content. No API keys. Token counts only.

---

## File size limits

| File type | Soft target | Hard ceiling |
|---|---|---|
| Implementation | 150 lines | 250 lines |
| Tests | 200 lines | 350 lines |
| Prompts (.md) | 80 lines | 150 lines |
| Interface stubs | 50 lines | 100 lines |
| Config / data | unconstrained | — |

Violation at CI gate → rework prompt with specific split instruction, not silent pass.

---

## Design decisions log

| Item | Status | Decision |
|---|---|---|
| Primary artifact | RESOLVED | Skills-first: .md files for Claude, SKILL.md + scripts for Gemini |
| PTY LLM usage | RESOLVED | Zero LLM calls in PTY shell — fully deterministic |
| Token counting | RESOLVED | Local tiktoken, ~95% accuracy, acceptable for threshold detection |
| Handoff threshold | RESOLVED | Hybrid: absolute 40K floor OR 30% of window ceiling — whichever fires first |
| Semantic handoff trigger | DEFERRED | Task completion (TASK_COMPLETE signal) as primary trigger; token threshold as safety net — v2 |
| Velocity-based trigger | DEFERRED | Track turn-over-turn input delta; trigger on accelerating growth (second derivative positive over 3-turn window) — v2 |
| Structured PTY signals | DEFERRED | Skills emit TASK_COMPLETE:<id> and CHECKLIST_ITEM_RESOLVED:<id> to stdout for PTY consumption — prerequisite for semantic trigger — v2 |
| Handoff state | RESOLVED | Living documents (architecture.md, execution_plan.md) — no separate handoff files |
| Session resume | RESOLVED | Oracle: UNRESOLVED items in architecture.md. Orchestrator: incomplete milestones in execution_plan.md |
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
| v1 milestone order | RESOLVED | 1: skill files (oracle, orchestrate, handoff prompts + provider files) → 2: PTY shell (pty_wrapper, tokenizer, session_manager) → v2: headless automation layer |
| Headless automation layer | DEFERRED | v2 — see Module boundaries for full list. PTY approach validated in v1 first before building headless runners. |
| Symbol indexer | RESOLVED | v1 — standalone CLI tool; PTY shell runs on session start; skills instruct Claude to read .idx before full files. Highest-leverage read optimisation (~65% per targeted read). |
| Context builder | RESOLVED | v1 — context_builder.py assembles minimal bundle; orchestrate skill writes context_bundle.md per task to disk; workers read only that file on session start. |
| Compact state docs | RESOLVED | v1 — handoff skill writes architecture.md and execution_plan.md in dense structured format (tables/bullets, no prose). Prompt instruction only, no code. |
| Verbosity control | RESOLVED | v1 — all skill system prompts instruct Claude to keep responses concise. Extends sessions by ~25% before threshold fires. |
| Section-only loading | RESOLVED | v1 — task reads fields use anchors (already enforced); skill prompts explicitly forbid loading full architecture.md. |
| Per-session thresholds | RESOLVED | v1 — config adds oracle_threshold_tokens and orchestrator_threshold_tokens; session_manager reads per-type threshold on session detection. |
| Orchestrator persona | RESOLVED | Staff Engineering Lead — executes plan faithfully, manages parallelism and failure, escalates to human when authority exceeded. Does not re-prioritize. Oracle (Senior PE + PM + Designer) sets priority; orchestrator delivers it. |
| Skill IP protection | UNRESOLVED | `.md` skill files on disk are readable — not IP-protected. PTY binary protects shell mechanics only. Open: does PTY embed+inject skill content at runtime? Server-side delivery? Must resolve before commercial distribution. |
| Skill file location | RESOLVED | `commands/` directory at project root (git-tracked). Users copy to `~/.claude/commands/` (global) or `.claude/commands/` (project-scoped). No pip package distribution of skill content — IP protection mechanism deferred. |
| Gemini provider | DEFERRED | Claude Code skills (commands/*.md) built and validated first. Gemini provider added once Claude skills prove token savings hypothesis. |
| Orchestrator round-sizing | RESOLVED | Before each round: `max_tasks = max(1, (orchestrator_threshold_tokens - current_tokens) / tokens_per_task_estimate)`. Prevents context blowout mid-round. Config: `shell.tokens_per_task_estimate` default 2500. Encoded in commands/orchestrate.md skill logic. |
| Token savings validation | UNRESOLVED | Manual testing of oracle + orchestrate + handoff skills required to prove savings hypothesis before further build. Pass criteria: measurable reduction in accumulated tokens per session vs. no-handoff baseline. |
