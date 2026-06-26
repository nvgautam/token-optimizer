# Testing Guide

## Red → Green TDD Cycle

Always start from a failing test. Never write implementation code before you have a failing test.

**Step 1 — Red:** Run the skeleton test file. All tests must fail with `NotImplementedError`.

```
.venv/bin/pytest <test_file> -v
```

If a test passes before you write any code, the skeleton is wrong. Stop, investigate, and escalate
via the blockers file before continuing.

**Step 2 — Green:** Write the minimum code to make one failing test pass. Do not over-implement.

**Step 3 — Refactor:** Clean up without changing behaviour. Run tests again to confirm still green.

**Step 4 — Repeat:** Move to the next failing test. One at a time.

---

## Skeleton Bodies Start as NotImplementedError

All stub function bodies must start as:

```python
def my_function(arg):
    raise NotImplementedError
```

This guarantees every test is red before implementation begins. Never write `pass` or `return None`
as a stub body — those silently pass some assertions and break the red-first guarantee.

---

## Behaviour, Not Implementation

Tests assert what a function does from the outside, not how it does it internally.

**Correct:** `assert result.status == "ok"`
**Wrong:** `assert mock_db.execute.call_count == 3`

Do not assert on internal call counts, internal state, or private method invocations. Assert on
observable outputs and declared side effects only. If the test would break after a valid internal
refactor, it is testing the wrong thing.

One behaviour per test method. Name each test after the scenario it covers:

**Correct:** `test_expired_token_raises_401`
**Wrong:** `test_auth_cases` or `test_auth_2`

---

## IO Boundaries Are Mocked Before Implementation Exists

IO boundaries (file reads, HTTP calls, subprocess invocations, database queries) are mocked in the
skeleton test file before any implementation exists. This is by design.

- Use only the mock fixtures pre-provided in your context bundle.
- Do not introduce new mocking libraries (`unittest.mock` and `pytest-mock` are available).
- Do not mock internal functions of the module under test — only IO boundaries.
- Integration test scenarios run against real dependencies; use `tmp_path` for filesystem isolation.

If an IO boundary is not declared in the project's test strategy, do not mock it. Escalate instead.

---

## Coverage

After each test turns green, check coverage:

```
.venv/bin/pytest --cov=<module> --cov-report=term-missing
```

The missing lines column shows what to test next. Do not open a PR until coverage meets the
threshold in your CONFIG section. Coverage below threshold is a hard gate — not advisory.
