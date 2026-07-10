#!/usr/bin/env bash
# AgentFlow design-partner installer
# Usage:
#   ./install.sh
#
# Env var overrides (all optional):
#   AGENTFLOW_INSTALL_DIR   — directory for the agentflow binary (default: /usr/local/bin)
#   CLAUDE_COMMANDS_DIR     — directory for Claude Code skills   (default: ~/.claude/commands)
#   AGENTFLOW_SKIP_HOOKS    — set to 1 to skip hook-merge step  (useful for CI/testing)

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (no hardcoded user-specific paths — all overridable)
# ---------------------------------------------------------------------------
INSTALL_DIR="${AGENTFLOW_INSTALL_DIR:-/usr/local/bin}"
COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
SKIP_HOOKS="${AGENTFLOW_SKIP_HOOKS:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_BINARY="$SCRIPT_DIR/dist/agentflow"
SKILLS_SRC="$SCRIPT_DIR/commands/claude"

# ---------------------------------------------------------------------------
# Step 1: Install binary
# ---------------------------------------------------------------------------
if [ -f "$DIST_BINARY" ]; then
    mkdir -p "$INSTALL_DIR"
    cp "$DIST_BINARY" "$INSTALL_DIR/agentflow"
    chmod +x "$INSTALL_DIR/agentflow"
    echo "agentflow: binary installed → $INSTALL_DIR/agentflow"
else
    echo "agentflow: WARNING — binary not found at $DIST_BINARY, skipping binary install" >&2
fi

# ---------------------------------------------------------------------------
# Step 2: Install skills (commands/claude/ → CLAUDE_COMMANDS_DIR/claude/)
# ---------------------------------------------------------------------------
if [ -d "$SKILLS_SRC" ]; then
    mkdir -p "$COMMANDS_DIR/claude"
    cp -r "$SKILLS_SRC/." "$COMMANDS_DIR/claude/"
    echo "agentflow: skills installed → $COMMANDS_DIR/claude/"
else
    echo "agentflow: WARNING — skills directory not found at $SKILLS_SRC, skipping skills install" >&2
fi

# ---------------------------------------------------------------------------
# Step 3: Merge hooks into ~/.claude/settings.json
# ---------------------------------------------------------------------------
if [ "$SKIP_HOOKS" = "1" ]; then
    echo "agentflow: AGENTFLOW_SKIP_HOOKS=1 — skipping hook-merge step"
else
    if command -v agentflow > /dev/null 2>&1; then
        agentflow install
    elif [ -x "$INSTALL_DIR/agentflow" ]; then
        "$INSTALL_DIR/agentflow" install
    else
        echo "agentflow: WARNING — agentflow binary not on PATH and not in $INSTALL_DIR; skipping hook-merge" >&2
    fi
fi

echo "agentflow: installation complete"
