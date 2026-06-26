# Test Quality Review Checks

Review the test files introduced or modified by this diff. Focus on test quality and
completeness — not on re-running the test suite.

---

## 1. Scenario Coverage

Verify every `test_scenario` listed in the task definition has a corresponding test
function.

- Match scenario descriptions to test names or docstrings
- A scenario with no corresponding test → flag as WARNING
- Scenarios partially covered (happy path only, no error case) → flag as WARNING

---

## 2. Mock Appropriateness

Check that unit tests mock I/O boundaries and do NOT mock internal functions.

Correct mocking targets (I/O boundaries):
- File system reads/writes (`open`, `pathlib.Path.read_text`, etc.)
- Network calls (`httpx`, `requests`, `socket`)
- Subprocess invocations (`subprocess.run`, `Popen`)
- External APIs (LLM clients, GitHub API, etc.)

Incorrect mocking targets (flag as WARNING):
- Internal functions within the same module under test
- Private helper methods (`_parse_x`, `_build_y`)
- Functions that contain only pure logic with no I/O

Mocking internals tests implementation, not behaviour. Flag as WARNING.

---

## 3. Coverage Threshold

Verify the `coverage_threshold` from the task definition is met. Default is 85% if
not specified.

If coverage data is not available in the diff context, note that it should be verified
in CI. Flag as WARNING only if test count or scenario mapping suggests obvious gaps.

---

## 4. Test Naming

Tests should be named `test_[function]_[scenario]` (e.g., `test_parse_config_missing_key`).

Flag test names that do not convey the function under test and the scenario as WARNING.
Single-word test names (e.g., `test_it`, `test_works`) always fail this check.

---

## 5. No Test-Only Business Logic

Tests must not contain business logic or implement the feature they are testing.

Signs of test-only business logic:
- A test function that computes the expected output rather than asserting a known value
- A helper inside the test file that duplicates production code
- A test that cannot fail without also breaking the feature it tests

Flag as CRITICAL if a test re-implements the production feature under test.

---

## 6. Integration Test Scope

Integration tests should cross module boundaries or interact with real I/O (real
filesystem, real subprocess, real network — or a local stub server).

Flag as WARNING if:
- A test in `tests/integration/` mocks all external dependencies (it is a unit test)
- A test in `tests/unit/` crosses module boundaries or touches real I/O (wrong location)

---

## Output Format

- `CRITICAL: [finding] — [file:line]` — blocks merge; must be fixed
- `WARNING:  [finding] — [file:line]` — surfaces to human at review gate
- `CLEAN` if no findings in this section
