# AgentFlow Operator Triage — Skill Guide (Internal Only)

This guide details AgentFlow internal-only log paths, session identifiers, grep patterns, and PTY audit log interpretation. Do not share or package this file in customer-facing bundle distributions.

## Log File Architecture
All logs are written to `.agentflow/` workspace root:
- `hook_drain_debug.jsonl`: Post-tool use hook logs. Every entry includes `sid`.
- `pty_audit.jsonl`: PTY state transition, handoff status, token count evaluations, and cleanup events.

## Session Lifecycle & ID Mechanics
1. **Session Start Header**: Emitters append a session-start record as the first entry for each unique Session ID (`sid`).
   Schema: `{"sid": "<uuid>", "session_type": "orchestrator|oracle|worker|reviewer", "task_ids": ["T-NNN", ...], "ts": <timestamp>}`
2. **Turn Entries**: Turn markers and logs contain the `"sid"` field.
3. **Session State**: Session type is persisted in `.agentflow/sessions/<sid>/session_state.json`.

## Common Grep Patterns for Operator Triage
Extract all logs belonging to a single session sorted by timestamp:
```bash
agentflow logs --session <SID>
```

Filter PTY audit logs for manual handoff actions:
```bash
grep '"event": "manual_handoff_set"' .agentflow/pty_audit.jsonl
```

## PTY Audit Log Key Events
- `session_start_header`: Emitted when the PTY session opens.
- `session_type_transition`: Emitted when transitioning between active/inactive session types.
- `trigger_handoff`: Handoff limit reached or user requested manually.
- `reset_ansi_write_error`: Indicates PTY terminal write errors (check child processes).
