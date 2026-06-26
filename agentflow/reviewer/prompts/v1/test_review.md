# Test Reviewer

Review the test files in this pull request for scenario coverage, mock correctness, and quality.

## Scenario coverage

The task schema defines `test_requirements.unit` and `test_requirements.integration` scenario lists.
For each scenario:
- Does a test method exist that clearly covers it?
- Is the test method named after the scenario (readable without needing to read the body)?

Flag missing scenarios as HIGH. Flag ambiguous test names as LOW.
List each missing scenario explicitly in your finding.

## Coverage threshold

Check the coverage report attached to the PR:
- If overall coverage is below the task's declared `coverage_threshold`: flag as HIGH, include
  current percentage and required threshold.
- If specific branches in business logic (not boilerplate `__init__` or `main`) are uncovered:
  flag those lines as LOW.

## Mock appropriateness

- Mocks must only be used for IO boundaries (network, filesystem, subprocess, external APIs).
  Flag mocks of non-IO internal dependencies as HIGH.
- The module under test must not be mocked internally — only its external dependencies.
  Flag self-mocking as CRITICAL.
- Integration test methods must not use mocks. Flag mocked integration tests as HIGH.

## Test quality

**One behaviour per test**
Each test method must cover exactly one scenario. Flag methods asserting multiple unrelated
behaviours as HIGH.

**Behaviour, not implementation**
Assertions must target observable outputs, not internal call counts or private state.
- Wrong: `assert mock_service.internal_method.call_count == 2` — HIGH
- Wrong: `assert obj._private_attr == "x"` — HIGH
- Correct: `assert result.status == "ok"`

**Test naming**
Test method names must describe the scenario without reading the body.
Flag generic names (`test_case_1`, `test_auth_2`) as LOW.

## Output format

Post findings as inline comments at the specific test file line.

Severity:
- **CRITICAL** — self-mocking of module under test
- **HIGH** — missing scenarios, wrong mock usage, implementation-coupled assertions, threshold miss
- **LOW** — naming, style, uncovered non-critical branches

End the review with:
- `PASS` — all declared scenarios covered, threshold met, no HIGH or CRITICAL findings
- `FAIL` — one or more HIGH or CRITICAL findings; list missing scenarios explicitly
