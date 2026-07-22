"""Tests for agentflow.shell.audit_logger."""
from __future__ import annotations
import json
import threading

import pytest

import agentflow.shell.audit_logger as _mod
from agentflow.shell.audit_logger import flush_writes, scrub, write_audit


# ---------------------------------------------------------------------------
# scrub() tests (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_scrub_redacts_sensitive_key():
    result = scrub({"token": "abc123secret"})
    assert result["token"] == "[REDACTED]"


def test_scrub_passes_nonsensitive():
    entry = {"event": "foo", "count": 42}
    result = scrub(entry)
    assert result == {"event": "foo", "count": 42}


def test_scrub_nested_dict():
    entry = {"outer": {"password": "s3cr3t", "user": "alice"}, "name": "test"}
    result = scrub(entry)
    assert result["outer"]["password"] == "[REDACTED]"
    assert result["outer"]["user"] == "alice"
    assert result["name"] == "test"


def test_scrub_does_not_mutate_original():
    entry = {"token": "secret_value", "event": "e"}
    scrub(entry)
    assert entry["token"] == "secret_value"


# ---------------------------------------------------------------------------
# Scenario 1 & 2: TypeError on missing required kwargs
# ---------------------------------------------------------------------------

def test_write_audit_missing_event_raises(tmp_path):
    """Scenario 1: TypeError when event kwarg is absent."""
    with pytest.raises(TypeError):
        write_audit(tmp_path / "audit.jsonl", source="shell")


def test_write_audit_missing_source_raises(tmp_path):
    """Scenario 2: TypeError when source kwarg is absent."""
    with pytest.raises(TypeError):
        write_audit(tmp_path / "audit.jsonl", event="startup")


# ---------------------------------------------------------------------------
# Scenario 3: Async write appears after flush_writes()
# ---------------------------------------------------------------------------

def test_write_audit_async_appears_after_flush(tmp_path):
    """Scenario 3: Entry absent before flush; present after."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="async_test", source="shell")
    flush_writes()
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "async_test"


# ---------------------------------------------------------------------------
# Scenario 4: Two calls + flush → two lines
# ---------------------------------------------------------------------------

def test_write_audit_appends_multiple(tmp_path):
    """Scenario 4: Two calls + flush produce two lines."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="first", source="shell")
    write_audit(log_path, event="second", source="shell")
    flush_writes()
    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "first"
    assert json.loads(lines[1])["event"] == "second"


# ---------------------------------------------------------------------------
# Scenario 5: Silent on missing parent dir
# ---------------------------------------------------------------------------

def test_write_audit_silent_on_missing_parent(tmp_path):
    """Scenario 5: No file created, no exception raised."""
    log_path = tmp_path / "nonexistent" / "audit.jsonl"
    write_audit(log_path, event="test", source="shell")
    flush_writes()
    assert not log_path.exists()


# ---------------------------------------------------------------------------
# Scenario 6: PII scrub
# ---------------------------------------------------------------------------

def test_write_audit_scrubs_before_write(tmp_path):
    """Scenario 6: password field is redacted in the written record."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="login", source="shell", password="hunter2")
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["password"] == "[REDACTED]"
    assert record["event"] == "login"


# ---------------------------------------------------------------------------
# Scenario 7: SID from env
# ---------------------------------------------------------------------------

def test_write_audit_sid_from_env(tmp_path, monkeypatch):
    """Scenario 7: SID captured from AGENTFLOW_SESSION_ID env var."""
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "sess-abc")
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="x", source="shell")
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["sid"] == "sess-abc"


# ---------------------------------------------------------------------------
# Scenario 8: Default level INFO
# ---------------------------------------------------------------------------

def test_write_audit_defaults_level_to_info(tmp_path):
    """Scenario 8: level defaults to INFO when not supplied."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="startup", source="shell")
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["level"] == "INFO"


# ---------------------------------------------------------------------------
# Scenario 9: Override level ERROR
# ---------------------------------------------------------------------------

def test_write_audit_preserves_caller_level(tmp_path):
    """Scenario 9: Explicit level=ERROR is preserved in record."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="drain_fail", source="shell", level="ERROR")
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["level"] == "ERROR"


# ---------------------------------------------------------------------------
# Scenario 10: session_type in record when not None
# ---------------------------------------------------------------------------

def test_write_audit_session_type_present(tmp_path):
    """Scenario 10: session_type appears in record when supplied."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="tick", source="shell", session_type="orchestrator")
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["session_type"] == "orchestrator"


# ---------------------------------------------------------------------------
# Scenario 11: session_type absent when None
# ---------------------------------------------------------------------------

def test_write_audit_session_type_absent_when_none(tmp_path):
    """Scenario 11: session_type key not present when None."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="tick", source="shell", session_type=None)
    flush_writes()
    record = json.loads(log_path.read_text())
    assert "session_type" not in record


# ---------------------------------------------------------------------------
# Scenario 12: Extra kwarg tokens=42 in record
# ---------------------------------------------------------------------------

def test_write_audit_extra_kwargs(tmp_path):
    """Scenario 12: Extra kwargs (e.g. tokens=42) appear in the record."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="fill", source="hook", tokens=42)
    flush_writes()
    record = json.loads(log_path.read_text())
    assert record["tokens"] == 42
    assert record["source"] == "hook"


# ---------------------------------------------------------------------------
# Scenario 13: 50 concurrent threads + flush → 50 valid JSON lines
# ---------------------------------------------------------------------------

def test_write_audit_concurrent_threads(tmp_path):
    """Scenario 13: 50 concurrent threads produce 50 valid JSON lines."""
    log_path = tmp_path / "audit.jsonl"
    n = 50
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait()
        write_audit(log_path, event=f"tick_{i}", source="shell", idx=i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    flush_writes()

    lines = log_path.read_text().splitlines()
    assert len(lines) == n
    for line in lines:
        record = json.loads(line)
        assert "event" in record


# ---------------------------------------------------------------------------
# Scenario 14: Rotation at threshold → .1 backup, new entry in fresh file
# ---------------------------------------------------------------------------

def test_rotation_at_threshold(tmp_path, monkeypatch):
    """Scenario 14: File rotates to .1 when >= _MAX_LOG_BYTES."""
    monkeypatch.setattr(_mod, "_MAX_LOG_BYTES", 10)  # tiny threshold
    log_path = tmp_path / "audit.jsonl"

    # Write enough to exceed threshold
    write_audit(log_path, event="big_entry", source="shell", data="x" * 20)
    flush_writes()

    # Write again — rotation should fire
    write_audit(log_path, event="after_rotation", source="shell")
    flush_writes()

    rotated = tmp_path / "audit.jsonl.1"
    assert rotated.exists(), ".1 backup not created"
    lines = log_path.read_text().splitlines()
    assert len(lines) >= 1
    assert json.loads(lines[0])["event"] == "after_rotation"


# ---------------------------------------------------------------------------
# Scenario 15: Rotation shifts .1 → .2
# ---------------------------------------------------------------------------

def test_rotation_shifts_existing(tmp_path, monkeypatch):
    """Scenario 15: Existing .1 is renamed to .2 on a second rotation."""
    monkeypatch.setattr(_mod, "_MAX_LOG_BYTES", 10)
    log_path = tmp_path / "audit.jsonl"

    # First rotation
    write_audit(log_path, event="entry1", source="shell", data="x" * 20)
    flush_writes()
    write_audit(log_path, event="entry2", source="shell", data="y" * 20)
    flush_writes()

    # Second rotation
    write_audit(log_path, event="entry3", source="shell", data="z" * 20)
    flush_writes()
    write_audit(log_path, event="entry4", source="shell")
    flush_writes()

    assert (tmp_path / "audit.jsonl.1").exists()
    assert (tmp_path / "audit.jsonl.2").exists()


# ---------------------------------------------------------------------------
# Scenario 16: Cap at _MAX_ROTATED=2 → no .3
# ---------------------------------------------------------------------------

def test_rotation_cap(tmp_path, monkeypatch):
    """Scenario 16: No .3 file created when _MAX_ROTATED=2."""
    monkeypatch.setattr(_mod, "_MAX_LOG_BYTES", 10)
    monkeypatch.setattr(_mod, "_MAX_ROTATED", 2)
    log_path = tmp_path / "audit.jsonl"

    for i in range(6):
        write_audit(log_path, event=f"e{i}", source="shell", data="x" * 20)
        flush_writes()
        write_audit(log_path, event=f"e{i}_after", source="shell")
        flush_writes()

    assert not (tmp_path / "audit.jsonl.3").exists(), ".3 should not exist with cap=2"
    assert (tmp_path / "audit.jsonl.1").exists()
    assert (tmp_path / "audit.jsonl.2").exists()


# ---------------------------------------------------------------------------
# Scenario 17: No rotation below threshold
# ---------------------------------------------------------------------------

def test_no_rotation_below_threshold(tmp_path, monkeypatch):
    """Scenario 17: File not rotated when below threshold."""
    monkeypatch.setattr(_mod, "_MAX_LOG_BYTES", 10 * 1024 * 1024)  # 10 MB
    log_path = tmp_path / "audit.jsonl"

    write_audit(log_path, event="small", source="shell")
    write_audit(log_path, event="small2", source="shell")
    flush_writes()

    assert not (tmp_path / "audit.jsonl.1").exists()
    assert len(log_path.read_text().splitlines()) == 2


# ---------------------------------------------------------------------------
# Legacy-style test (re-routed to new signature)
# ---------------------------------------------------------------------------

def test_write_audit_appends_jsonl(tmp_path):
    """Basic smoke test: one entry appears after flush."""
    log_path = tmp_path / "audit.jsonl"
    write_audit(log_path, event="test_event", source="shell")
    flush_writes()
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert "ts" in record
    assert "sid" in record
    assert record["event"] == "test_event"
