"""PTY shell tokenizer — tiktoken-based token counter and accumulator.

provider param is reserved for future multi-provider support; ignored now.
No LLM calls, no config reads, no I/O.
"""
import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")
_running_total: int = 0


def count_tokens(text: str, provider: str) -> int:
    """Return token count for text. Pure — no side effects."""
    return len(_encoder.encode(text))


def accumulate(text: str, provider: str) -> int:
    """Add token count for text to running total; return new total."""
    global _running_total
    _running_total += count_tokens(text, provider)
    return _running_total


def reset() -> None:
    """Reset running total to 0."""
    global _running_total
    _running_total = 0
