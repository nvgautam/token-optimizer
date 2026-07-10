"""Diagnostic hook: log raw stdin payload to .agentflow/payload_inspect.jsonl."""
import json
import os
import sys
from pathlib import Path

event = os.environ.get("AGENTFLOW_HOOK_EVENT", "unknown")
payload = json.load(sys.stdin)

out = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".agentflow" / "payload_inspect.jsonl"
with open(out, "a") as f:
    json.dump({"event": event, "keys": list(payload.keys()), "payload": payload}, f)
    f.write("\n")
