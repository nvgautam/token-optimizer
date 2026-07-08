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

---

## Targeted Reads Rule

Before reading any file (except phase files read at phase entry), check `.idx`:

1. Compute:
   ```bash
   HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
   IDX=~/.agentflow/cache/$HASH/index/<relative-path>.idx
   ```
2. Grep: `grep "^<symbol_name>:" "$IDX"` → `name:start-end`
3. Read: `Read(offset=start, limit=end-start+1)`
4. Fallback: `.idx` absent or symbol not found → read full file.

Phase files (`market.md`, `checklist.md`, `generation.md`) — read in full at phase entry; rule applies to all other reads.
