"""Fill token utilities for context_fill.json management.

Computes and extracts fill tokens (input_tokens + cache_read_input_tokens + cache_creation_input_tokens)
from transcript entries and usage data.
"""
import json


def compute_fill(usage: dict) -> int:
    """Sum the three input token fields; output_tokens not included."""
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def extract_fill_from_transcript(transcript_path: str) -> int | None:
    """Return fill for the last assistant entry with usage; None if absent."""
    last_fill: int | None = None
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                usage = entry.get("message", {}).get("usage")
                if usage is not None:
                    last_fill = compute_fill(usage)
    except OSError:
        return None
    return last_fill
