#!/usr/bin/env bash
# AgentFlow customer installer.
# Run from inside the extracted distribution archive directory.
#
# Usage:
#   ./install.sh
#
# Optional env vars:
#   AGENTFLOW_INSTALL_DIR   binary destination (default: /usr/local/bin)
#   CLAUDE_COMMANDS_DIR     stub destination   (default: ~/.claude/commands)
#   AGENTFLOW_BUNDLE_DEST   bundle destination (default: ~/.agentflow/skills/bundle-v1.enc)
#   AGENTFLOW_SKIP_HOOKS    set to 1 to skip hook registration (CI/testing)
#   AGENTFLOW_ARCHIVE_DIR   override archive root dir (default: dir of this script)
#
# Idempotent: safe to run multiple times — no duplicate hooks or stubs.

set -euo pipefail

ARCHIVE_DIR="${AGENTFLOW_ARCHIVE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
INSTALL_DIR="${AGENTFLOW_INSTALL_DIR:-/usr/local/bin}"
COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
BUNDLE_DEST="${AGENTFLOW_BUNDLE_DEST:-$HOME/.agentflow/skills/bundle-v1.enc}"
SKIP_HOOKS="${AGENTFLOW_SKIP_HOOKS:-0}"

BINARY_SRC="$ARCHIVE_DIR/dist/agentflow"
STUBS_SRC="$ARCHIVE_DIR/stubs"
BUNDLE_SRC="$ARCHIVE_DIR/skills/bundle-v1.enc"

# ---------------------------------------------------------------------------
# Step 1: Install binary
# ---------------------------------------------------------------------------
if [ -f "$BINARY_SRC" ]; then
  mkdir -p "$INSTALL_DIR"
  cp "$BINARY_SRC" "$INSTALL_DIR/agentflow"
  chmod +x "$INSTALL_DIR/agentflow"
  echo "agentflow: binary installed -> $INSTALL_DIR/agentflow"
else
  echo "agentflow: WARNING — binary not found at $BINARY_SRC" >&2
fi

# ---------------------------------------------------------------------------
# Step 2: Install stub .md files into COMMANDS_DIR (idempotent — skip unchanged)
# ---------------------------------------------------------------------------
if [ -d "$STUBS_SRC" ]; then
  mkdir -p "$COMMANDS_DIR"
  for stub in "$STUBS_SRC"/*.md; do
    [ -f "$stub" ] || continue
    name="$(basename "$stub")"
    dest="$COMMANDS_DIR/$name"
    if [ ! -f "$dest" ] || ! cmp -s "$stub" "$dest"; then
      cp "$stub" "$dest"
    fi
  done
  echo "agentflow: stubs installed -> $COMMANDS_DIR"
else
  echo "agentflow: WARNING — stubs directory not found at $STUBS_SRC" >&2
fi

# ---------------------------------------------------------------------------
# Step 3: Install encrypted skill bundle
# ---------------------------------------------------------------------------
if [ -f "$BUNDLE_SRC" ]; then
  mkdir -p "$(dirname "$BUNDLE_DEST")"
  cp "$BUNDLE_SRC" "$BUNDLE_DEST"
  echo "agentflow: skill bundle installed -> $BUNDLE_DEST"
else
  echo "agentflow: WARNING — bundle not found at $BUNDLE_SRC" >&2
fi

# ---------------------------------------------------------------------------
# Step 4: Register Claude Code hooks (idempotent via agentflow install)
# ---------------------------------------------------------------------------
if [ "$SKIP_HOOKS" = "1" ]; then
  echo "agentflow: AGENTFLOW_SKIP_HOOKS=1 — skipping hook registration"
else
  if command -v agentflow > /dev/null 2>&1; then
    agentflow install
  elif [ -x "$INSTALL_DIR/agentflow" ]; then
    "$INSTALL_DIR/agentflow" install
  else
    echo "agentflow: WARNING — binary not on PATH and not in $INSTALL_DIR; skipping hooks" >&2
  fi
fi

# ---------------------------------------------------------------------------
# Step 5: Smoke test
# ---------------------------------------------------------------------------
SMOKE_BIN=""
if command -v agentflow > /dev/null 2>&1; then
  SMOKE_BIN="agentflow"
elif [ -x "$INSTALL_DIR/agentflow" ]; then
  SMOKE_BIN="$INSTALL_DIR/agentflow"
fi

if [ -n "$SMOKE_BIN" ]; then
  if "$SMOKE_BIN" --version > /dev/null 2>&1; then
    echo "agentflow: smoke test passed ($("$SMOKE_BIN" --version 2>&1))"
  else
    echo "agentflow: WARNING — smoke test failed ('$SMOKE_BIN --version' non-zero)" >&2
  fi
else
  echo "agentflow: smoke test skipped — binary not in PATH or $INSTALL_DIR"
fi

echo "agentflow: installation complete"
