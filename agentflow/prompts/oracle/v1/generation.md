# Oracle — Generation Protocol

When the user confirms, produce artifacts in this order. Emit each completely — no truncation.

## 1. architecture.md (project root)

Required sections in order:
- One-paragraph overview
- Guiding principles (bullet list)
- System components (ASCII block diagram)
- Package / directory structure (annotated tree)
- What-each-agent-reads table (agent | reads | writes)
- Task schema (JSON example with all fields)
- Task state machine (ASCII diagram: PENDING → ... → MERGED)
- Context bundle specification (labelled sections)
- File size limits (table: type | soft target | hard ceiling)
- Config schema excerpt (YAML)
- Telemetry schema (JSON example)
- Oracle checklist (copied from checklist.md, filled with resolved values)
- CLI surface (bash block)

## 2. tasks.json (project root)

Valid JSON. Each task object must include:
`task_id`, `title`, `description`, `owns`, `reads`, `depends_on`, `contracts`,
`test_requirements` (unit[], integration[], coverage_threshold),
`security_constraints`, `acceptance_criteria`, `estimated_lines`, `context_section`.

Validation rules (enforce before emitting):
- No two tasks share an `owns` entry.
- All `depends_on` values reference a valid `task_id` in the same file.
- `estimated_lines` must not exceed the ceiling for the file type.

Include a `parallelism_plan` object mapping round numbers to task_id arrays.

## 3. .agentflow/design_session.md

Structure:
- Decisions made (bullet list with brief rationale)
- Tradeoffs discussed (table: option | chose | rejected | reason)
- Options explicitly rejected (and why)
- Open questions deferred to implementation

## 4. .agentflow/test_strategy.md

Structure:
- Coverage thresholds (per file type)
- Mock boundaries (what is mocked and why)
- Integration test scope (what runs against real dependencies)
- Compliance-driven test scenarios (if any)

## 5. Contract stubs

After emitting the above, instruct the contract generator to:
- Create stub files for all `contracts` entries across all tasks
- Create test skeleton files for all `tests/` entries in `owns`
- Commit to main before any worker is spawned
