# AgentFlow — Design Partner Installation Guide

This package is a pre-release build of AgentFlow for design partner evaluation.
It installs a compiled binary, Claude Code skill files, and optional hook configuration.

---

## Prerequisites

| Requirement | Version |
|---|---|
| macOS or Linux | any recent release |
| Claude Code CLI | installed and on PATH |
| Bash | 3.2+ (macOS default is fine) |

No Python runtime is required — the binary is self-contained.

---

## Installation

1. Extract the package archive into a directory of your choice.
2. Run the installer from that directory:

```bash
./install.sh
```

The installer performs three steps:

1. Copies the `agentflow` binary to `/usr/local/bin` (override with `AGENTFLOW_INSTALL_DIR`).
2. Copies skill files from `commands/claude/` to `~/.claude/commands/claude/` (override with `CLAUDE_COMMANDS_DIR`).
3. Merges AgentFlow hooks into `~/.claude/settings.json` (idempotent and non-destructive).

### Environment variable overrides

| Variable | Default | Purpose |
|---|---|---|
| `AGENTFLOW_INSTALL_DIR` | `/usr/local/bin` | Binary destination |
| `CLAUDE_COMMANDS_DIR` | `~/.claude/commands` | Skill file destination |
| `AGENTFLOW_SKIP_HOOKS` | `0` | Set to `1` to skip hook-merge (CI/testing) |

Example — install binary to a local path:

```bash
AGENTFLOW_INSTALL_DIR="$HOME/.local/bin" ./install.sh
```

---

## Quick Start

Once installed, open a Claude Code session in any project:

```bash
/oracle        # design sparring session
/orchestrate   # multi-agent task decomposition + execution
/handoff       # flush session state
/drift         # architecture drift audit
```

Token usage analytics:

```bash
agentflow report        # savings summary across all strategies
```

---

## Verify Installation

```bash
agentflow --version     # prints binary version
agentflow report        # shows token savings (will show 0 until sessions run)
```

---

## Uninstall

```bash
agentflow uninstall     # removes AgentFlow hooks from ~/.claude/settings.json
rm "$(which agentflow)" # removes the binary
```

Skill files in `~/.claude/commands/claude/` can be removed manually if desired.
Other entries in `~/.claude/settings.json` are left untouched.

---

## Feedback

Please share feedback via the channel your design-partner contact provided.
Include the output of `agentflow --version` in any bug reports.
