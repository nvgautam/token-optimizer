# AgentFlow — Architecture

Provider-agnostic multi-agent project management delivered as skills + PTY overlay shell. Given a project description, the oracle spars with the user to produce a living architecture document, the orchestrator decomposes it into milestones and tasks, headless workers implement each task in an isolated worktree, and the PTY shell manages context lifecycle transparently across all sessions.

---

## Guiding principles

- **Skills-first**: the primary artifacts are skill files (`.md` for Claude, `SKILL.md` + scripts for Gemini). Python modules are the runtime backing those skills.
- **Token-first**: context is cycled at task boundaries; workers receive minimal context bundles; symbol index enables targeted file reads instead of full-file reads.
- **Living documents**: `architecture.md`, `execution_plan.md`, and `tasks.json` are continuously updated state — not written once and forgotten.
- **Prove before automating**: token savings are delivered by the skills + state documents. PTY shell automates the handoff trigger and protects IP — built last, after savings are empirically validated with manual handoffs.
- **Idempotency**: every operation is safe to run twice. Starting oracle or orchestrator on an existing project resumes from current state.
- **IP by obscurity of mechanism**: symbol index files live outside the project tree; the PTY shell ships as a compiled binary.

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
agentflow/
  cli.py                          # entry points, arg dispatch
  shell/
    pty_wrapper.py                # PTY process lifecycle, I/O interception
    tokenizer.py                  # local token counting per provider (tiktoken)
    session_manager.py            # threshold watch, session type, restart coordination
    countdown.py                  # configurable countdown with SIGINT handler
  skills/
    providers/
      claude/
        oracle.md                 # Claude Code oracle skill
        orchestrate.md            # Claude Code orchestrate skill
        handoff.md                # Claude Code handoff skill
      gemini/
        oracle/SKILL.md + scripts/
        orchestrate/SKILL.md + scripts/
        handoff/SKILL.md + scripts/
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
| Claude Code | `.md` in `~/.claude/commands/` | `/handoff` (existing skill) | `tiktoken` cl100k_base |
| Gemini CLI | `SKILL.md` in `.agents/skills/` | `/handoff` (custom skill) | `tiktoken` cl100k_base (approx) |
| Codex | — | — | v2 |

Token counting uses `tiktoken` for all providers. ~95% accuracy is sufficient for a 40% threshold trigger.

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

### execution_plan.md (orchestrator's living state)

```markdown
## Milestone 1: Foundation
Status: COMPLETE
Architecture: architecture.md#module-boundaries
Tasks: T-001 (MERGED), T-002 (MERGED), T-003 (MERGED)

## Milestone 2: Core Tools
Status: IN_PROGRESS
Architecture: architecture.md#tools
Tasks: T-004 (MERGED), T-005 (IN_PROGRESS), T-006 (PENDING)
Blocked: T-006 depends on T-005

## Milestone 3: Orchestration Layer
Status: PENDING — not yet decomposed
Architecture: architecture.md#orchestrator-design

## Deferred
- Codex provider: v2
- Brownfield file refactoring: v2
- Tier/licensing: TBD
```

Milestones are decomposed **lazily** — Milestone 3 tasks are only written to `tasks.json` when Milestone 2 completes. This keeps `tasks.json` lean and avoids over-planning against architecture that may still evolve.

Orchestrator startup:
1. Read `execution_plan.md` — any milestones not `COMPLETE`? → resume from the first incomplete milestone
2. Read `tasks.json` — pick up in-flight tasks, spawn pending ones
3. Neither exists? → decompose `architecture.md` into Milestone 1, write both files
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

The oracle generates `tasks.json` as part of sparring completion — all tasks decomposed upfront. The orchestrator reads this and may extend it via lazy milestone decomposition as the project evolves.

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
  threshold_tokens: 40000         # absolute floor — empirical sweet spot before compounding accelerates
  threshold_pct: 0.30             # percentage ceiling — safety net for large-window models (e.g. 1M Gemini)
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
| tasks.json owner | RESOLVED | Oracle generates tasks.json upfront at sparring completion; orchestrator reads and extends via lazy milestone decomposition |
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
| PTY sequencing | RESOLVED | PTY is v1 but built last — after token savings are empirically validated via manual handoffs. Skills emit HANDOFF RECOMMENDED signal; user triggers /handoff manually until PTY is ready. |
| v1 milestone order | RESOLVED | 1: foundation + skills + handoff (prove savings) → 2: symbol index → 3: worker pipeline → 4: reviewer pipeline → 5: PTY shell (automate + IP) |
| Orchestrator persona | RESOLVED | Staff Engineering Lead — executes plan faithfully, manages parallelism and failure, escalates to human when authority exceeded. Does not re-prioritize. Oracle (Senior PE + PM + Designer) sets priority; orchestrator delivers it. |
