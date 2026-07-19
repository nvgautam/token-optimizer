# Artifact Generation Spec

---

## Compact writing rules

- **Tables and bullets only** — no prose paragraphs in any artifact.
- **Telegraphic style** — no articles (a/an/the), no transition phrases, no "This module…" / "The system will…" sentences.
- **≤10 words per bullet or table cell** — split longer ideas into sub-bullets.
- One idea per bullet; sub-bullets for detail, not continuation.
- Tables for comparisons, tradeoffs, status matrices, or anything with ≥2 attributes.
- Applies to all generated content: `tasks.json` descriptions, `execution_plan.md` entries, `design_status.md` decisions, `architecture.md` sections, `CLAUDE.md` body.

---

## Architecture.md format

Each design item uses one of three statuses:

```
**RESOLVED** — [item name]: [one-line decision]
**UNRESOLVED** — [item name]: [open question or blocking uncertainty]
**DEFERRED** — [item name]: [what was deferred and why]
```

Required sections (in order):
1. Overview — one-line purpose + tech stack table
2. Module Boundaries — table: module | responsibility | owns
3. Shared Interfaces — table: interface | producer | consumer | contract location
4. External Integrations — table: service | owner module | credential storage | failure strategy
5. Data Flow — bullet list of critical paths
6. Security Model — bullets: auth, authz, data sensitivity, trust boundaries
7. Test Strategy — table: layer | scope | mock boundary | coverage floor
8. Deployment Target — bullets: cloud/on-prem, container strategy, CI/CD

---

## CLAUDE.md template

```markdown
# [Project Name]

[One-line purpose]

## Commands
- Test:  `<test command>`
- Lint:  `<lint command>`
- Build: `<build command>`

## Structure
\`\`\`
[module paths and one-line descriptions]
\`\`\`

## State documents
\`\`\`
architecture.md   → living design document
execution_plan.md → milestone plan
tasks.json        → task lifecycle
\`\`\`

## Integrations
\`\`\`
[service]: [owner module] — [credential location]
\`\`\`

## Constraints
- [constraint 1]
- [constraint 2]

## Tech stack
[language, framework, persistence, key libs]

## Deployment
[cloud/on-prem, container, CI/CD]

## Reference
- Full architecture: architecture.md
- Milestone plan:    execution_plan.md
- Task status:       tasks.json
```

---

## tasks.json schema

```json
{
  "tasks": [
    {"task_id": "T-001", "status": "pending"}
  ]
}
```

Rules:
- **`task_id` and `status` ONLY** — no `title`, `description`, `owns`, `reads`, `depends_on`, `estimated_lines`, or any other field
- All task spec (title, description, owns, test scenarios) goes in `execution_plan.md` addendum ONLY
- All tasks start with `status: "pending"`
- Violation enforced by `tests/test_tasks_json_schema.py` — any extra field fails CI

---

## execution_plan.md format

Milestone table:

| Milestone | Goal | Status | Rounds |
|---|---|---|---|
| M1 | [goal] | pending | [N] |

Round grouping (within each milestone):

```
### Round R1
| Task | Description | Depends on |
|---|---|---|
| T-001 | ... | — |
| T-002 | ... | T-001 |
```

- Group tasks into rounds by dependency order — all tasks in a round can run in parallel.
- Each round starts only after all tasks in the prior round are complete.
- Round size target: 3–6 tasks; split if larger.
