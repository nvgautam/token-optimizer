# Milestone Decomposition Format

Use this format when decomposing a milestone from its architecture anchor section.

## Milestone record (in execution_plan.md)

```yaml
milestone: M-02
name: "Prompt Layer"
status: IN_PROGRESS          # PENDING | IN_PROGRESS | COMPLETE | MERGED
architecture_anchor: "#prompt-layer"
rounds:
  - round: 1
    parallel: true
    tasks: [T-013, T-014, T-015]
  - round: 2
    parallel: false
    tasks: [T-016]
```

- `architecture_anchor`: the heading in `architecture.md` to load (section only, never full doc)
- `rounds`: execution order; tasks in the same round run in parallel
- `parallel: true` means spawn all tasks in the round simultaneously

## Task record formats

### Stub (pre-decomposition — do not spawn workers against stubs)

```json
{
  "id": "T-015",
  "title": "Reviewer + orchestrator prompts",
  "status": "PENDING",
  "stub": true
}
```

### Full definition (ready to spawn)

```json
{
  "id": "T-015",
  "title": "Reviewer + orchestrator prompts",
  "status": "PENDING",
  "stub": false,
  "owns": [
    "agentflow/reviewer/prompts/v1/code_review.md",
    "agentflow/reviewer/prompts/v1/security_review.md",
    "agentflow/reviewer/prompts/v1/test_review.md",
    "agentflow/orchestrator/prompts/v1/system.md",
    "agentflow/orchestrator/prompts/v1/planning.md",
    "tests/prompts/test_reviewer_orchestrator_prompts.py"
  ],
  "reads": [
    "architecture.md#security-model",
    "architecture.md#orchestrator-design"
  ],
  "test_requirements": {
    "unit": [
      "all prompt files exist and are valid UTF-8",
      "no prompt file exceeds 150 lines",
      "security_review.md references OWASP",
      "security_review.md contains untrusted-diff rule",
      "planning.md contains milestone decomposition format",
      "system.md contains Staff Engineering Lead persona",
      "system.md contains escalation criteria"
    ],
    "integration": []
  },
  "coverage_threshold": 90,
  "security_constraints": []
}
```

## Decomposition rules

1. One task per file-ownership cluster — no task owns files in two unrelated modules.
2. Tasks with no interdependency go in the same round (`parallel: true`).
3. A task that reads the output of another task goes in a later round.
4. Stub tasks must be fully decomposed before the round that contains them begins.
5. Write decomposed task records to `tasks.json` before spawning any workers.
