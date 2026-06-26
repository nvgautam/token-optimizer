#!/usr/bin/env bash
# run_handoff.sh — Emit HANDOFF_COMPLETE signal for PTY shell detection.
# Usage: run_handoff.sh <state_file>
#   <state_file>  Path to the state document that was flushed (e.g. architecture.md)
#
# The Gemini skill (SKILL.md) handles the actual state writing. This script
# emits the signal that the PTY shell scans for on stdout.

set -euo pipefail

STATE_FILE="${1:-architecture.md}"

echo "HANDOFF_COMPLETE: ${STATE_FILE}"
