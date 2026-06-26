# Oracle — Generation Protocol

When the user confirms, produce artifacts in this order. Emit each completely — no truncation.

## Compact writing rules (apply to all state documents)

- Tables over prose for comparisons and mappings.
- Bullets over paragraphs for lists.
- No sentence-level explanations in state documents — encode decisions as structured items.
- One-line rationale per RESOLVED item; no rationale for DEFERRED.

---

## 1. architecture.md (project root)

State document. Use RESOLVED / UNRESOLVED / DEFERRED item format.

**Item format:**
```
## <Section Name>
Status: RESOLVED
Decision: <one-line decision>
Rationale: <one sentence>
```

```
## <Section Name>
Status: UNRESOLVED
Question: <open question>
Options: [<option A>, <option B>]
```

```
## <Section Name>
Status: DEFERRED
Reason: <one-line reason>
```

**Required sections (in order):**
- Overview (2–3 bullets, no prose paragraphs)
- Guiding Principles (bullet list)
- Market Segment + Defaults (table)
- System Components (ASCII block diagram)
- Package / Directory Structure (annotated tree)
- Agent Reads / Writes Table (`agent | reads | writes`)
- Task Schema (JSON example with all required fields)
- Task State Machine (ASCII: `PENDING → IN_PROGRESS → REVIEW → HUMAN_APPROVED → MERGED`)
- Context Bundle Specification (labelled sections)
- File Size Limits (table: `type | soft target | hard ceiling`)
- Config Schema (YAML excerpt)
- Telemetry Schema (JSON example)
- Oracle Checklist (copied from checklist.md, filled with resolved values)
- CLI Surface (bash block)

---

## 2. CLAUDE.md (project root)

Project guide loaded at the start of every Claude Code session.

**Required sections:**
- Project name + one-line purpose
- Commands table (`Test | Lint | Build | Run`)
- Directory structure (annotated tree — same as architecture.md)
- State documents list (living documents — path + one-line description each)
- Integrations (bullet list)
- Constraints (bullet list — hard limits only, no prose)
- Tech stack (one-liner per layer)
- Deployment (one-liner)
- Reference (links to architecture.md, execution_plan.md, tasks.json)

---

## 3. execution_plan.md (project root)

- Milestone table: `milestone | goal | exit criterion`
- Milestone 1: full task definitions (same schema as tasks.json)
- Milestones 2+: one-line stub per milestone only — the orchestrator expands them

---

## 4. tasks.json (project root)

Valid JSON. Each task object must include:

| Field | Type | Notes |
|---|---|---|
| `task_id` | string | Unique, e.g. `T-001` |
| `title` | string | |
| `description` | string | |
| `owns` | array | Files this task creates or is sole owner of |
| `reads` | array | Files this task reads but does not own |
| `depends_on` | array | `task_id` values that must merge first |
| `contracts` | array | Stub files this task's interfaces require |
| `test_requirements` | object | `unit[]`, `integration[]`, `coverage_threshold` |
| `security_constraints` | array | Per-task security obligations |
| `acceptance_criteria` | array | Verifiable conditions for done |
| `estimated_lines` | integer | Must not exceed ceiling for file type |
| `context_section` | string | Section in architecture.md to load |

**Validation rules (enforce before emitting):**
- No two tasks share an `owns` entry.
- All `depends_on` values reference a valid `task_id` in the same file.
- `estimated_lines` must not exceed the hard ceiling for the file type.

Include a `parallelism_plan` object: `{ "round_N": ["T-001", "T-002", ...] }`.

Milestone 1 tasks: full definitions. Future milestones: slim stubs (`task_id`, `title`, `milestone` only).

---

## 5. Contract stubs (after tasks.json)

Instruct the contract generator to:
- Create stub files for all `contracts` entries across all Milestone 1 tasks.
- Create test skeleton files for all `tests/` entries in `owns`.
- Commit stubs to main before any worker agent is spawned.
