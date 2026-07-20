#!/usr/bin/env bash
# Build the encrypted skill bundle for distribution.
#
# Usage:
#   AGENTFLOW_MASTER_KEY=<hex-or-passphrase> ./scripts/build_dist.sh
#
# The bundle is written to ~/.agentflow/skills/bundle-v1.enc.
# Running this script a second time replaces the existing bundle (idempotent).

set -euo pipefail

BUNDLE_PATH="${AGENTFLOW_BUNDLE_PATH:-$HOME/.agentflow/skills/bundle-v1.enc}"
SOURCE_DIR="${AGENTFLOW_SKILLS_SRC:-commands/claude}"

if [ -z "${AGENTFLOW_MASTER_KEY:-}" ] && [ -z "${AGENTFLOW_KEY:-}" ]; then
  echo "Error: AGENTFLOW_MASTER_KEY (or AGENTFLOW_KEY) must be set." >&2
  exit 1
fi

echo "Building skill bundle from ${SOURCE_DIR} → ${BUNDLE_PATH} ..."

python3 -m agentflow.ip.build_bundle \
  --source-dir "${SOURCE_DIR}" \
  --output "${BUNDLE_PATH}"

echo "Done. Bundle written to ${BUNDLE_PATH}"
