#!/bin/bash
set -euo pipefail

# Nuitka compilation script for agentflow PTY shell
# Usage: ./compile.sh [--output-dir OUTPUT_DIR]
# Default output directory: dist/

OUTPUT_DIR="${1:-dist}"

# Detect python interpreter
PYTHON="${PYTHON:-python3}"

# Nuitka compile command
exec "$PYTHON" -m nuitka \
  --standalone \
  --onefile \
  --output-dir="$OUTPUT_DIR" \
  --include-package=agentflow \
  --output-filename=agentflow \
  agentflow/cli.py
