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
