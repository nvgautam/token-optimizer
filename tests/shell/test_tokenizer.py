"""Tests for agentflow.shell.tokenizer — TDD red phase."""
import agentflow.shell.tokenizer as tok


def setup_function():
    """Reset accumulator before each test."""
    tok.reset()


def test_count_tokens_known_string():
    # "Hello world" encodes to 2 tokens in cl100k_base
    assert tok.count_tokens("Hello world", "claude") == 2


def test_count_tokens_empty_string():
    assert tok.count_tokens("", "claude") == 0


def test_count_tokens_unicode_and_multiline():
    text = "def foo():\n    return '日本語'\n"
    result = tok.count_tokens(text, "claude")
    assert isinstance(result, int)
    assert result > 0


def test_count_tokens_no_side_effects():
    tok.count_tokens("some text", "claude")
    tok.count_tokens("more text", "claude")
    # Running total should still be 0 — count_tokens is pure
    assert tok._running_total == 0


def test_accumulate_running_total():
    first = tok.accumulate("Hello world", "claude")   # 2 tokens
    second = tok.accumulate("Hello world", "claude")  # 2 more tokens
    assert first == 2
    assert second == 4


def test_accumulate_returns_new_total():
    tok.accumulate("Hello world", "claude")  # 2 tokens
    result = tok.accumulate("Hello world", "claude")  # cumulative = 4
    assert result == 4


def test_reset_clears_total():
    tok.accumulate("Hello world", "claude")
    tok.accumulate("Hello world", "claude")
    tok.reset()
    assert tok._running_total == 0


def test_reset_then_accumulate():
    tok.accumulate("Hello world", "claude")
    tok.reset()
    result = tok.accumulate("Hello world", "claude")
    assert result == 2


def test_provider_param_ignored():
    # provider is reserved — same result regardless of value
    a = tok.count_tokens("Hello world", "claude")
    b = tok.count_tokens("Hello world", "gemini")
    assert a == b
