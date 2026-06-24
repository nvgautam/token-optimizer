# AgentFlow — Architecture

A pip-installable package for AI-driven project management. Given a project description,
it spars with the user to produce an architecture, decomposes work into token-optimized
tasks, spawns headless agents per task, and manages the full lifecycle through to merged PRs.

---

## Guiding principles

- **Token-first**: every design decision minimises token consumption. Workers get minimal
  context bundles; files stay small; sessions are scoped to one task.
- **Separation of concerns**: prompts, tools, and MCPs are independently versioned artifacts,
  not entangled with orchestration logic.
- **Config-driven extensibility**: behaviour is controlled by layered config, not code changes.
- **Observability by default**: every span emits structured JSON logs in an OTel-compatible schema.
- **Greenfield v1**: single-repo, git worktrees per task. Brownfield is out of scope.

---

## System components

```
┌─────────────────────────────────────────────────────┐
│                     CLI (agentflow)                  │
│  init │ oracle │ orchestrate start/status │ report   │
└───────────────────┬─────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │     Design Oracle      │  ← spars with user, Option B exit
        │  conversation loop     │    outputs architecture.md +
        │  checklist evaluator   │    tasks.json + contract stubs
        │  artifact generator    │
        └───────────┬───────────┘
                    │  tasks.json
        ┌───────────▼───────────┐
        │      Orchestrator      │  ← project manager
        │  DAG scheduler         │    owns full task lifecycle
        │  state machine         │    PENDING→...→MERGED
        │  progress dashboard    │
        │  merge sequencer       │
        └──┬──────────┬─────────┘
           │          │
   ┌───────▼──┐  ┌────▼──────────────────────────┐
   │ Contract  │  │         Worker Pool             │
   │ Generator │  │  context builder + API runner   │
   │ stubs +   │  │  TDD loop: red→green→PR         │
   │ test skel │  │  one headless agent per task     │
   └───────────┘  └────────────┬───────────────────┘
                               │  PR opened
                  ┌────────────▼───────────────────┐
                  │       Reviewer Pipeline          │
                  │  code reviewer   (conformance)   │
                  │  security reviewer (OWASP/compliance) │
                  └────────────┬───────────────────┘
                               │  comments posted
                          Human approval
                               │
                          Merge (DAG order)
```

---

## Package structure

```
agentflow/                        # installable package root
  cli.py                          # entry points, arg parsing
  oracle/
    conversation.py               # sparring loop, message history
    checklist.py                  # NFR checklist, confidence scoring
    artifact_generator.py         # outputs architecture.md + tasks.json
    contract_generator.py         # stub files, test skeletons, IO mocks
  orchestrator/
    project_manager.py            # state machine, lifecycle coordination
    dag.py                        # dependency graph, topological sort
    state.py                      # persistent state r/w (.agentflow/state.json)
    merge_sequencer.py            # post-approval ordered merge
  worker/
    context_builder.py            # assembles minimal context bundle per task
    agent_runner.py               # Anthropic API headless agent, TDD loop
  reviewer/
    code_reviewer.py              # architecture conformance, contract adherence
    security_reviewer.py          # OWASP, secrets, compliance constraints
  tools/
    git.py                        # worktree create/delete, branch, commit
    github.py                     # PR create, inline comments, status checks
    test_runner.py                # run tests in worktree, return coverage result
    file_validator.py             # enforce file size limits, fail with rework msg
  telemetry/
    logger.py                     # structured JSON logger, trace IDs
    metrics.py                    # OTel-compatible span/metric emission
    token_tracker.py              # per-span token attribution, ledger integration
  config/
    loader.py                     # layered resolution: env → project → user → defaults
    schema.py                     # pydantic schema + validation
    defaults.yaml                 # shipped defaults
  prompts/
    oracle/v1/
      system.md                   # senior PE persona
      checklist.md                # NFR question bank
      generation.md               # artifact output format
    worker/v1/
      system.md                   # implementer persona
      context_bundle.md           # how to interpret the bundle
    reviewer/v1/
      code_review.md
      security_review.md
  mcps/
    github.yaml                   # MCP config, pinned version
    filesystem.yaml
pyproject.toml
```

---

## Project runtime layout

After each CLI command, `.agentflow/` grows in a defined way:

```
# after: agentflow init
.agentflow/
  config.yaml                  # user-editable project config

# after: agentflow oracle (oracle done sparring)
architecture.md                # at project root — the design document
tasks.json                     # at project root — the executable plan
.agentflow/
  config.yaml
  design_session.md            # oracle conversation summary: decisions + rationale
  state.json                   # all tasks initialised as PENDING

# after: agentflow orchestrate start (context bundles pre-generated)
.agentflow/
  config.yaml
  architecture.md              # (symlink or copy — worker reads locally)
  design_session.md
  state.json                   # tasks transitioning through state machine
  ledger.json                  # token records per task session
  telemetry.jsonl              # OTel-compatible span records
  context/
    T-001.md                   # pre-generated context bundle — worker opening prompt
    T-002.md
    ...

# worktrees per task (outside .agentflow/)
workspaces/
  T-001/                       # git worktree on branch task/T-001
  T-002/                       # git worktree on branch task/T-002
```

Package-level files (generic, versioned, ship with pip install):
```
agentflow/prompts/
  oracle/v1/system.md            # senior PE persona
  oracle/v1/checklist.md         # NFR question bank (functional + non-functional)
  oracle/v1/generation.md        # artifact output format (architecture.md + tasks.json)
  worker/v1/system.md            # implementer persona
  worker/v1/context_bundle.md    # how to interpret the context bundle file
  worker/v1/testing_guide.md     # TDD approach: red→green, behavior not implementation,
                                 # IO mocks are pre-generated, read test scenarios from bundle,
                                 # skeleton bodies start as NotImplementedError
  reviewer/v1/code_review.md     # conformance + contract adherence criteria
  reviewer/v1/security_review.md # OWASP Top 10, secrets, compliance constraint checks
  reviewer/v1/test_review.md     # how to review tests: scenario coverage, mock appropriateness,
                                 # no implementation-coupled assertions, coverage threshold met
```

These are the same for every project. Upgrading the oracle persona or test philosophy
is a prompt file edit, not a code release.

Project-level generated files (oracle writes these, project-specific):
```
architecture.md                  # system design — at project root
tasks.json                       # executable task plan — at project root
.agentflow/
  config.yaml                    # user-editable project config
  design_session.md              # oracle conversation summary: decisions + rationale
  test_strategy.md               # project-specific test decisions: coverage thresholds,
                                 # integration scope, what is mocked and why,
                                 # compliance-driven test scenarios
  state.json                     # task states (runtime)
  ledger.json                    # token records per task session
  telemetry.jsonl                # OTel-compatible span records
  context/
    T-001.md                     # pre-generated context bundle — worker opening prompt
    T-002.md
    ...
```

`test_strategy.md` is included in every worker's context bundle (read-only) so workers
do not infer the project's test philosophy. Reviewers also read it to judge whether
tests match the strategy, not only whether they pass.

---

## What each agent reads to start

| Agent | Reads | Writes |
|---|---|---|
| Oracle | `prompts/oracle/v1/system.md`, `checklist.md`, `generation.md` | `architecture.md`, `tasks.json`, `.agentflow/design_session.md`, `.agentflow/test_strategy.md`, `.agentflow/state.json` |
| Orchestrator | `tasks.json`, `.agentflow/state.json`, `.agentflow/config.yaml` | `.agentflow/state.json` (transitions) |
| Context builder | `tasks.json`, `architecture.md`, `.agentflow/test_strategy.md`, contract stubs | `.agentflow/context/<task-id>.md` |
| Worker | `.agentflow/context/<task-id>.md` as opening message — nothing else | files in `workspaces/<task-id>/` |
| Code reviewer | PR diff, contract stubs, `architecture.md#<anchor>`, `prompts/reviewer/v1/code_review.md` | inline PR comments |
| Security reviewer | PR diff, `.agentflow/test_strategy.md`, `prompts/reviewer/v1/security_review.md` | inline PR comments |
| Test reviewer | PR diff test files, `.agentflow/test_strategy.md`, `prompts/reviewer/v1/test_review.md` | inline PR comments |

The worker's entire instruction set is one file. Context stays minimal.

---

## Session handoff and ledger

**Handoff in orchestrated mode (automatic):**
The orchestrator calls `token_tracker.close_session(task_id)` when a worker returns
a `WorkerResult`. No manual step. Token spans are emitted throughout the worker's API
loop; `close_session` finalises the record and writes to `.agentflow/ledger.json`.

**Handoff in manual mode (CLI):**
`agentflow handoff` remains available for users running Claude manually outside the
orchestrator — same as the original `agentflow.py` workflow.

**Ledger locations:**
- `.agentflow/ledger.json` — project-level detail, one record per task session
- `~/.agentflow/projects.json` — global registry of project paths (pointers only)
- `agentflow report --all` aggregates across registry entries

**Ledger record schema:**
```json
{
  "task_id": "T-001",
  "project": "payments-service",
  "model": "claude-sonnet-4-6",
  "started_at": "2026-06-23T10:00:00Z",
  "ended_at": "2026-06-23T10:22:00Z",
  "tokens_in": 18400,
  "tokens_out": 6200,
  "restarts": 0,
  "status": "pr_opened",
  "shadow_tokens_in": 41200
}
```

**Shadow calculation (multi-agent context):**
- **Real**: sum of `tokens_in + tokens_out` across all worker sessions
- **Shadow**: what a single agent would have consumed doing all tasks sequentially.
  Each task's shadow input = its real input + accumulated output of all prior tasks
  (prior context bleeds forward in a single session). Shadow always exceeds real.
- Ratio shadow/real is the package's headline metric.

---

## Task schema (tasks.json)

```json
{
  "project": "<name>",
  "repo": "<path>",
  "tasks": [
    {
      "task_id": "<id>",
      "title": "<short title>",
      "description": "<what to build and why>",
      "owns": ["<files worker may write>"],
      "reads": ["<files worker may read only>"],
      "depends_on": ["<task_ids that must reach MERGED first>"],
      "contracts": ["<stub files already committed>"],
      "test_requirements": {
        "unit": ["<scenario descriptions>"],
        "integration": ["<scenario descriptions>"],
        "coverage_threshold": 85
      },
      "security_constraints": ["<constraint strings>"],
      "acceptance_criteria": "<single sentence gate>",
      "estimated_lines": 180,
      "context_section": "architecture.md#<anchor>"
    }
  ]
}
```

Validation rule: no two tasks may share an `owns` entry. Orchestrator rejects tasks.json
that violates this before spawning anything.

---

## Task state machine

```
PENDING → SPAWNED → IMPLEMENTING → PR_OPEN → REVIEW_IN_PROGRESS
                                                  │
                            ┌─────────────────────┤
                            │                     │
                       REWORK_NEEDED         REVIEW_PASSED
                            │                     │
                    (worker reruns with      HUMAN_APPROVED
                     reviewer comments            │
                     as rework context)       MERGED
```

Failure policy: retry once on worker crash → rework on review failure → escalate to human
after second rework failure (no third attempt; burns tokens).

---

## Context bundle (per worker, token-optimised)

```
task brief          (description + acceptance criteria)
owned file list     (what to create/modify)
read-only files     (interfaces the task depends on)
contract stubs      (already committed — implement against these)
relevant arch section (architecture.md#<anchor>, not the full doc)
security constraints
test scenarios      (from task schema)
config snapshot     (model, coverage threshold, file size limits)
```

Everything else is excluded. Workers do not receive the full architecture doc,
other tasks' context, or session history from the oracle.

---

## File size limits (enforced at oracle design time + CI gate)

| File type       | Soft target | Hard ceiling |
|-----------------|-------------|--------------|
| Implementation  | 150 lines   | 250 lines    |
| Tests           | 200 lines   | 350 lines    |
| Prompts (.md)   | 80 lines    | 150 lines    |
| Interface stubs | 50 lines    | 100 lines    |
| Config / data   | unconstrained | —          |

Violation at CI gate → rework prompt with specific split instruction, not silent pass.

---

## Config schema (excerpt)

```yaml
models:
  oracle: claude-opus-4-8
  worker: claude-sonnet-4-6
  reviewer_code: claude-sonnet-4-6
  reviewer_security: claude-opus-4-8

prompts:
  oracle: v1
  worker: v1
  reviewer: v1

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

mcps:
  - github
  - filesystem
```

Resolution order: env vars → `.agentflow/config.yaml` (project) →
`~/.agentflow/config.yaml` (user) → `defaults.yaml` (package).

---

## Telemetry schema (every span)

```json
{
  "trace_id": "<uuid>",
  "span": "<component.action>",
  "task_id": "<id or null>",
  "model": "<model-id>",
  "tokens_in": 0,
  "tokens_out": 0,
  "duration_ms": 0,
  "status": "<ok|error|rework>",
  "metadata": {}
}
```

Stage 1: emitted as newline-delimited JSON to `.agentflow/telemetry.jsonl`.
Stage 2 (later): OTel SDK exporter layer added without schema change.

---

## Oracle checklist (Option B exit trigger)

Oracle proposes generation when all items resolve:

```
Functional
  [ ] Project name and one-line purpose
  [ ] Tech stack (language, framework, persistence)
  [ ] Core module boundaries identified
  [ ] Shared interfaces agreed (what crosses boundaries)

Non-functional
  [ ] Scale requirements (load, data volume)
  [ ] Performance constraints (latency SLOs)
  [ ] Security model (auth mechanism, data sensitivity)
  [ ] Compliance requirements (GDPR / HIPAA / SOC2 / none)
  [ ] Test strategy (coverage floor, integration scope)
  [ ] Deployment target

Quality
  [ ] No file would exceed size ceiling at current decomposition
  [ ] No two tasks share owned files
  [ ] All cross-task interfaces have a stub owner
```

---

## CLI surface

```bash
agentflow init                    # scaffold .agentflow/ in current project
agentflow oracle                  # start design sparring session
agentflow orchestrate start       # read tasks.json, begin lifecycle
agentflow orchestrate status      # live progress dashboard
agentflow orchestrate merge       # trigger post-approval merge sequence
agentflow report                  # token usage report (ledger integration)
agentflow validate tasks.json     # dry-run: check schema + ownership conflicts
```
