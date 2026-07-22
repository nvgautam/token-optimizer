"""Structured audit logger with PII/secret scrubbing."""
from __future__ import annotations
import datetime
import json
import os
import pathlib

from agentflow.config.constants import ENV_SESSION_ID, KEY_SID, KEY_TS, UTF8

_SENSITIVE_KEYS = frozenset({"api_key", "secret", "password", "token", "passwd", "auth"})


def scrub(entry: dict) -> dict:
    result = {}
    for k, v in entry.items():
        if isinstance(v, dict):
            result[k] = scrub(v)
        elif isinstance(v, str) and k.lower() in _SENSITIVE_KEYS:
            result[k] = "[REDACTED]"
        else:
            result[k] = v
    return result


def write_audit(log_path: pathlib.Path, entry: dict) -> None:
    if not log_path.parent.exists():
        return
    try:
        scrubbed = scrub(entry)
        record = {
            KEY_TS: datetime.datetime.now().isoformat(),
            KEY_SID: os.environ.get(ENV_SESSION_ID),
            "level": scrubbed.get("level", "INFO"),
            **scrubbed,
        }
        with open(log_path, "a", encoding=UTF8) as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass
