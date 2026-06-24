# Testing Guide

## TDD — red first

Run the test skeleton before writing any implementation code:

```
pytest <test_file> -v
```

All tests must fail with `NotImplementedError`. If a test passes before you write code, the skeleton is wrong — stop and investigate before continuing.

## Behaviour, not implementation

Tests assert what a function does, not how it does it internally.

Correct: `assert result.status == "ok"`
Wrong: `assert mock_db.execute.call_count == 3`

Do not assert on internal call counts, internal state, or private method invocations. Assert on the observable output and side effects declared in the test scenario.

## IO mocks are pre-generated

Your context bundle includes mock fixtures for all external IO boundaries (database, HTTP API calls, filesystem outside your worktree). Use them as provided. Do not introduce new mocking libraries. Do not mock IO that is not declared in the project's test strategy.

## One behaviour per test method

Each test method covers exactly one scenario from your TEST SCENARIOS list. Name the test after the scenario description:

Correct: `test_expired_token_raises_401`
Wrong: `test_auth_cases` or `test_auth_2`

Do not combine multiple assertions for unrelated behaviours in one test method.

## Coverage

After each test turns green, run:

```
pytest --cov=<module> --cov-report=term-missing
```

The missing lines column shows what to test next. Do not open a PR until coverage meets the threshold in your CONFIG section.

## Integration tests

Integration test scenarios run against real dependencies — real filesystem (`tmp_path`), real subprocess calls. Do not use mocks in integration tests. Use `tmp_path` for filesystem isolation so tests do not pollute each other.
