#!/usr/bin/env bash
# Build the AgentFlow customer distribution archive.
#
# Usage:
#   AGENTFLOW_MASTER_KEY=<hex-or-passphrase> ./scripts/build_dist.sh
#
# Optional env vars:
#   AGENTFLOW_SKIP_COMPILE=1    skip Nuitka compile (use existing dist/agentflow)
#   AGENTFLOW_DIST_DIR          output directory (default: <project-root>/dist)
#   AGENTFLOW_SKILLS_SRC        skill source dir (default: commands/claude)
#
# Output: $AGENTFLOW_DIST_DIR/agentflow-v<version>.tar.gz
# Idempotent: running twice replaces the previous archive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DIST_DIR="${AGENTFLOW_DIST_DIR:-$PROJECT_ROOT/dist}"
SOURCE_DIR="${AGENTFLOW_SKILLS_SRC:-$PROJECT_ROOT/commands/claude}"
SKIP_COMPILE="${AGENTFLOW_SKIP_COMPILE:-0}"
STUBS_DIR="$SCRIPT_DIR/stubs"

if [ -z "${AGENTFLOW_MASTER_KEY:-}" ] && [ -z "${AGENTFLOW_KEY:-}" ]; then
  echo "Error: AGENTFLOW_MASTER_KEY (or AGENTFLOW_KEY) must be set." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION=$(python3 -c "
import re, pathlib
try:
    text = pathlib.Path('$PROJECT_ROOT/pyproject.toml').read_text()
    m = re.search(r'version\s*=\s*\"([^\"]+)\"', text)
    print(m.group(1) if m else '0.0.0')
except Exception:
    print('0.0.0')
" 2>/dev/null || echo "0.0.0")

ARCHIVE_NAME="agentflow-v${VERSION}"
STAGING="$DIST_DIR/$ARCHIVE_NAME"
BUNDLE_PATH="$STAGING/skills/bundle-v1.enc"

# ---------------------------------------------------------------------------
# Step 1: Compile binary (skip if AGENTFLOW_SKIP_COMPILE=1)
# ---------------------------------------------------------------------------
if [ "$SKIP_COMPILE" = "1" ]; then
  echo "[dist] Skipping Nuitka compile (AGENTFLOW_SKIP_COMPILE=1)"
else
  echo "[dist] Compiling with Nuitka..."
  mkdir -p "$DIST_DIR"
  cd "$PROJECT_ROOT"
  bash "$PROJECT_ROOT/agentflow/ip/compile.sh" "$DIST_DIR"
fi

BINARY="$DIST_DIR/agentflow"
if [ ! -f "$BINARY" ]; then
  echo "Error: binary not found at $BINARY — compile first or set AGENTFLOW_SKIP_COMPILE=1." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Strip all .py / .pyc from dist directory (no source in delivery)
# ---------------------------------------------------------------------------
echo "[dist] Stripping .py and .pyc from $DIST_DIR..."
find "$DIST_DIR" \( -name "*.py" -o -name "*.pyc" \) -delete

# ---------------------------------------------------------------------------
# Step 3: Assemble staging directory
# ---------------------------------------------------------------------------
echo "[dist] Assembling $STAGING..."
rm -rf "$STAGING"
mkdir -p "$STAGING/dist" "$STAGING/stubs" "$STAGING/skills"

cp "$BINARY" "$STAGING/dist/agentflow"
chmod +x "$STAGING/dist/agentflow"

# ---------------------------------------------------------------------------
# Step 4: Build encrypted skill bundle into staging/skills/
# ---------------------------------------------------------------------------
echo "[dist] Encrypting skill bundle..."
cd "$PROJECT_ROOT"
python3 -m agentflow.ip.build_bundle \
  --source-dir "$SOURCE_DIR" \
  --output "$BUNDLE_PATH"

# ---------------------------------------------------------------------------
# Step 5: Copy stubs
# ---------------------------------------------------------------------------
cp "$STUBS_DIR/"*.md "$STAGING/stubs/"

# ---------------------------------------------------------------------------
# Step 6: Copy install.sh into staging
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/install.sh" "$STAGING/install.sh"
chmod +x "$STAGING/install.sh"

# ---------------------------------------------------------------------------
# Step 7: Verify no .py/.pyc in staging directory
# ---------------------------------------------------------------------------
PY_COUNT=$(find "$STAGING" \( -name "*.py" -o -name "*.pyc" \) | wc -l | tr -d '[:space:]')
if [ "$PY_COUNT" -ne 0 ]; then
  echo "Error: staging directory contains Python source files:" >&2
  find "$STAGING" \( -name "*.py" -o -name "*.pyc" \) >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 8: Create versioned .tar.gz
# ---------------------------------------------------------------------------
ARCHIVE="$DIST_DIR/agentflow-v${VERSION}.tar.gz"
echo "[dist] Creating $ARCHIVE..."
cd "$DIST_DIR"
tar -czf "$ARCHIVE" "$ARCHIVE_NAME/"

echo "[dist] Done. Distribution archive: $ARCHIVE"
