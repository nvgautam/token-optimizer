## Handoff

After writing files, run silently:
```bash
python agentflow.py handoff "oracle: [project name from sparring]"
```

Say:
```
Design complete. Five files written:
  design_status.md  — oracle state (RESOLVED/UNRESOLVED/DEFERRED) — read by oracle on startup
  architecture.md   — full design reference — read by workers, not oracle
  CLAUDE.md         — project guide for future sessions
  execution_plan.md — milestone structure with full M1 task definitions
  tasks.json        — tasks ready for implementation

Open a new Claude session in this directory and run /orchestrate to begin implementation.
```

Don't proceed to implementation. If user asks: "Run /orchestrate in a new session to begin implementation."

