### Step 2c — Prioritization Spar (pending tasks found)

Use `.idx` to read only the "Master Round Table" section of `execution_plan.md` (grep for `^## Master Round Table` in the idx, then `Read(offset, limit)`). If no idx exists, read full file. Group PENDING tasks into **value tiers** — what each group unlocks (e.g., "handoff precision", "parallel throughput", "multi-provider"). Identify independent tasks (no pending deps) as Round A candidates; chain dependents into subsequent rounds.

> **Disjoint OWNS Check (mandatory before round composition):**
>
> For each task proposed for parallel assignment, extract its OWNS set from the task's addendum:
> 1. Grep: `grep -A 2 "^| T-NNN |" execution_plan.md` to find the task row
> 2. Grep: `grep "^\\*\\*OWNS:\\*\\*" execution_plan.md` to locate the addendum
> 3. Extract: All file paths listed in backticks after `**OWNS:**`
> 4. **If OWNS is missing/undefined:** Schedule the task solo in its own round (unknown coverage — cannot verify disjoint)
> 5. **For each pair of tasks (A, B) proposed for the same round:** Verify no overlapping files between A.OWNS and B.OWNS
> 6. **If any pair overlaps:** Split both into separate sequential solo rounds (A Round X, B Round X+1)
> 7. **Repeat pairwise check** for all remaining tasks in the proposed group — only truly disjoint pairs may coexist

> **Round composition rule:** Same round = truly parallel (disjoint OWNS sets, spawned simultaneously). Sequential dependency = separate rounds (one task per round). Before writing the round table, verify every `‖` group has pairwise-disjoint OWNS sets — if any overlap, split into sequential solo rounds. Never group sequential tasks into one round.

Lead with:
- Recommended round table (A / B / C…) + dominant rationale (one line per round: what ships)
- The key trade-off driving the order (e.g., "shortest path to token savings vs. differentiator features")

Spar on — ≤3 sentences per exchange; challenge vague answers: delivery context (internal/external), next increment, constraints. On agreement: write round table into `execution_plan.md`. Emit `HANDOFF RECOMMENDED: task prioritization resolved — good stopping point`. Say: "Run `/orchestrate` to begin implementation."
