"""Structured audit logger with async write queue, PII/secret scrubbing, and log rotation."""
from __future__ import annotations
import datetime
import json
import os
import pathlib
import queue
import threading

from agentflow.config.constants import ENV_SESSION_ID, KEY_SID, KEY_TS, UTF8

_SENSITIVE_KEYS = frozenset({"api_key", "secret", "password", "token", "passwd", "auth"})

_MAX_LOG_BYTES: int = 5 * 1024 * 1024  # 5 MB — monkeypatch-able in tests
_MAX_ROTATED: int = 3                    # monkeypatch-able in tests

# ---------------------------------------------------------------------------
# Background write queue
# ---------------------------------------------------------------------------
_q: queue.Queue = queue.Queue()


def _worker() -> None:
    while True:
        item = _q.get()
        if item is None:
            _q.task_done()
            break
        log_path, record = item
        try:
            _rotate_if_needed(log_path)
            with open(log_path, "a", encoding=UTF8) as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass
        finally:
            _q.task_done()


_thread = threading.Thread(target=_worker, daemon=True)
_thread.start()


def flush_writes() -> None:
    """Block until all enqueued writes are complete."""
    _q.join()


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------

def _rotate_if_needed(log_path: pathlib.Path) -> None:
    """Rotate log_path to log_path.1 (shifting .1→.2 etc.) if >= _MAX_LOG_BYTES."""
    try:
        if not log_path.exists() or log_path.stat().st_size < _MAX_LOG_BYTES:
            return
        # Shift existing rotated files: .N-1 → .N (drop if > _MAX_ROTATED)
        for n in range(_MAX_ROTATED, 0, -1):
            src = pathlib.Path(f"{log_path}.{n - 1}") if n > 1 else log_path
            dst = pathlib.Path(f"{log_path}.{n}")
            if n == _MAX_ROTATED and dst.exists():
                dst.unlink()
            if src.exists() and n > 1:
                src.rename(dst)
        # Rename current log to .1
        rotated = pathlib.Path(f"{log_path}.1")
        log_path.rename(rotated)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_audit(
    log_path: pathlib.Path,
    *,
    event: str,
    source: str,
    level: str = "INFO",
    session_type: str | None = None,
    **extra: object,
) -> None:
    """Enqueue an audit record for async write.

    Raises TypeError (from Python) if ``event`` or ``source`` are not supplied
    as keyword arguments.
    """
    if not log_path.parent.exists():
        return
    entry: dict = {"event": event, "source": source, "level": level, **extra}
    scrubbed = scrub(entry)
    record: dict = {
        KEY_TS: datetime.datetime.now().isoformat(),
        KEY_SID: os.environ.get(ENV_SESSION_ID),
        "level": scrubbed.get("level", "INFO"),
        **scrubbed,
    }
    if session_type is not None:
        record["session_type"] = session_type
    _q.put((log_path, record))
