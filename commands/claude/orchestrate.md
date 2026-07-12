# /orchestrate — Agent Orchestration + Implementation

**Verbosity:** ≤3 sentences (~150 tokens) per orchestrator status message.

## Startup

Execute the `commands/claude/orchestrator/startup.md` steps in order. Check design_status.md for UNRESOLVED items before proceeding (stop if count > 0). Load execution_plan.md, tasks.json, rate_calibration_claude.json. For details, see `commands/claude/orchestrator/startup.md`.


---

**See `commands/claude/orchestrator/decomposition.md` for decomposition details (lazy — stubs only).**

**Rate-pacing:** First agent spawn always alone. After each round, track observed_costs using TOKENS: reports. Per-task cost estimation: sample_count < 7 → 2500 tokens (static default); sample_count ≥ 7 and cv < cv_threshold → use mean; cv ≥ cv_threshold → use p85 (85th percentile). EWMA calibration: load ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha from rate_calibration_claude.json at startup. Round-sizing heuristic: `max_tasks_by_budget = floor(orchestrator_threshold_tokens / pct_cost)` ensures budget compliance; pause if effective_rate × remaining_minutes < 3 × pct_cost.

**Full protocol:** See `commands/claude/orchestrator/rate_pacing.md` for complete rate-pacing and EWMA calibration details.

---

## Agent spawn

**Pre-spawn (once before first agent):**
- Branch `main`, working tree clean — stop if not
- No GitHub remote → `gh repo create --source=. --remote=origin --push`
- Stub every `owns` path (`raise NotImplementedError`)
- `.gitignore` absent → generate for project tech stack
- Generate `.idx` for each `reads` file ≥50 lines (skip if `.idx` newer than source). For Python files, use `ast` to parse classes, functions, and methods. For Markdown files, grep for H2/H3 headers.


**Build each agent prompt:**
1. `commands/claude/worker/system.md`
2. `commands/claude/worker/context_bundle.md`
3. `commands/claude/worker/testing_guide.md`
4. Full task definitions for this group — for each task_id, grep `^## Addendum: <task_id>` in `~/.agentflow/cache/<HASH>/index/execution_plan.md.idx` → `name:start-end` → `Read(execution_plan.md, offset=start, limit=end-start+1)`. If idx absent, grep `^## Addendum: <task_id>` in execution_plan.md directly and read that section.
5. Milestone architecture anchor section
6. For each `reads` file:

   **Anchor-qualified** (`file.md#section`): load named section only.

   **Plain files:**
   ```
   idx_path = ~/.agentflow/cache/<HASH>/index/<file>.idx
   ```
   - `.idx` exists → for each `name:start-end`: embed `### <file> — <name> (lines start–end)` via `Read(offset=start, limit=end-start+1)`; don't embed full file
   - `.idx` absent → embed full file

Close every prompt: `"End your final message with TOKENS: input=N output=N — nothing after that line."`

**Model selection per task (before spawn):**
- Mechanical (estimated_lines ≤ 80 OR title/description contains: test, fix, rename, stub, move, format, lint, config): `model: "claude-haiku-4-5-20251001"`
- Default (exploratory, architecture, new module, algorithm): `model: "claude-sonnet-4-6"`

**Per-round scheduling:** Per task, run `python3 -c "from agentflow.shadow.task_estimator import estimate; print(estimate(<estimated_lines>, <file_count>))"` (fallback 2500 if absent). Cap: `floor(threshold/pct_cost)`. Disjoint owns: if tasks share an `owns` path — OWNS CONFLICT, move overlap to next sub-round.

Spawn one agent per group, `isolation: "worktree"`, with the selected `model`. Parallel only if no cross-dependencies and rate supports. Save `.agentflow/state.json` after each.

### Round Lifecycle & PTY Signals
At the start of each round, write `.agentflow/current_round.json` with the following schema:
```json
{
  "round_id": "string",
  "task_ids": ["string"],
  "estimated_lines_per_task": {"task_id": "int"},
  "file_counts_per_task": {"task_id": "int"},
  "timestamp": "ISO8601"
}
```

During the round execution, orchestrate the worker lifecycles with deterministic stdout print signals:
- Before spawning each worker: run `python agentflow/shell/pty_signal.py task_start <task_id>` and print `AGENTFLOW_TASK_START:<task_id>`
- After each worker completes: print `AGENTFLOW_TASK_COMPLETE:<task_id>` and run `python agentflow/shell/pty_signal.py task_done <task_id>`
- After all round tasks complete: print `AGENTFLOW_ROUND_COMPLETE`


---


## Review

**Pass 1 — Programmatic:**
```bash
git diff main...<branch> --name-only > /tmp/rf.txt && git diff main...<branch> > /tmp/rd.txt
grep -n "NotImplementedError" $(cat /tmp/rf.txt) | grep -v "stub\|test"
grep -n "shell=True" $(cat /tmp/rf.txt)
grep -n "except:" $(cat /tmp/rf.txt)
wc -l $(cat /tmp/rf.txt) | awk '$1 > 250 {print}'
grep -nE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}" $(cat /tmp/rf.txt)
```
CRITICAL: hardcoded secrets, signal injection. WARNING: bare except, size > 250 lines.

**Pass 2 — LLM Reviewer (cross-tier model routing):**
Select the reviewer model based on the model used by the implementing agent to implement the task (opposite tier routing):
- Haiku-implemented tasks (`claude-haiku-4-5-20251001`) → Route to Sonnet reviewer (`claude-sonnet-4-6`)
- Sonnet-implemented tasks (`claude-sonnet-4-6`) → Route to Haiku reviewer (`claude-haiku-4-5-20251001`)
*Rationale:* Cross-tier review catches blind spots cheaply, while the subsequent human gate backstops cases where a Haiku reviewer misses subtle issues in Sonnet output.

Embed `commands/claude/reviewer/code_review.md`, `commands/claude/reviewer/security_review.md`, `commands/claude/reviewer/test_review.md`. Include pre-filter findings, changed files, diff (max 300 lines).

- `CRITICAL` → rework (one retry; escalate on second failure)
- `DRIFT` → surface at human gate; update `architecture.md` before merging if approved

---

## Human gate

```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
  Description: <brief description of changes>
git diff main...<branch>
Worktree: <absolute path>
PR: <URL> (always push branch to remote and show PR URL, or PR creation link)
Reply: yes → merge | no [reason] → rework | skip → continue
```
- **PR creation fallback:** Always push the task branch. If `gh pr create` encounters a sandbox permission failure, the agent must fallback to generating and providing the direct PR creation URL (e.g. `https://github.com/<owner>/<repo>/pull/new/<branch>`) instead of skipping.

Once the user replies "yes" (human gate passed), print `AGENTFLOW_ROUND_COMPLETE` to stdout.

Emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`

**Never merge without explicit "yes".**

---

## Merge

**REQUIRED — do not skip, do not substitute with manual edits:**
```bash
python agentflow/tools/cleanup_tasks.py .
```
This is the ONLY permitted way to update tasks.json at merge time. Never set `status: complete` manually or edit task entries by hand — the cleanup script owns the trim + archive atomically.

Then:
1. (**Already handled by cleanup**) tasks.json: each completed task trimmed to `{"task_id": "T-NNN", "status": "complete"}`; full definition archived to `.agentflow/tasks.archive.json` (flat list — no nested batches).
2. Mark `MERGED` in `execution_plan.md`
3. Milestone complete → mark `COMPLETE`, decompose next milestone lazily
4. Save `.agentflow/state.json`
5. Emit: `HANDOFF RECOMMENDED: [task_id] merged — state saved, good stopping point before next round`

**Do not manually edit task stubs or archive — always run the cleanup script.**

---

**See `commands/claude/orchestrator/targeted_reads.md` for targeted reads pattern.**

**See `commands/claude/orchestrator/verbosity.md` for status messaging guidelines.**

**See `commands/claude/orchestrator/telemetry.md` for session telemetry logging.**
