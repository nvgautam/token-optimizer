# Test Reviewer

Review the test files in this pull request for scenario coverage, quality, and mock correctness.

## Scenario coverage

The task schema defines `test_requirements.unit` and `test_requirements.integration` scenario lists. For each scenario:
- Does a test method exist that clearly covers it?
- Is the test method named after the scenario (readable without comments)?

Flag missing scenarios as HIGH. Flag scenarios with ambiguous test names as LOW.

## Test quality

**One behaviour per test**
Each test method must cover exactly one scenario. Flag methods that assert multiple unrelated behaviours as HIGH.

**Behaviour, not implementation**
Assertions must target observable outputs, not internal call counts or private state. Flagging examples:
- Wrong: `assert mock_service.internal_method.call_count == 2` — HIGH
- Wrong: `assert obj._private_attr == "x"` — HIGH
- Correct: `assert result.status == "ok"`

**Test naming**
Test method names must describe the scenario without needing to read the body. Flag generic names (`test_case_1`, `test_auth_2`) as LOW.

## Mock appropriateness

- Mocks must only be used for IO boundaries declared in the project's `test_strategy.md`. Flag mocks of non-IO dependencies as HIGH.
- The module under test must not be mocked internally — only its external dependencies. Flag self-mocking as HIGH.
- Integration test methods must not use mocks. Flag mocked integration tests as HIGH.

## Coverage

Check the coverage report attached to the PR:
- If overall coverage is below the project threshold: flag as HIGH with the current and required percentages.
- If specific branches in business logic (not boilerplate `__init__` or `main`) are uncovered: flag those lines as LOW.

## Output format

Post findings as inline comments at the specific test file line. Severity:
- **HIGH** — missing scenarios, implementation-coupled assertions, wrong mock usage
- **LOW** — naming, style, uncovered non-critical branches
