#!/usr/bin/env bash
# provision.sh — Manage AgentFlow license keys in Cloudflare Workers KV
#
# Required env vars:
#   CF_ACCOUNT_ID     — Cloudflare account ID
#   CF_API_TOKEN      — Cloudflare API token with Workers KV write access
#   KV_NAMESPACE_ID   — Workers KV namespace ID for the key registry
#
# Usage:
#   ./provision.sh add-key <api_key> [--tier=friendly]
#   ./provision.sh revoke-key <api_key>
#
# No shell=True: all wrangler invocations use direct CLI calls (no eval/sh -c).

set -euo pipefail

BUNDLE_VERSION="${BUNDLE_VERSION:-v1}"

usage() {
    echo "Usage:" >&2
    echo "  $0 add-key <api_key> [--tier=friendly|pro|enterprise]" >&2
    echo "  $0 revoke-key <api_key>" >&2
    exit 1
}

require_env() {
    local var="$1"
    if [[ -z "${!var:-}" ]]; then
        echo "Error: $var is not set." >&2
        exit 1
    fi
}

kv_put() {
    local key="$1"
    local value="$2"
    wrangler kv:key put \
        --account-id "$CF_ACCOUNT_ID" \
        --namespace-id "$KV_NAMESPACE_ID" \
        "$key" \
        "$value"
}

cmd_add_key() {
    local api_key="$1"
    local tier="friendly"

    # Parse optional --tier flag
    shift
    for arg in "$@"; do
        case "$arg" in
            --tier=*) tier="${arg#--tier=}" ;;
            *) echo "Unknown option: $arg" >&2; usage ;;
        esac
    done

    if [[ -z "$api_key" ]]; then
        echo "Error: api_key is required." >&2
        usage
    fi

    local payload
    payload=$(printf '{"status":"active","tier":"%s","bundle_version":"%s"}' \
        "$tier" "$BUNDLE_VERSION")

    kv_put "$api_key" "$payload"
    echo "Added key [tier=$tier, bundle_version=$BUNDLE_VERSION]: ${api_key:0:12}..."
}

cmd_revoke_key() {
    local api_key="$1"

    if [[ -z "$api_key" ]]; then
        echo "Error: api_key is required." >&2
        usage
    fi

    # Read current record to preserve tier/bundle_version
    local current
    current=$(wrangler kv:key get \
        --account-id "$CF_ACCOUNT_ID" \
        --namespace-id "$KV_NAMESPACE_ID" \
        "$api_key" 2>/dev/null || echo '{}')

    local tier bundle_version
    tier=$(echo "$current" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tier','unknown'))" 2>/dev/null || echo "unknown")
    bundle_version=$(echo "$current" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bundle_version','v1'))" 2>/dev/null || echo "v1")

    local payload
    payload=$(printf '{"status":"revoked","tier":"%s","bundle_version":"%s"}' \
        "$tier" "$bundle_version")

    kv_put "$api_key" "$payload"
    echo "Revoked key: ${api_key:0:12}..."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if [[ $# -lt 2 ]]; then
    usage
fi

COMMAND="$1"
API_KEY="$2"
shift 2

require_env CF_ACCOUNT_ID
require_env CF_API_TOKEN
require_env KV_NAMESPACE_ID

case "$COMMAND" in
    add-key)    cmd_add_key "$API_KEY" "$@" ;;
    revoke-key) cmd_revoke_key "$API_KEY" ;;
    *) echo "Unknown command: $COMMAND" >&2; usage ;;
esac
