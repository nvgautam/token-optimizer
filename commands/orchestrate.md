# /orchestrate — Agent Orchestration + Implementation

Read the design from disk, group tasks, spawn implementation agents, run reviews, and merge.

Requires `CLAUDE.md`, `architecture.md`, and `tasks.json` in the project root.

---

## Startup

Read `tasks.json`, `architecture.md`, and `CLAUDE.md` from disk. Do not rely on any prior conversation history — everything needed is in these files.

Check for `.agentflow/state.json`. If it exists, this is a resumed session:

```
Resuming orchestration. Current state:
  Complete:    [task_ids]
  In progress: [task_ids] (PRs open — check GitHub Desktop)
  Pending:     [task_ids]

Continue from where we left off? yes/no
```

If no state file, this is a fresh run. Report:

```
Ready to orchestrate.
  Tasks:   N pending across M modules
  Groups:  [will calculate after grouping]

Starting now.
```

---

## Step 1 — Group tasks by shared context

Group tasks that share high `reads` overlap AND are adjacent in the DAG. One group = one agent spawn.

Algorithm:
1. Topological sort all tasks by `depends_on`
2. Score overlap between adjacent tasks: `len(set(task_a.reads) & set(task_b.reads))`
3. Merge high-overlap adjacent pairs into groups (score ≥ 2 shared files)
4. Cap each group at 4 tasks — do not span a dependency edge to an external task

If invoked as `/orchestrate debug`, report the grouping plan before proceeding:

```
Task groups:
  Group 1: T-001, T-002  (3 shared reads — auth + config)
  Group 2: T-003         (no overlap with Group 1)
  Group 3: T-004, T-005  (4 shared reads — db models + schema)
  ...

Proceed? yes/no
```

Otherwise proceed silently without revealing groups, overlap scores, or grouping rationale.

---

## Step 2 — Create stub files and workspace scaffolding

Before spawning any agent:

**Branch check:** Verify the current branch is `main`:
```bash
git branch --show-current
```
If not on `main`, stop and tell the user:
> "Orchestration must start from `main`. Currently on `[branch]`. Switch to `main` and re-run `/orchestrate`."

If on `main`, verify it is clean (no uncommitted changes):
```bash
git status --short
```
If dirty, stop and tell the user:
> "Uncommitted changes on `main`. Commit or stash them before running `/orchestrate`."

**GitHub remote:** Check whether a remote repo exists:
```bash
git remote get-url origin
```
If this fails (no remote configured):
1. Check if `gh` is installed: `which gh`
2. If yes: `gh repo create --source=. --remote=origin --push` — this creates the repo on GitHub, wires the remote, and pushes the current branch in one step.
3. If no: warn the user — "No remote repo found and `gh` CLI is not installed. Run `brew install gh && gh auth login`, then re-run `/orchestrate`." — and stop.

**Stub files:** Write a stub file for every path in every task's `owns` list. Each stub contains the module interface with `raise NotImplementedError`. This lets agents import dependencies even when the owning task is not yet complete.

**`.gitignore`:** If a `.gitignore` does not already exist in the project root, create one with the following content. Do not overwrite an existing file.

```
# Python
__pycache__/
*.py[cod]
*.egg-info/

# Virtual environment
.venv/
venv/
env/

# Testing / coverage
.pytest_cache/
.coverage
htmlcov/
.tox/

# Build artefacts
dist/
build/
*.so

# OS
.DS_Store
```

---

## Step 3 — Spawn implementation agents

Spawn one agent per group using the Agent tool with `isolation: "worktree"`. Give each agent this prompt:

```
You are implementing the following tasks. Work through them in order.

## Setup (run once before implementing anything)

1. If `.venv` does not exist, create it: `python -m venv .venv`
2. Install project dependencies (skip if already installed):
   - If `pyproject.toml` or `setup.py` exists: `.venv/bin/pip install -e .[dev]`
     (fall back to `.venv/bin/pip install -e .` if the `[dev]` extra is absent)
   - Else if `requirements.txt` exists: `.venv/bin/pip install -r requirements.txt`
3. Run all subsequent commands (tests, linters) using `.venv/bin/python` and `.venv/bin/pytest`.

## Your tasks
[paste full task definitions for this group]

## Architecture context
[paste the relevant Module Boundaries section from architecture.md]

## Files you own
[list owns paths]

## Dependencies to read first
[paste contents of reads files]

## Test requirements
[list test_scenarios for each task]

## What to implement per task
For each task, write two things:
1. The implementation file(s) listed in owns
2. A test file at tests/test_[module_name].py covering:
   - Unit tests: one per function/method
   - Contract test: verify your implementation satisfies the stub interface
   - Integration tests: for any cross-module interactions (if agreed in test strategy)
   - Security tests: for any scenario involving auth, user input, or data storage

## Rules
- Implement only files in your owns list — do not touch anything else
- Commit both implementation and test files together on your branch
- Run tests after implementing each file
- If tests fail, fix and retry once — if still failing, stop and report: ESCALATE: [reason]
- When all tasks pass tests, open one PR for this group
- End your final message with:
  TOKENS: input=N output=N files_read=[list] files_written=[list]
```

Run groups with no cross-dependencies in parallel. Run dependent groups after their dependencies merge.

---

## Step 4 — Save state after each agent completes

After each agent finishes, write `.agentflow/state.json`:

```json
{
  "updated": "ISO8601",
  "groups": [
    {"group_id": 1, "task_ids": ["T-001","T-002"], "status": "complete", "pr": 4, "tokens": 18000},
    {"group_id": 2, "task_ids": ["T-003"], "status": "in_progress", "pr": null, "tokens": null},
    {"group_id": 3, "task_ids": ["T-004","T-005"], "status": "pending", "pr": null, "tokens": null}
  ]
}
```

This allows `/orchestrate` to be resumed in a new session if this session runs long.

---

## Step 5 — Automated review gates

Two passes: a free programmatic pre-filter, then a focused LLM review only on what bash cannot judge.

### Pass 1 — Programmatic pre-filter (bash, no LLM)

Run these checks directly. Collect all failures before proceeding.

```bash
# Get the diff
git diff main...<branch> --name-only > /tmp/review_files.txt
git diff main...<branch> > /tmp/review_diff.txt

# Code checks
grep -n "NotImplementedError" $(cat /tmp/review_files.txt) | grep -v "stub\|test"  # fail if any hit
grep -n "shell=True" $(cat /tmp/review_files.txt)                                   # fail if any hit
grep -n "except:" $(cat /tmp/review_files.txt)                                      # fail if any hit
wc -l $(cat /tmp/review_files.txt) | awk '$1 > 250 {print}'                        # fail if any file > 250 lines

# Security checks
grep -nE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}" $(cat /tmp/review_files.txt)  # hardcoded secrets
grep -nE "os\.environ\[|os\.getenv" $(cat /tmp/review_files.txt)                               # env var access in agent stdout paths

# Agentic checks
# Scope creep: every file written must be in the task's owns list
# (compare review_files.txt against owns paths from tasks.json — flag any path not in owns)
grep -nE "\[TASK_COMPLETE|TASK_FAILED\]" $(cat /tmp/review_files.txt) | grep -v "emit\|print\|sentinel"  # signal injection

# Drift checks
grep -nE "^import |^from " /tmp/review_diff.txt | grep -v "# "   # new imports to check against architecture.md
```

If any programmatic check fails, record it as `CRITICAL` or `WARNING` (hardcoded secrets and signal injection = CRITICAL; bare except, file size = WARNING). Do not block on programmatic failures alone — collect them and pass the list to Pass 2.

### Pass 2 — LLM review (fresh haiku agent, judgment calls only)

Spawn a fresh agent (model: haiku). Pass only what it needs — do not include the full diff if it exceeds 300 lines; instead pass a summary of changed files and paste only the security-relevant sections.

```
You are a security and architecture reviewer. The programmatic pre-filter has already
checked for shell=True, bare except, file sizes, and hardcoded secrets. Do not repeat
those checks. Focus only on the judgment calls below.

## Pre-filter findings to incorporate
[paste any CRITICAL/WARNING findings from Pass 1, or "none"]

## Checks requiring judgment

### Security
- Injection vectors: SQL, shell, path traversal — look for string concatenation into queries or commands
- Auth enforcement: missing auth decorators, unguarded routes, conditional logic where null/missing value skips auth instead of rejecting
- Sensitive data in logs: PII or secrets passed to logging calls
- Timing attacks: secret comparisons not using constant-time equality (e.g. raw == on tokens or HMAC digests)
- Auth bypass via logic: `if token and validate(token)` patterns where absent token passes

### Agentic security
- Prompt injection: external data (API responses, file content, user input) interpolated directly into prompts without sanitization
- Data leakage: PII or secrets flowing into .ctx.md files, agent output, or logs
- Context poisoning: any code path writing to .ctx.md from external input rather than the compressor
- Credential leakage into transcript: stack traces or debug paths that could expose secrets in agent stdout
- Inter-agent trust: code that reads one worker's task file and writes status back to another worker's file
- Unbounded tool use: subprocess or HTTP calls not implied by the task's declared scope

### Architecture drift
- New module or directory absent from architecture.md Module Boundaries
- Cross-module import not listed in architecture.md Shared Interfaces
- New external service call absent from architecture.md External Integrations

## Inputs
<changed_files>
[list from /tmp/review_files.txt]
</changed_files>

<diff>
[paste /tmp/review_diff.txt — truncate to 300 lines if longer, keeping auth/security-relevant sections]
</diff>

<architecture>
[paste Module Boundaries and Shared Interfaces sections from architecture.md]
</architecture>

<tasks>
[paste task definitions for this group]
</tasks>

## Output format
  CRITICAL: [finding] — blocks merge, must fix
  WARNING:  [finding] — surface to user, judgment call
  DRIFT:    [finding] — architecture.md needs update if intentional
  CLEAN     (if no findings beyond pre-filter)
```

- `CLEAN` or only `WARNING`/`DRIFT` → proceed to human review gate
- `CRITICAL` → send back to implementation agent for one retry, then escalate to user if still failing
- `DRIFT` → surface at human gate, await decision; if user approves, update `architecture.md` before merging

---

## Step 6 — Human review gate

After automated reviews pass, pause and report:

```
PR #N ready for review — [task_ids] ([module name])
  ✓ Code review clean
  ✓ Security review clean  (if applicable)
  ⚠ Drift: [violations, if any]

To review the diff:
  git diff main...[branch-name]

To review in your editor, the worktree is at:
  [absolute path to worktree directory]

PR on GitHub:
  [PR URL]

Files changed:
  [implementation files]
  [test files]

Reply:
  yes          → merge this PR
  no [reason]  → I will send back to the agent with your feedback
  skip         → leave open, continue with other groups
```

Always provide the `git diff` command, worktree path, and PR URL — never just say "open GitHub Desktop." The user needs to know exactly where to look.

Wait for the user's reply. Do not merge without explicit "yes".

If "no" with feedback: re-open the agent in its worktree with the feedback, re-run reviews, return to this gate.
If drift was flagged and user replies "yes": update `architecture.md` and `CLAUDE.md` to reflect the intentional change before merging.

---

## Step 7 — Merge in topological order

Merge PRs dependencies-first after user approval. Update `tasks.json` status to `complete` and save state after each merge.

---

## Telemetry

Collect the `TOKENS:` report from each agent. After all tasks complete, write silently to `.agentflow/telemetry.jsonl`:

```json
{"event": "session_complete", "timestamp": "ISO8601", "real_tokens": N, "shadow_tokens": N, "ratio": N, "groups": N, "tasks": N}
```

Shadow tokens = modelled cost of running all tasks in one session (accumulated context growth per task). Do not surface this calculation to the user.

Run silently:
```bash
python /Users/gautam/code/token-optimizer/agentflow.py handoff "orchestrate: [project name]"
```

Then report to the user:

```
Orchestration complete.
  Tasks:  N completed across G groups
```
