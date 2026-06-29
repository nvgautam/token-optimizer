# Milestone Decomposition Guide

This file defines how the orchestrator lazily expands a new milestone's tasks into
`tasks.json` and rounds into `execution_plan.md`.

---

## When to Decompose

Decompose a milestone when:
- (a) Its prior milestone status is `COMPLETE` in `execution_plan.md`, AND
- (b) Its tasks in `tasks.json` are stub-only — each entry contains only
  `{task_id, status}` with no title, description, or owns list populated.

Do not decompose a milestone that is already `IN_PROGRESS` or `COMPLETE`.

---

## What to Read

Load only the architecture anchor section listed in `execution_plan.md` for that
milestone (e.g., `architecture.md#pty-shell-design`). Do NOT load the full
`architecture.md` — it exceeds context budget and contains sections irrelevant to
the milestone being decomposed.

Also load the existing task stubs from `tasks.json` to confirm task IDs.

---

## Task Definition Format

Expand each stub into the following schema in `tasks.json`:

```json
{
  "task_id": "T-NNN",
  "title": "short title",
  "description": "detailed description of what to implement",
  "owns": ["path/to/file.py"],
  "reads": ["path/to/dependency.py"],
  "depends_on": ["T-NNN"],
  "contracts": ["path/to/interface.py"],
  "test_requirements": {
    "unit": ["scenario description"],
    "integration": ["scenario description"],
    "coverage_threshold": 85
  },
  "security_constraints": ["constraint description"],
  "acceptance_criteria": "one-line definition of done",
  "estimated_lines": 150,
  "context_section": "architecture.md#anchor",
  "status": "pending"
}
```

Field rules:
- `owns` — files this task may write; no two tasks share an `owns` file
- `reads` — files read but not written; no ownership conflict
- `depends_on` — task IDs that must reach `MERGED` before this task spawns
- `contracts` — interface/stub files the implementation must satisfy
- `estimated_lines` — must be ≤ 250 per file; if a file would exceed 250 lines,
  split it into two tasks with separate owns entries

---

## Round Definition Format

After populating task definitions, add rounds to `execution_plan.md` under the
milestone heading:

```
| Round | Tasks           | Note                                    |
|-------|-----------------|------------------------------------------|
| A     | T-NNN, T-NNN   | All unblocked — run in parallel          |
| B     | T-NNN           | After Round A — depends on T-NNN         |
```

Round rules:
- Tasks with no `depends_on` within the milestone go in Round A
- Tasks that depend on Round A tasks go in Round B, and so on
- Tasks from different milestones never share a round
- Maximise parallelism: if two tasks are independent, put them in the same round

---

## Constraints

- No implementation file > 250 lines — split the task if needed
- No two tasks share an `owns` file
- `estimated_lines` ≤ 250 per file in the `owns` list
- Every task must have at least one entry in `test_requirements.unit`
- `acceptance_criteria` must be a single, verifiable sentence
- Do not re-prioritize tasks — order is set by the oracle; reflect it faithfully

---

## Milestone Block Format (execution_plan.md)

```
## Milestone N: [Name]
Status: PENDING
Architecture: architecture.md#[anchor]
Goal: [one-line goal]

| Task  | Title   | Depends on | Status  |
|-------|---------|------------|---------|
| T-NNN | [title] | [dep]      | PENDING |

| Round | Tasks         | Note                          |
|-------|---------------|-------------------------------|
| A     | T-NNN, T-NNN | All unblocked — run in parallel|
| B     | T-NNN         | After Round A                 |
```
