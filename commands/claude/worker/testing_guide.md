# Testing Guide — TDD for Implementer Agents

---

## 1. Red → Green TDD

Write the failing test first. Implement to make it pass. Never write
implementation code before the test exists.

**Sequence:**
1. Write `tests/test_[module_name].py` with one test per function.
2. Run `.venv/bin/pytest tests/test_[module_name].py` — expect failure (red).
3. Implement the function in your owned file.
4. Run pytest again — expect pass (green).
5. Repeat for each function.

Do not collapse steps. Writing implementation first defeats the purpose and
makes regressions harder to detect.

---

## 2. Behaviour, Not Implementation

Test what the function does, not how it does it. Test the public contract, not
internals.

**Good:** `assert result == expected_output`
**Bad:** `assert mock_helper.called` (unless the call itself is the contract)

Testing internal state, private methods, or call order locks the test to the
current implementation. When the implementation changes, the test breaks even
though the behaviour is correct.

---

## 3. IO Mocks

For file I/O, network calls, subprocess: use mocks pre-generated in the test
setup. Do not make real network calls or write real files in unit tests.

```python
from unittest.mock import patch, MagicMock

def test_reads_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("threshold: 85")
    result = load_config(config_file)
    assert result.threshold == 85
```

For network/subprocess, use `patch`:

```python
@patch("agentflow.module.requests.get")
def test_fetch(mock_get):
    mock_get.return_value.json.return_value = {"key": "value"}
    result = fetch_data("https://example.com")
    assert result["key"] == "value"
```

---

## 4. Skeleton Bodies Start as NotImplementedError

Stub implementations start as `raise NotImplementedError`. Your test will fail
(red). Implement to make it pass (green).

```python
def compute_tokens(text: str) -> int:
    raise NotImplementedError
```

This ensures you never accidentally ship a stub.

---

## 5. Coverage Threshold

Your test suite must meet the `coverage_threshold` in the config snapshot
(default 85%). Run with:

```
.venv/bin/pytest --cov=[module] --cov-report=term-missing
```

If coverage is below threshold, add tests for uncovered branches before
committing.

---

## 6. Test File Location

Write tests at `tests/test_[module_name].py`.
For prompt files, write at `tests/prompts/test_[name].py`.

Do not write tests inside the module directory. Keep `tests/` flat for
implementation tests; use `tests/prompts/` for prompt validation tests only.

---

## 7. One Test Per Function

Write one unit test per public function or method. Name tests:

```
test_[function_name]_[scenario]
```

Examples:
- `test_load_config_returns_defaults_when_missing`
- `test_compute_tokens_empty_string`
- `test_build_bundle_raises_on_missing_task`

Multiple scenarios for a single function are encouraged — use the suffix to
distinguish them.

## 8. Edge Cases Are Mandatory

Happy-path tests alone are insufficient. For every function, identify and test:

- **Missing inputs**: absent files, empty strings, None values, missing keys
- **Malformed inputs**: invalid JSON, wrong types, truncated data
- **Boundary conditions**: empty collections, single-element collections, max values
- **Concurrent / isolation**: two instances running simultaneously must not cross-contaminate
- **Failure recovery**: what happens after a prior step failed (e.g. file never written)
- **Idempotency**: running twice produces the same result as running once

If a function silently swallows an exception, the test must assert the audit log entry is written — silence is not acceptable as a test outcome.

## 9. Hook–Skill Contract Tests

Any hook that conditions behavior on `tool_name` must be tested with **every tool the calling skill plausibly uses**, not just the intended happy-path tool.

- Identify the tool the hook expects (e.g. `Write`) and test it passes.
- Identify every other tool the skill *could* realistically use for the same operation (e.g. `Bash`, `Edit`) and test each one explicitly — assert the correct outcome, not just that the hook skips silently.
- The contract "skill X must use tool Y for operation Z" is implicit and will be violated. The test is the only enforcement.

Example failure mode: a hook fires on `Write` to detect a file change; the skill writes via `Bash` instead; the hook silently skips; the system silently breaks. Without a test exercising the `Bash` path, this goes undetected.

## 10. Worktree Testing Requirements

When working in a task worktree, **NEVER run `pip install -e .`** — editable installs pollute
the global environment and break worktree isolation. Instead, **run tests via `python -m pytest`**,
which prepends the worktree directory to `sys.path` for that execution only.

**Run tests like this:**
```bash
cd {worktree_abs_path}
python -m pytest tests/test_[module_name].py
```

This isolates your test execution to the local worktree code without side effects to the global
environment. The pytest module execution method is the correct and safe way to test within
disposable task worktrees.
