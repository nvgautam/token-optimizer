# Artifact Generation Spec

---

## Compact writing rules

- **Tables and bullet points only** for all state document writes (architecture.md, CLAUDE.md, tasks.json, execution_plan.md).
- **No prose paragraphs.** If a sentence begins with "This module..." or "The system will...", rewrite it as a bullet.
- Target 35–40% smaller than prose equivalent.
- One idea per bullet; sub-bullets for detail, not continuation.
- Tables for comparisons, tradeoffs, status matrices, or anything with two or more attributes.

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
    {
      "task_id": "T-001",
      "description": "one-line description of what to implement",
      "owns": ["src/module/file.py"],
      "reads": ["src/other/dependency.py"],
      "depends_on": [],
      "estimated_lines": 120,
      "security_sensitive": false,
      "status": "pending",
      "test_scenarios": ["test_happy_path", "test_edge_case"]
    }
  ]
}
```

Rules:
- No two tasks share an `owns` file
- `estimated_lines` ≤ 250 per owned file
- `security_sensitive: true` for tasks touching auth, external APIs, user input, data storage, or compliance
- All tasks start with `status: "pending"`
- Milestone 1: full task definitions; later milestones: slim stubs only

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
