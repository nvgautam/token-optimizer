# Claude Code Slash Commands

These are Claude Code slash commands — skills invoked via `/command-name` in any Claude Code session.

## Commands

| Command | Description |
|---|---|
| `/orchestrate` | Group tasks from `tasks.json`, spawn implementation agents in isolated worktrees, run automated reviews, and merge PRs in dependency order |
| `/oracle` | Design sparring and architecture artifact generation — challenges assumptions, surfaces trade-offs, produces `architecture.md` and `tasks.json` |
| `/drift` | Architecture drift audit — compares current codebase against `architecture.md` and flags divergence |
| `/handoff` | End-of-session handoff — prunes merged worktree branches, aggregates token telemetry, writes a handoff memory file |

## Installing

Commands must be placed in one of two locations depending on scope:

**Global** — available in every project:
```bash
cp commands/claude/*.md ~/.claude/commands/
```

**Project-local** — available only in this project:
```bash
mkdir -p .claude/commands
cp commands/claude/*.md .claude/commands/
```

Claude Code picks up both locations automatically. Project-local commands take precedence over global ones with the same name.

## Updating

After editing a command file here, re-copy it to wherever you installed it:
```bash
# global
cp commands/claude/orchestrate.md ~/.claude/commands/orchestrate.md

# project-local
cp commands/claude/orchestrate.md .claude/commands/orchestrate.md
```
