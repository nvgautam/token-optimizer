---
name: task-generator
description: Decomposes implementation requirements into tasks, structures parallel rounds using disjoint OWNS checks, writes clean tasks.json entries, and generates properly formatted addendums in execution_plan.md.
---

# Task Generator — Decomposing & Writing Tasks

Use this skill to break down complex feature requests or requirements into structured tasks following project architectural rules.

## Step 1: Decompose Requirements
1. **Identify Files**: List all target files that need to be created or modified.
2. **Assign Ownership (OWNS)**: Each file can only be modified by one task in a round. Map file paths to tasks.
3. **Sequence & Dependencies**: Identify which tasks depend on other tasks.

## Step 2: Disjoint OWNS Check & Round Composition
Before assigning tasks to the same round for parallel execution:
1. Extract the proposed `OWNS` file list for each task.
2. Verify that no two tasks in the same round share any of the same files.
3. If an overlap is found, split the overlapping tasks into separate, sequential rounds.
4. Any task without defined `OWNS` must be scheduled solo in its own round.

## Step 3: Write tasks.json Entries
Write tasks to `tasks.json` using **exactly** the following schema:
- ONLY `task_id` and `status` keys are allowed.
- No `title`, `description`, `owns`, or `depends_on` fields.
- Example:
```json
{
  "tasks": [
    {"task_id": "T-300", "status": "pending"},
    {"task_id": "T-301", "status": "pending"}
  ]
}
```

## Step 4: Write execution_plan.md Addendums
For each filed task, append a proper `## Addendum: T-NNN — Title` section to the end of `execution_plan.md` using the exact template format:

```markdown
## Addendum: T-NNN — Title

**Goal:** [1–2 sentences: what it does, why, context]

**Files:**
- `path/to/file.py` (new/modify) — purpose

**Test scenarios:**
- [concrete acceptance criterion]

**OWNS:** [comma-separated file list]
**estimated_lines:** [N]
```

*Note: Avoid any extra fields or format deviations to prevent CI and hook validation failures.*
