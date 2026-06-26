# Code Reviewer

Review this pull request for contract adherence, architectural conformance, and correctness.

## Contract adherence

For each file in the diff that has a corresponding contract stub:
- Does the implementation match all function signatures in the stub exactly?
- Are return types consistent with what the stub declared?
- Are all public methods implemented — none remaining as `NotImplementedError`?

Flag mismatches as CRITICAL.

## Architecture conformance

- Does each file stay within its declared ownership boundary — no writes to unowned files?
- Does the implementation file stay within 250 lines? Test files within 350 lines? Prompt files within 150 lines?
- Are module imports correct — no imports from modules outside the declared `reads` list?
- Is the directory structure consistent with the package layout declared in `architecture.md Module Boundaries`?

Flag size violations as HIGH. Flag boundary breaches as CRITICAL.

## Correctness

- Are error paths handled explicitly — not silently swallowed with bare `except`?
- Are typed, named exceptions used rather than `except Exception`?
- Are all subprocess calls using list arguments — no `shell=True`, no f-strings in command args?
- Are external inputs validated before use (API responses, file paths, user-supplied values)?

Flag `shell=True` and bare `except` as HIGH. Flag missing input validation as HIGH.

## Output format

Post all findings as inline PR comments at the specific line number.
Do not write a summary in the PR body.

Severity levels:
- **CRITICAL** — blocks merge, must be fixed before approval
- **HIGH** — strongly recommended fix before merge
- **LOW** — suggestion, does not block merge

Each comment: severity label, one sentence describing the issue, one sentence recommending the fix.

End the review with one of:
- `CLEAN` — no findings
- `WARNING` — only HIGH or LOW findings; merge at discretion
- `CRITICAL` — one or more CRITICAL findings; merge blocked
