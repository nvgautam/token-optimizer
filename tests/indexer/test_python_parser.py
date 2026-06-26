"""Tests for agentflow.indexer.parsers.python_parser — T-028a."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentflow.indexer import IndexEntry
from agentflow.indexer.parsers.python_parser import parse


# ─── Fixture source ────────────────────────────────────────────────────────────
# 51 lines → above the 50-line threshold

LARGE_SOURCE = textwrap.dedent("""\
    import os
    import sys
    from pathlib import Path
    from typing import Optional


    CONSTANT = 42


    def top_func(x: int, y: int) -> int:
        \"\"\"Top-level function.\"\"\"
        return x + y


    def another_func(path: Path) -> Optional[str]:
        \"\"\"Another top-level function.\"\"\"
        if path.exists():
            return str(path)
        return None


    class MyClass:
        \"\"\"A simple class.\"\"\"

        class_var = "value"

        def __init__(self, name: str) -> None:
            self.name = name

        def method_one(self, value: int) -> str:
            return f"{self.name}: {value}"

        def method_two(self) -> None:
            pass


    class AnotherClass:
        \"\"\"Another class.\"\"\"

        def compute(self, x: float, y: float) -> float:
            return x * y


    def final_func() -> None:
        \"\"\"Final function.\"\"\"
        pass


    # padding
    # padding
    # padding
    """)


def _write(tmp_path: Path, content: str, name: str = "sample.py") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ─── Test 9: IndexEntry dataclass fields ──────────────────────────────────────

def test_index_entry_fields():
    entry = IndexEntry(
        name="foo",
        kind="function",
        start_line=1,
        end_line=5,
        signature="def foo() -> None:",
    )
    assert entry.name == "foo"
    assert entry.kind == "function"
    assert entry.start_line == 1
    assert entry.end_line == 5
    assert entry.signature == "def foo() -> None:"


def test_index_entry_signature_none():
    entry = IndexEntry(name="Cls", kind="class", start_line=1, end_line=10, signature=None)
    assert entry.signature is None


# ─── Test 1: top-level functions ──────────────────────────────────────────────

def test_parse_extracts_top_level_functions(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    funcs = {e.name: e for e in entries if e.kind == "function"}

    assert "top_func" in funcs
    assert "another_func" in funcs
    assert "final_func" in funcs

    tf = funcs["top_func"]
    assert tf.kind == "function"
    assert tf.start_line < tf.end_line
    assert tf.start_line >= 1


def test_parse_function_line_ranges(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    tf = by_name["top_func"]
    assert tf.start_line == 10
    assert tf.end_line == 12

    af = by_name["another_func"]
    assert af.start_line == 15
    assert af.end_line == 19

    ff = by_name["final_func"]
    assert ff.start_line == 44
    assert ff.end_line == 46


# ─── Test 2: top-level classes ────────────────────────────────────────────────

def test_parse_extracts_top_level_classes(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    classes = {e.name: e for e in entries if e.kind == "class"}

    assert "MyClass" in classes
    assert "AnotherClass" in classes

    mc = classes["MyClass"]
    assert mc.kind == "class"
    assert mc.start_line < mc.end_line
    assert mc.signature is None


def test_parse_class_line_ranges(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    mc = by_name["MyClass"]
    assert mc.start_line == 22
    assert mc.end_line == 34

    ac = by_name["AnotherClass"]
    assert ac.start_line == 37
    assert ac.end_line == 41


# ─── Test 3: class methods in ClassName.method format ─────────────────────────

def test_parse_extracts_class_methods(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    methods = {e.name: e for e in entries if e.kind == "method"}

    assert "MyClass.__init__" in methods
    assert "MyClass.method_one" in methods
    assert "MyClass.method_two" in methods
    assert "AnotherClass.compute" in methods

    m = methods["MyClass.method_one"]
    assert m.kind == "method"
    assert m.start_line < m.end_line


def test_parse_method_line_ranges(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    init = by_name["MyClass.__init__"]
    assert init.start_line == 27
    assert init.end_line == 28

    compute = by_name["AnotherClass.compute"]
    assert compute.start_line == 40
    assert compute.end_line == 41


# ─── Test 4: signatures ───────────────────────────────────────────────────────

def test_parse_function_signature(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    assert by_name["top_func"].signature == "def top_func(x: int, y: int) -> int:"
    assert by_name["another_func"].signature == "def another_func(path: Path) -> Optional[str]:"
    assert by_name["final_func"].signature == "def final_func() -> None:"


def test_parse_method_signature(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    assert by_name["MyClass.__init__"].signature == "def __init__(self, name: str) -> None:"
    assert by_name["MyClass.method_one"].signature == "def method_one(self, value: int) -> str:"
    assert by_name["AnotherClass.compute"].signature == "def compute(self, x: float, y: float) -> float:"


def test_parse_class_signature_is_none(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    by_name = {e.name: e for e in entries}

    assert by_name["MyClass"].signature is None
    assert by_name["AnotherClass"].signature is None


# ─── Test 5 & 6: short / empty files ──────────────────────────────────────────

def test_parse_returns_empty_for_short_file(tmp_path):
    short = "def foo():\n    pass\n"
    assert len(short.splitlines()) < 50
    path = _write(tmp_path, short)
    assert parse(path) == []


def test_parse_returns_empty_for_exactly_49_lines(tmp_path):
    content = "\n".join(["# line"] * 49) + "\n"
    assert len(content.splitlines()) == 49
    path = _write(tmp_path, content)
    assert parse(path) == []


def test_parse_returns_empty_for_empty_file(tmp_path):
    path = _write(tmp_path, "")
    assert parse(path) == []


# ─── Test 7: unreadable file ──────────────────────────────────────────────────

def test_parse_returns_empty_for_nonexistent_file(tmp_path):
    path = tmp_path / "does_not_exist.py"
    result = parse(path)
    assert result == []


# ─── Test 8: invalid syntax ───────────────────────────────────────────────────

def test_parse_returns_empty_for_invalid_syntax(tmp_path):
    bad = ("def broken(\n" + "    pass\n" * 50)  # missing closing paren
    path = _write(tmp_path, bad)
    result = parse(path)
    assert result == []


# ─── Order / completeness check ───────────────────────────────────────────────

def test_parse_returns_all_expected_entries(tmp_path):
    path = _write(tmp_path, LARGE_SOURCE)
    entries = parse(path)
    names = [e.name for e in entries]

    expected = {
        "top_func", "another_func", "final_func",
        "MyClass", "AnotherClass",
        "MyClass.__init__", "MyClass.method_one", "MyClass.method_two",
        "AnotherClass.compute",
    }
    assert expected == set(names)
